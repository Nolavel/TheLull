"""Paired, finite-fuel test of WHEN to light a shelter stove, not how to tune it.

Every arm uses canonical survival_loop.run with the exact same finite world,
fuel yield, weather (seed, day), body and evening rules. Only the timing policy
changes. The reactive policy observes current body core, never future weather.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from statistics import mean

from .survival_loop import HEATING_POLICIES, run
from .world import World

VARIANTS = ("A_safe", "B_readable", "C_unreadable")
PROFILES = ("novice", "local")


def _mean(values):
    return round(mean(values), 4)


def experiment(seeds: int = 30, days: int = 7) -> dict:
    if not 1 <= seeds <= 100 or not 1 <= days <= 30:
        raise ValueError("seeds must be 1..100 and days 1..30")

    groups = {}
    checks = Counter()
    exemplars = {}
    all_runs = {}
    for variant in VARIANTS:
        initial_stock = World.load("district_v0", variant)
        for profile in PROFILES:
            for seed in range(1, seeds + 1):
                key = (variant, profile, seed)
                all_runs[key] = {
                    policy: run(seed, days, variant=variant, profile=profile,
                                heating_policy=policy)
                    for policy in HEATING_POLICIES
                }
                baseline = all_runs[key]["dusk"]
                for policy, story in all_runs[key].items():
                    for b, d in zip(baseline["history"], story["history"]):
                        if b["world_weather"] != d["world_weather"]:
                            checks["weather_mismatch"] += 1
                    if story["terminal_at_minute"] is not None:
                        if abs(story["terminal_at_minute"] - story["elapsed_minutes"]) > .001:
                            checks["terminal_clock_mismatch"] += 1
                    if story["days_completed"] != sum(d["completed_dawn"] for d in story["history"]):
                        checks["completed_day_mismatch"] += 1
                    for d in story["history"]:
                        if d["completed_dawn"]:
                            if (abs(d["minutes_accounted"] - 1440) > .001
                                    or d["next_dawn_minute"] is None):
                                checks["full_day_clock"] += 1
                        else:
                            if (d["next_dawn_minute"] is not None
                                    or not d["end_reason"]
                                    or d["minutes_accounted"] >= 1440):
                                checks["partial_day_clock"] += 1
                        if d["fuel_next_dawn"] > (
                            d["fuel_at_dawn"] + d["fuel_delivered"] +
                            4 * (d["furniture_at_dawn"] - d["furniture_next_dawn"]) +
                            .001
                        ):
                            checks["free_fuel"] += 1
                        if any(n < 0 for n in d["remaining_loot"].values()):
                            checks["negative_loot"] += 1
                        if any(v > initial_stock.loot[node]
                               for node, v in d["remaining_loot"].items()):
                            checks["loot_respawn"] += 1
                        for e in d["early_ignitions"]:
                            if (story["terminal_at_minute"] is not None and
                                    e["elapsed_minute"] > story["terminal_at_minute"]):
                                checks["ignition_after_terminal"] += 1
                if seed == 1:
                    exemplars[f"{variant}/{profile}"] = {
                        policy: {
                            "elapsed_hours": round(story["elapsed_minutes"] / 60, 3),
                            "end_reason": story["end_reason"],
                            "first_phase": story["history"][-1]["phase_at_end"],
                            "fire_events": [
                                e for d in story["history"] for e in d["early_ignitions"]
                            ],
                            "first_day": {
                                k: story["history"][0][k] for k in
                                ("minutes_accounted", "completed_dawn",
                                 "core_next_dawn", "fuel_next_dawn",
                                 "return_minute", "phase_at_end")
                            },
                        } for policy, story in all_runs[key].items()
                    }

    for variant in VARIANTS:
        groups[variant] = {}
        for policy in HEATING_POLICIES:
            selected = [
                arm[policy] for (v, profile, seed), arm in all_runs.items()
                if v == variant
            ]
            paired = [
                (arm["dusk"], arm[policy])
                for (v, profile, seed), arm in all_runs.items() if v == variant
            ]
            phase_counts = Counter(r["history"][-1]["phase_at_end"] for r in selected)
            groups[variant][policy] = {
                "runs": len(selected),
                "mean_elapsed_hours": _mean(r["elapsed_minutes"] / 60 for r in selected),
                "mean_completed_dawns": _mean(r["days_completed"] for r in selected),
                "mean_ignition_events_before_evening": _mean(
                    sum(len(d["early_ignitions"]) for d in r["history"])
                    for r in selected
                ),
                "mean_fuel_delivered": _mean(
                    sum(d["fuel_delivered"] for d in r["history"])
                    for r in selected
                ),
                "mean_final_fuel": _mean(r["history"][-1]["fuel_next_dawn"] for r in selected),
                "mean_unused_world_loot": _mean(
                    sum(r["history"][-1]["remaining_loot"].values()) for r in selected
                ),
                "end_causes": dict(sorted(Counter(r["end_reason"] or "horizon"
                                                 for r in selected).items())),
                "stop_phases": dict(sorted(phase_counts.items())),
                "paired_time_change": {
                    "longer": sum(a["elapsed_minutes"] > b["elapsed_minutes"] + .001
                                  for b,a in paired),
                    "shorter": sum(a["elapsed_minutes"] < b["elapsed_minutes"] - .001
                                   for b,a in paired),
                    "same": sum(abs(a["elapsed_minutes"]-b["elapsed_minutes"]) <= .001
                                for b,a in paired),
                    "mean_delta_h": _mean(
                        (a["elapsed_minutes"] - b["elapsed_minutes"]) / 60
                        for b,a in paired
                    ),
                },
            }
    return {
        "design": {
            "cases_per_policy": len(all_runs),
            "policies": HEATING_POLICIES,
            "horizon_days": days,
            "paired_weather": "(variant, profile, seed, day), same true weather",
            "random_loot": "sequential draws may diverge after altered actions",
            "the_only_change": "fire ignition moment; finite loot and real fuel cost retained",
        },
        "groups": groups,
        "checks": {name: checks[name] for name in (
            "weather_mismatch", "terminal_clock_mismatch", "completed_day_mismatch",
            "full_day_clock", "partial_day_clock", "free_fuel",
            "negative_loot", "loot_respawn", "ignition_after_terminal"
        )},
        "seed_1_traces": exemplars,
        "limitations": [
            "Policies are experimental player behaviours, not an optimized decision algorithm.",
            "An early fire can burn while the player is away: this is a genuine cost.",
            "End-of-horizon runs are censored; mean elapsed hours is capped, not expected lifetime.",
            "The terminal threshold and heat constants are prototype rules, not physiological facts.",
            "No UE runtime or subjective player enjoyment is measured.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()
    r = experiment(args.seeds, args.days)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    for variant, rows in r["groups"].items():
        print(f"{variant}:")
        for policy, x in rows.items():
            print(f"  {policy}: {x['mean_elapsed_hours']} h, "
                  f"paired {x['paired_time_change']}, "
                  f"ignitions={x['mean_ignition_events_before_evening']}, "
                  f"fuel_delivered={x['mean_fuel_delivered']}")
    print("Checks:", r["checks"])


if __name__ == "__main__":
    main()
