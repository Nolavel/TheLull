"""Minimal bridge between the existing day and evening labs (no parallel world).

This is an integration PROBE, not gameplay-ready code. It explicitly undoes
the day's legacy flat night charge before calling the real evening simulator.
The day still has no unified character clock, hunger or thirst; see audit docs.
No changes to the Claude/Codex-owned files are required.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from statistics import mean

from .agent import Agent
from .evening import (COOLING_RATE_C_PER_H, EXPEDITION, SHORT_WALK,
                      Body, EveningBeliefs, Room, choose)
from .evening_run import play
from .sim import DEPART_MIN, run_day
from .world import World


def linked(seed: int, days: int, *, variant: str = "B_readable",
           profile: str = "local") -> dict:
    if days < 1:
        raise ValueError("days must be positive")
    world = World.load("district_v0", variant)
    agent = Agent(profile, world)
    loot_rng = random.Random(f"{seed}:loot")
    room = Room(fuel=world.start_fuel)
    body = Body()
    beliefs = EveningBeliefs()
    insulated_once = False
    out = []

    for day in range(1, days + 1):
        weather = world.roll_weather(random.Random(f"{seed}:weather:{day}"))
        fuel_at_dawn = room.fuel
        record, legacy_fuel_after_night = run_day(
            world, agent, weather, loot_rng, day, room.fuel)

        # run_day ends by billing an OLD, flat night. Reconstruct its pre-night
        # value, then bill exactly ONE real evening/night using evening.play.
        # This works only for this version of run_day and is a temporary adapter.
        recovered_pre_night = record.fuel_morning + record.carried
        room.fuel = recovered_pre_night

        # Day's travel/search creates fatigue; heuristic until Claude owns a
        # common time/needs contract. No covert perfect knowledge of tomorrow.
        activity_h = max(0.0, (record.actual_return or DEPART_MIN) - DEPART_MIN) / 60
        body.fatigue = min(100.0, body.fatigue + activity_h * 5.0)
        tomorrow = EXPEDITION if day % 3 == 1 else SHORT_WALK
        candidate, reason, revised = choose(body, room, beliefs, tomorrow, -18)

        choice = candidate["option"]
        guard = None
        if choice.startswith("A:") and room.furniture <= 0:
            # Owner code currently awards logs even when furniture is empty.
            guard = "blocked impossible furniture-to-fuel conversion"
            choice = "B: лечь раньше на том, что есть"
        elif choice.startswith("C:") and insulated_once:
            # Owner code can repeatedly halve the cooling rate for one repair.
            guard = "blocked repeated sealing of the same room"
            choice = "B: лечь раньше на том, что есть"
        if choice.startswith("C:"):
            insulated_once = True

        night = play(choice, -18, room, body, beliefs)
        out.append({
            "day": day, "weather_storm_start": weather.storm_start,
            "went_out": record.went_out, "target": record.target,
            "return_min": record.actual_return,
            "carried": record.carried, "fuel_dawn": round(fuel_at_dawn, 2),
            "fuel_before_night": round(recovered_pre_night, 2),
            "legacy_night_ignored": round(legacy_fuel_after_night, 2),
            "planned": tomorrow.name, "choice": choice[:1],
            "proposed": candidate["option"][:1], "guard": guard,
            "wakes": night["woke_cold"], "slept_h": night["slept_hours"],
            "fuel_next_dawn": room.fuel, "furniture_next_dawn": room.furniture,
            "fatigue_next_dawn": body.fatigue, "warmth_next_dawn_c": body.core_c,
        })
    return {
        "seed": seed, "variant": variant, "profile": profile, "days": out,
        "limits": [
            "Uses real lab.sim.run_day and lab.evening_run.play; no duplicated weather model.",
            "Old flat night is explicitly disregarded; prevents a double fuel charge.",
            "Day fatigue bridge is a placeholder; game clock and four needs are not shared.",
            "Guards stop two infinite-resource exploits in the probe, not in owner modules.",
            "This is NOT a verified complete TLD-like gameplay loop.",
        ],
    }


def study(seeds: int = 60, days: int = 7) -> dict:
    if not 1 <= seeds <= 1000:
        raise ValueError("seeds must be 1..1000")
    runs = [linked(i, days) for i in range(1, seeds + 1)]
    rows = [d for r in runs for d in r["days"]]
    choices = Counter(d["choice"] for d in rows)
    blocked = Counter(d["guard"] for d in rows if d["guard"])
    return {
        "seeds": seeds, "days": days, "sampled_nights": len(rows),
        "mean_trips_per_seed": round(mean(sum(d["went_out"] for d in r["days"]) for r in runs), 2),
        "mean_loot_per_seed": round(mean(sum(d["carried"] for d in r["days"]) for r in runs), 2),
        "mean_cold_wakes_per_seed": round(mean(sum(d["wakes"] for d in r["days"]) for r in runs), 2),
        "mean_fuel_end": round(mean(r["days"][-1]["fuel_next_dawn"] for r in runs), 2),
        "mean_fatigue_end": round(mean(r["days"][-1]["fatigue_next_dawn"] for r in runs), 2),
        "evening_choices": dict(choices), "blocked_invalid_choices": dict(blocked),
        "one_example": runs[0]["days"],
        "limits": runs[0]["limits"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=60)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json")
    args = parser.parse_args()
    report = study(args.seeds, args.days)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
