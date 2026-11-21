"""First connected 24-hour survival loop. Pure Python research harness.

One World, one Agent/Beliefs, one Body and one Room survive across dawns.
`sim.run_day` owns travel/search; `evening_run.play` owns the entire night.
No second weather generator, night billing or synthetic resource replenishment.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import asdict
from statistics import mean

from .agent import Agent
from .body import DEATH_C, Body
from .evening import Room, Tomorrow, UNDECIDED, choose, step_body
from .evening_run import play
from .sim import DEPART_AFTER_DAWN_MIN, DayRecord, clock, run_day
from .world import DAY_MINUTES, World

STEP_H = 0.25


def _shelter_wait(room: Room, body: Body, outside_c: float, minutes: float) -> float:
    """Only actually elapsed minutes are billed, including partial terminal ticks."""
    if minutes < -1e-8:
        raise ValueError("time cannot move backwards")
    left = max(0.0, minutes / 60.0)
    used = 0.0
    while left > 1e-9 and not body.terminal:
        step = min(STEP_H, left)
        room.step(step)
        actual = step_body(body, room, outside_c, step, asleep=False, fatigue_per_h=2.0)
        if actual <= 0:
            break
        used += actual
        left -= actual
    return used * 60.0


def run(seed: int, days: int = 3, *, variant: str = "B_readable",
        profile: str = "local", intentions: list[Tomorrow] | None = None,
        initial_furniture: int = 2, recheck_policy: bool = True) -> dict:
    """Advance one shared state. Partial days are NOT credited as dawns."""
    if days < 1:
        raise ValueError("days must be positive")
    if initial_furniture < 0:
        raise ValueError("furniture must be non-negative")
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

        _shelter_wait(room, body, world.air_temp_c, departure - world.dawn_min)
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
            evening_start = max(float(world.day_length), return_minute)
            _shelter_wait(room, body, world.air_temp_c, evening_start - return_minute)

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
                night = play(
                    proposed["option"], world.air_temp_c, room, body,
                    agent.beliefs, hours_of_night=actual_night_h
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
        "end_reason": end_reason, "history": history,
        "limits": [
            "Partial days are counted in elapsed_minutes, NOT days_completed.",
            "The terminal threshold is a game-model stop, not a physiological prediction.",
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
