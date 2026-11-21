"""First connected 24-hour survival loop. Pure Python research harness.

One World, one Agent/Beliefs, one Body and one Room survive across dawns.
`sim.run_day` owns travel/search; `evening_run.play` owns the entire night.
No second weather generator, night billing or synthetic resource replenishment.
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Callable
from collections import Counter
from dataclasses import asdict
from statistics import mean

from .agent import Agent
from .body import DEATH_C, Body
from .evening import Room, Tomorrow, UNDECIDED, choose, step_body
from .evening_run import play
from .heat_choice import LIGHT, DecisionProvider, make_heat_decision
from .sim import DEPART_AFTER_DAWN_MIN, DayRecord, clock, run_day
from .world import DAY_MINUTES, World

STEP_H = 0.25
HEATING_POLICIES = ("dusk", "at_dawn", "on_return", "cold_trigger_36c")


def _light_fire(room: Room, body: Body, events: list[dict], reason: str) -> bool:
    """A decision can use only the current room fuel and observable body state."""
    if body.terminal or room.fire_lit or room.fuel <= 0:
        return False
    room.fire_lit = True
    events.append({"elapsed_minute": round(body.elapsed_minutes, 4),
                   "reason": reason, "fuel_at_ignition": round(room.fuel, 3),
                   "core_at_ignition_c": round(body.core_c, 4)})
    return True


def _shelter_wait(room: Room, body: Body, outside_c: float, minutes: float,
                  *, heating_policy: str = "dusk",
                  ignition_events: list[dict] | None = None,
                  before_tick: Callable[[], None] | None = None,
                  after_tick: Callable[[float, float, float, bool], None] | None = None) -> float:
    """Only actually elapsed minutes are billed, including partial terminal ticks."""
    if minutes < -1e-8:
        raise ValueError("time cannot move backwards")
    left = max(0.0, minutes / 60.0)
    used = 0.0
    while left > 1e-9 and not body.terminal:
        if before_tick is not None:
            before_tick()
        if (heating_policy == "cold_trigger_36c" and body.core_c <= 36.0
                and ignition_events is not None):
            _light_fire(room, body, ignition_events, "observed_core_at_or_below_36c")
        step = min(STEP_H, left)
        core_before = body.core_c
        burning_before = room.fire_lit and room.fuel > 0
        room.step(step)
        actual = step_body(body, room, outside_c, step, asleep=False, fatigue_per_h=2.0)
        if after_tick is not None and actual > 0:
            after_tick(core_before, body.core_c, actual, burning_before)
        if actual <= 0:
            break
        used += actual
        left -= actual
    return used * 60.0


def run(seed: int, days: int = 3, *, variant: str = "B_readable",
        profile: str = "local", intentions: list[Tomorrow] | None = None,
        initial_furniture: int = 2, recheck_policy: bool = True,
        heating_policy: str = "dusk",
        decision_provider: DecisionProvider | None = None) -> dict:
    """Advance one shared state. Partial days are NOT credited as dawns."""
    if days < 1:
        raise ValueError("days must be positive")
    if initial_furniture < 0:
        raise ValueError("furniture must be non-negative")
    if heating_policy not in (*HEATING_POLICIES, "agent"):
        raise ValueError(f"unknown heating policy: {heating_policy}")
    if decision_provider is not None and heating_policy != "agent":
        raise ValueError("human decisions are only accepted in heating_policy=agent")
    world = World.load("district_v0", variant)
    agent = Agent(profile, world, allow_rechecks=recheck_policy)
    body = Body()
    room = Room(fuel=world.start_fuel, furniture=initial_furniture)
    loot_rng = random.Random(f"{seed}:loot")
    history = []
    end_reason = None

    for day in range(1, days + 1):
        weather = world.roll_weather(random.Random(f"{seed}:weather:{day}"))
        start_clock = world.dawn_min + (day - 1) * DAY_MINUTES
        start_elapsed = body.elapsed_minutes
        fuel_at_dawn = room.fuel
        core_at_dawn = body.core_c
        fatigue_at_dawn = body.fatigue
        furniture_at_dawn = room.furniture
        fuel_burned_at_dawn = room.burned_fuel_total
        fire_hours_at_dawn = room.fire_hours_total
        day_record = DayRecord(day=day, fuel_morning=room.fuel)
        plan = intentions[(day - 1) % len(intentions)] if intentions else UNDECIDED
        revised = plan
        proposed = None
        why = "до вечернего выбора не дошёл"
        night = None
        learned = "ночных наблюдений нет"
        departure = world.dawn_min + max(
            0, DEPART_AFTER_DAWN_MIN - (15 if body.packed else 0)
        )
        return_minute = None
        evening_start = None
        actual_night_h = 0.0
        packed_before_departure = body.packed
        phase = "morning_shelter"
        ignitions: list[dict] = []
        stove_decisions = []
        stove_outcomes = []
        pending = None
        last_prompt_at = None
        last_prompt_core = None

        def settle_previous() -> None:
            nonlocal pending
            if pending is None:
                return
            d, when, before_burn, before_fire_hours, before_core = pending
            outcome = {
                "decision_index": len(stove_decisions) - 1,
                "observed_at_elapsed_minute": round(body.elapsed_minutes, 5),
                "elapsed_since_decision_h": round(
                    (body.elapsed_minutes - when) / 60.0, 5
                ),
                "observed_core_delta_c": round(body.core_c - before_core, 5),
                "realized_fuel_burned": round(
                    room.burned_fuel_total - before_burn, 5
                ),
                "realized_fire_hours": round(
                    room.fire_hours_total - before_fire_hours, 5
                ),
                "fuel_after": round(room.fuel, 5),
                "next_intention": plan.name,
            }
            stove_outcomes.append(outcome)
            d.outcome = (
                f"наблюдение через {(body.elapsed_minutes - when) / 60.0:.2f} ч: "
                f"тело {before_core:.2f}→{body.core_c:.2f}°C; "
                f"печь сожгла {room.burned_fuel_total - before_burn:.3f} топлива "
                f"за {room.fire_hours_total - before_fire_hours:.3f} ч; "
                f"дров осталось {room.fuel:.3f}"
            )
            pending = None

        def decide_stove(point: str, window_h: float,
                         away_h: float = 0.0) -> bool:
            nonlocal pending, last_prompt_at, last_prompt_core
            if body.terminal or room.fire_lit or room.fuel <= 0:
                return False
            settle_previous()
            d = make_heat_decision(
                body, room, agent.beliefs, plan, room.felt_c(world.air_temp_c),
                point, window_h, away_h=away_h, dawn_min=world.dawn_min,
                provider=decision_provider,
            )
            stove_decisions.append(d)
            last_prompt_at = body.elapsed_minutes
            last_prompt_core = body.core_c
            pending = (d, body.elapsed_minutes, room.burned_fuel_total,
                       room.fire_hours_total, body.core_c)
            if d.choice == LIGHT:
                return _light_fire(room, body, ignitions, f"choice:{point}")
            return False

        def poll_stove() -> None:
            if last_prompt_at is None or last_prompt_core is None:
                return
            delta_m = body.elapsed_minutes - last_prompt_at
            # A meaningful second observation, not a 15-minute prompt flood.
            if (delta_m >= 90.0 or
                (delta_m >= 30.0 and last_prompt_core - body.core_c >= 0.65)):
                decide_stove("повторная оценка в убежище", 1.0)

        def observe_thermal(before: float, after: float, used_h: float,
                            burning: bool) -> None:
            if not burning and not room.fire_lit:
                lesson = agent.beliefs.observe_shelter_cooling(
                    before, after, used_h
                )
                if lesson and stove_decisions:
                    stove_decisions[-1].belief_update = lesson

        if heating_policy == "agent":
            # Real initial point: the current fire/fuel/body and the known
            # departure plan; not future weather or unknown house inventory.
            estimated_trip = agent.rank_targets()
            likely_away = (
                (2 * estimated_trip[0]["minutes"] + 30) / 60.0
                if estimated_trip else 0.0
            )
            decide_stove("утро", (departure - world.dawn_min) / 60.0,
                         away_h=likely_away)
        if heating_policy == "at_dawn":
            _light_fire(room, body, ignitions, "first_light")
        _shelter_wait(
            room, body, world.air_temp_c, departure - world.dawn_min,
            heating_policy=heating_policy, ignition_events=ignitions,
            before_tick=poll_stove if heating_policy == "agent" else None,
            after_tick=observe_thermal if heating_policy == "agent" else None,
        )
        fuel_at_departure = room.fuel

        if not body.terminal:
            phase = "trip"
            # Daytime travel, searching and storm waits use THIS same body.
            day_record, _ = run_day(
                world, agent, weather, loot_rng, day, fuel_at_departure,
                body=body, charge_legacy_night=False
            )

        if not body.terminal:
            # A returned trip deposits only what actually made it home.
            if day_record.went_out:
                if day_record.actual_return is None:
                    raise AssertionError("nonterminal trip has no actual return")
                elapsed_out = day_record.actual_return - departure
                if elapsed_out < -1e-8:
                    raise ValueError("return precedes departure")
                room.step(elapsed_out / 60.0)
                room.fuel += day_record.carried
                body.packed = False
                return_minute = float(day_record.actual_return)
            else:
                return_minute = float(departure)

            phase = "day_shelter"
            if heating_policy == "on_return":
                _light_fire(room, body, ignitions, "returned_or_stayed_home")
            elif heating_policy == "agent":
                decide_stove("возвращение в убежище", 1.0)
            evening_start = max(float(world.day_length), return_minute)
            _shelter_wait(
                room, body, world.air_temp_c, evening_start - return_minute,
                heating_policy=heating_policy, ignition_events=ignitions,
                before_tick=poll_stove if heating_policy == "agent" else None,
                after_tick=observe_thermal if heating_policy == "agent" else None,
            )

        if not body.terminal:
            actual_night_h = (
                world.dawn_min + DAY_MINUTES - evening_start
            ) / 60.0
            if actual_night_h <= 0:
                end_reason = "не вернулся к следующему рассвету"
            else:
                phase = "evening_and_night"
                proposed, why, revised = choose(
                    body, room, agent.beliefs, plan, world.air_temp_c,
                    daylight_hours=world.daylight_hours,
                    night_hours=actual_night_h
                )
                if heating_policy == "agent":
                    decide_stove("вечер перед работой", 1.5)
                night_args = {"hours_of_night": actual_night_h}
                if heating_policy == "agent":
                    night_args["automatic_ignition"] = False
                    night_args["on_fire_opportunity"] = (
                        lambda point, hours: decide_stove(point, min(hours, 2.0))
                    )
                night = play(
                    proposed["option"], world.air_temp_c, room, body,
                    agent.beliefs, **night_args
                )
                if not body.terminal:
                    if night["observed_burn_rate"] is not None:
                        learned = agent.beliefs.observe_burn_rate(
                            night["observed_burn_rate"]
                        )
                    elif night["burn_rate_lower_bound"] is not None:
                        learned = agent.beliefs.observe_rate_lower_bound(
                            night["burn_rate_lower_bound"]
                        )

        settle_previous()
        elapsed_today = body.elapsed_minutes - start_elapsed
        if body.terminal:
            end_reason = body.terminal_reason
        elif end_reason is None:
            if abs(elapsed_today - DAY_MINUTES) > 1e-5:
                raise AssertionError(
                    f"missing or double-billed time: {elapsed_today} / 1440 minutes"
                )
            if body.fatigue >= 100.0:
                end_reason = "усталость достигла предела"
            elif (room.fuel <= 0 and room.furniture <= 0
                  and not any(v > 0 for v in world.loot.values())):
                end_reason = "исчерпаны доступные в районе источники топлива"

        if room.fuel < -1e-9 or room.furniture < 0 or any(v < 0 for v in world.loot.values()):
            raise AssertionError("world created negative resources")
        complete_dawn = not body.terminal and abs(elapsed_today - DAY_MINUTES) < 1e-5
        elapsed_rounded = round(elapsed_today, 6)
        history.append({
            "day": day, "world_weather": asdict(weather),
            "starting_dawn_minute": start_clock,
            # None is intentional: a partial day must not invent the next dawn.
            "next_dawn_minute": start_clock + DAY_MINUTES if complete_dawn else None,
            "completed_dawn": complete_dawn,
            "phase_at_end": phase,
            "minutes_accounted": elapsed_rounded,
            "stop_at_minute": round(start_clock + elapsed_today, 6),
            "terminal_at_minute": body.terminal_at_minute,
            "departure_minute": round(departure, 3)
                if phase != "morning_shelter" else None,
            "return_minute": round(return_minute, 3)
                if return_minute is not None else None,
            "night_start_minute": round(evening_start, 3)
                if evening_start is not None and phase == "evening_and_night" else None,
            "night_hours": round(actual_night_h, 6),
            "fuel_at_dawn": round(fuel_at_dawn, 3),
            "fuel_at_departure": round(fuel_at_departure, 3),
            "stove_decisions": [asdict(d) for d in stove_decisions],
            "stove_outcomes": stove_outcomes,
            "fuel_burned_today": round(
                room.burned_fuel_total - fuel_burned_at_dawn, 5
            ),
            "fire_hours_today": round(
                room.fire_hours_total - fire_hours_at_dawn, 5
            ),
            "heating_policy": heating_policy,
            "early_ignitions": ignitions,
            "fuel_delivered": day_record.carried if return_minute is not None
                and day_record.went_out else 0,
            "carried": day_record.carried,
            "fuel_next_dawn": round(room.fuel, 3),
            "furniture_at_dawn": furniture_at_dawn,
            "furniture_next_dawn": room.furniture,
            "core_at_dawn": round(core_at_dawn, 4),
            "core_next_dawn": round(body.core_c, 4),
            "fatigue_at_dawn": round(fatigue_at_dawn, 3),
            "fatigue_next_dawn": round(body.fatigue, 3),
            "packed_before_departure": packed_before_departure,
            "day_trip": {
                "went_out": day_record.went_out,
                "target": day_record.target,
                "carried": day_record.carried,
                "search_minutes": day_record.search_minutes,
                "recheck_searches": day_record.recheck_searches,
                "empty_searches": day_record.empty_searches,
                "terminal_minute": day_record.terminal_minute,
                "events": day_record.events,
                "next_intention": day_record.next_intention,
                "decisions": [asdict(d) for d in day_record.decisions],
            },
            "evening": {
                "intention": plan.name, "revision": revised.name,
                "chose": proposed["option"] if proposed else "NOT_REACHED",
                "why": why,
                "predicted_ready": (proposed["ready_for_tomorrow_expected"]
                                    if proposed else None),
                "lesson": learned,
            },
            "night": night if night is not None else {
                "night_elapsed_h": 0.0,
                "slept_hours": 0.0,
                "woke_cold": 0,
                "fire_out_at": None,
                "terminal": body.terminal_reason,
            },
            "beliefs_after": {
                "cooling_rate_est": round(agent.beliefs.cooling_rate_est, 4),
                "burn_rate_est": round(agent.beliefs.burn_rate_est, 4),
                "known_locations": sorted(agent.beliefs.loot),
                "estimated_loot": dict(sorted(agent.beliefs.loot.items())),
                "confirmed_empty": sorted(agent.beliefs.confirmed_empty),
            },
            "remaining_loot": dict(sorted(world.loot.items())),
            "end_reason": end_reason,
        })
        if end_reason:
            break

    return {
        "seed": seed, "variant": variant, "profile": profile,
        "days_requested": days,
        "days_started": len(history),
        "days_completed": sum(d["completed_dawn"] for d in history),
        "elapsed_minutes": round(body.elapsed_minutes, 6),
        "elapsed_days": round(body.elapsed_minutes / DAY_MINUTES, 6),
        "terminal_at_minute": body.terminal_at_minute,
        "recheck_policy": recheck_policy,
        "heating_policy": heating_policy,
        "decision_source": (
            "human" if decision_provider is not None
            else "agent" if heating_policy == "agent"
            else "scripted_baseline"
        ),
        "end_reason": end_reason, "history": history,
        "limits": [
            "Partial days are counted in elapsed_minutes, NOT days_completed.",
            "The terminal threshold is a game-model stop, not a physiological prediction.",
            "Heat policies are controlled counterfactuals, not a validated agent choice.",
            "Daytime choices still optimize fuel, not water/food.",
            "A fixed dawn+dusk schedule, no interpolated weather across midnight.",
            "No resource respawn or balance calibration.",
            "Legacy sim.run and standalone linked_days remain separate baselines."
        ],
    }


def study(seeds: int = 30, days: int = 7) -> dict:
    runs = [run(seed=i, days=days) for i in range(1, seeds + 1)]
    completed = [r["days_completed"] for r in runs]
    return {
        "seeds": seeds, "days": days,
        "mean_days_completed": round(mean(completed), 2),
        "end_reasons": dict(Counter(r["end_reason"] or "horizon" for r in runs)),
        "evening_choices": dict(Counter(d["evening"]["chose"][0]
                                for r in runs for d in r["history"])),
        "mean_trips": round(mean(sum(d["day_trip"]["went_out"] for d in r["history"])
                                 for r in runs), 2),
        "one_example": runs[0]["history"], "limits": runs[0]["limits"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--seeds", type=int, default=0)
    parser.add_argument("--variant", choices=("A_safe", "B_readable", "C_unreadable"),
                        default="B_readable")
    parser.add_argument("--profile", choices=("local", "novice"), default="local")
    parser.add_argument("--json")
    args = parser.parse_args()
    result = study(args.seeds, args.days) if args.seeds else run(
        args.seed, args.days, variant=args.variant, profile=args.profile)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
