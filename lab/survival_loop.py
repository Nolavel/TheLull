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
from .sim import DEPART_AFTER_DAWN_MIN, clock, run_day
from .world import DAY_MINUTES, World

STEP_H = 0.25


def _shelter_wait(room: Room, body: Body, outside_c: float, minutes: float) -> None:
    """A real time advance while indoors: the room, stove and body all evolve."""
    if minutes < -1e-8:
        raise ValueError("time cannot move backwards")
    left = max(0.0, minutes / 60.0)
    while left > 1e-9:
        step = min(STEP_H, left)
        room.step(step)
        step_body(body, room, outside_c, step, asleep=False, fatigue_per_h=2.0)
        left -= step


def run(seed: int, days: int = 3, *, variant: str = "B_readable",
        profile: str = "local", intentions: list[Tomorrow] | None = None,
        initial_furniture: int = 2) -> dict:
    """Advance from one dawn to the next, preserving actual resources and memories."""
    if days < 1:
        raise ValueError("days must be positive")
    if initial_furniture < 0:
        raise ValueError("furniture must be non-negative")
    world = World.load("district_v0", variant)
    agent = Agent(profile, world)
    body = Body()
    room = Room(fuel=world.start_fuel, furniture=initial_furniture)
    loot_rng = random.Random(f"{seed}:loot")
    history = []
    end_reason = None

    for day in range(1, days + 1):
        weather = world.roll_weather(random.Random(f"{seed}:weather:{day}"))
        fuel_at_dawn = room.fuel
        core_at_dawn = body.core_c
        fatigue_at_dawn = body.fatigue
        furniture_at_dawn = room.furniture

        # Morning preparation occupies real time, including a shortened prepared departure.
        departure = world.dawn_min + max(0, DEPART_AFTER_DAWN_MIN - (15 if body.packed else 0))
        _shelter_wait(room, body, world.air_temp_c, departure - world.dawn_min)
        fuel_at_departure = room.fuel
        packed_before_departure = body.packed

        # The day observes the same body that woke after the previous night.
        # No flat/synthetic night is charged by this call.
        day_record, fuel_after_trip = run_day(
            world, agent, weather, loot_rng, day, fuel_at_departure,
            body=body, charge_legacy_night=False
        )

        # The stove continues burning in the actual shelter during the trip,
        # not for free while the traveller is outside.
        if day_record.went_out:
            assert day_record.actual_return is not None
            elapsed_out = day_record.actual_return - departure
            if elapsed_out < -1e-8:
                raise ValueError("return precedes departure")
            room.step(elapsed_out / 60.0)
            room.fuel += day_record.carried
            body.packed = False  # its travel preparation has been used
            return_minute = float(day_record.actual_return)
        else:
            return_minute = float(departure)

        # No omitted hours between return and dusk: they are spent in the shelter.
        evening_start = max(float(world.day_length), return_minute)
        _shelter_wait(room, body, world.air_temp_c, evening_start - return_minute)
        actual_night_h = ((world.dawn_min + DAY_MINUTES) - evening_start) / 60.0
        if actual_night_h <= 0:
            end_reason = "не вернулся к следующему рассвету"
            break

        plan = intentions[(day - 1) % len(intentions)] if intentions else UNDECIDED
        proposed, why, revised = choose(
            body, room, agent.beliefs, plan, world.air_temp_c,
            daylight_hours=world.daylight_hours, night_hours=actual_night_h
        )
        night = play(proposed["option"], world.air_temp_c, room, body, agent.beliefs,
                     hours_of_night=actual_night_h)

        learned = "наблюдений о расходе нет"
        if night["observed_burn_rate"] is not None:
            learned = agent.beliefs.observe_burn_rate(night["observed_burn_rate"])
        elif night["burn_rate_lower_bound"] is not None:
            learned = agent.beliefs.observe_rate_lower_bound(night["burn_rate_lower_bound"])

        total_min = departure - world.dawn_min + (
            return_minute - departure) + (evening_start - return_minute) + actual_night_h * 60
        if abs(total_min - DAY_MINUTES) > 1e-6:
            raise AssertionError(f"lost or double-counted time: {total_min} minutes")
        if room.fuel < -1e-9 or room.furniture < 0 or any(v < 0 for v in world.loot.values()):
            raise AssertionError("world created negative resources")

        if body.core_c <= DEATH_C + 0.2:
            end_reason = "температура тела достигла предела"
        elif body.fatigue >= 100.0:
            end_reason = "усталость достигла предела"
        elif room.fuel <= 0 and room.furniture <= 0 and not any(v > 0 for v in world.loot.values()):
            end_reason = "исчерпаны доступные в районе источники топлива"

        history.append({
            "day": day, "world_weather": asdict(weather),
            "starting_dawn_minute": world.dawn_min + (day - 1) * DAY_MINUTES,
            "next_dawn_minute": world.dawn_min + day * DAY_MINUTES,
            "minutes_accounted": round(total_min, 4),
            "departure_minute": round(departure, 3),
            "return_minute": round(return_minute, 3),
            "night_start_minute": round(evening_start, 3),
            "night_hours": round(actual_night_h, 3),
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
            "day_trip": {"went_out": day_record.went_out,
                         "target": day_record.target,
                         "carried": day_record.carried,
                         "events": day_record.events,
                         "decisions": [asdict(d) for d in day_record.decisions]},
            "evening": {"intention": plan.name, "revision": revised.name,
                        "chose": proposed["option"],
                        "why": why,
                        "predicted_ready": proposed["ready_for_tomorrow_expected"],
                        "lesson": learned},
            "night": night,
            "beliefs_after": {
                "cooling_rate_est": round(agent.beliefs.cooling_rate_est, 4),
                "burn_rate_est": round(agent.beliefs.burn_rate_est, 4),
                "known_locations": sorted(agent.beliefs.loot),
            },
            "remaining_loot": dict(sorted(world.loot.items())),
            "end_reason": end_reason,
        })
        if end_reason:
            break

    return {"seed": seed, "variant": variant, "profile": profile,
            "days_requested": days, "days_completed": len(history),
            "end_reason": end_reason, "history": history,
            "limits": ["Daytime choices still optimize fuel, not water/food.",
                       "A fixed dawn+dusk schedule, no interpolated weather across midnight.",
                       "No resource respawn or balance calibration.",
                       "Legacy sim.run and standalone linked_days remain separate research baselines."]}


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
