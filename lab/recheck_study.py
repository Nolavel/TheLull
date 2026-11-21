"""Registered paired intervention: belief zero versus observed zero in the SAME world.

The control explicitly disables rechecking. The treatment only allows one
30-minute recheck in a building whose estimate hit zero, but which has not
actually been observed empty. No added loot, weather changes, or fuel tuning.

Authoritative outcomes are the identical simulation, not an oracle agent.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict

from .survival_loop import run
from .world import World

VARIANTS = ("A_safe", "B_readable", "C_unreadable")
PROFILES = ("novice", "local")


def _readout(story: dict) -> dict:
    h = story["history"]
    last = h[-1] if h else None
    uncollected = sum(last["remaining_loot"].values()) if last else 0
    estimated = last["beliefs_after"]["estimated_loot"] if last else {}
    empty = last["beliefs_after"]["confirmed_empty"] if last else []
    return {
        "days": story["days_completed"], "reason": story["end_reason"] or "horizon",
        "fuel_found": sum(d["carried"] for d in h),
        "trips": sum(int(d["day_trip"]["went_out"]) for d in h),
        "search_minutes": sum(d["day_trip"]["search_minutes"] for d in h),
        "recheck_chunks": sum(d["day_trip"]["recheck_searches"] for d in h),
        "empty_observations": sum(d["day_trip"]["empty_searches"] for d in h),
        "unused_world_loot": uncollected,
        "unobserved_but_estimated_zero": sum(
            estimated.get(node, 0) <= 0 and node not in empty
            and remaining > 0
            for node, remaining in (last["remaining_loot"].items() if last else [])
        ),
        "no_trip_last_day_with_stock": bool(
            last and not last["day_trip"]["went_out"] and uncollected > 0
        ),
        "core_next_dawn": last["core_next_dawn"] if last else None,
    }


def _average(rows, key):
    return round(statistics.mean(r[key] for r in rows), 3)


def study(seeds: int = 30, days: int = 7) -> dict:
    if seeds < 1 or seeds > 200 or days < 1 or days > 30:
        raise ValueError("1..200 seeds and 1..30 days")
    samples = defaultdict(lambda: {"control": [], "recheck": [], "pairwise": []})
    weather_mismatch = 0
    conservation_failures = 0
    empty_oracle_violations = 0
    single_visit_excess = 0

    for variant in VARIANTS:
        for profile in PROFILES:
            label = f"{variant}/{profile}"
            for seed in range(1, seeds + 1):
                control = run(seed, days, variant=variant, profile=profile,
                              recheck_policy=False)
                changed = run(seed, days, variant=variant, profile=profile,
                              recheck_policy=True)
                # Compare only shared realized days; different run lengths
                # are a legitimate gameplay outcome.
                weather_mismatch += sum(
                    a["world_weather"] != b["world_weather"]
                    for a, b in zip(control["history"], changed["history"])
                )
                for story in (control, changed):
                    initial_stock = World.load("district_v0", variant).loot
                    for day in story["history"]:
                        if day["day_trip"]["recheck_searches"] * 30 > day["day_trip"]["search_minutes"]:
                            conservation_failures += 1
                        for node in day["beliefs_after"]["confirmed_empty"]:
                            if day["remaining_loot"].get(node, 0) > 0:
                                empty_oracle_violations += 1
                        if day["day_trip"]["recheck_searches"] > 1:
                            single_visit_excess += 1
                        if (day["fuel_next_dawn"] >
                                day["fuel_at_dawn"] + day["carried"] +
                                4 * (day["furniture_at_dawn"] - day["furniture_next_dawn"]) + 0.01):
                            conservation_failures += 1
                        if any(value > initial_stock.get(node, 0)
                               for node, value in day["remaining_loot"].items()):
                            conservation_failures += 1
                old = _readout(control)
                new = _readout(changed)
                samples[label]["control"].append(old)
                samples[label]["recheck"].append(new)
                samples[label]["pairwise"].append({
                    "seed": seed,
                    "survival_delta_days": new["days"] - old["days"],
                    "found_delta": new["fuel_found"] - old["fuel_found"],
                    "unused_delta": new["unused_world_loot"] - old["unused_world_loot"],
                    "search_delta_minutes": new["search_minutes"] - old["search_minutes"],
                    "recheck_chunks": new["recheck_chunks"],
                })

    stats = {}
    combined = {"control": [], "recheck": [], "pairwise": []}
    for group, data in samples.items():
        result = {}
        for name in ("control", "recheck"):
            rows = data[name]
            combined[name].extend(rows)
            result[name] = {
                "cases": len(rows),
                "mean_days": _average(rows, "days"),
                "end_reasons": dict(sorted(Counter(r["reason"] for r in rows).items())),
                "mean_fuel_found": _average(rows, "fuel_found"),
                "mean_trips": _average(rows, "trips"),
                "mean_search_minutes": _average(rows, "search_minutes"),
                "mean_recheck_chunks": _average(rows, "recheck_chunks"),
                "mean_unused_world_loot": _average(rows, "unused_world_loot"),
                "runs_no_trip_last_day_despite_stock": sum(r["no_trip_last_day_with_stock"] for r in rows),
                "mean_false_zero_unobserved": _average(rows, "unobserved_but_estimated_zero"),
            }
        pair = data["pairwise"]
        combined["pairwise"].extend(pair)
        result["paired"] = {
            "recheck_longer": sum(r["survival_delta_days"] > 0 for r in pair),
            "recheck_shorter": sum(r["survival_delta_days"] < 0 for r in pair),
            "same_days": sum(r["survival_delta_days"] == 0 for r in pair),
            "more_loot_collected": sum(r["found_delta"] > 0 for r in pair),
            "less_loot_collected": sum(r["found_delta"] < 0 for r in pair),
            "same_loot_collected": sum(r["found_delta"] == 0 for r in pair),
        }
        stats[group] = result
    aggregate = {}
    for name in ("control", "recheck"):
        rows = combined[name]
        aggregate[name] = {
            "cases": len(rows),
            "mean_days": _average(rows, "days"),
            "end_reasons": dict(sorted(Counter(r["reason"] for r in rows).items())),
            "mean_fuel_found": _average(rows, "fuel_found"),
            "mean_unused_world_loot": _average(rows, "unused_world_loot"),
            "mean_recheck_chunks": _average(rows, "recheck_chunks"),
            "mean_search_minutes": _average(rows, "search_minutes"),
            "no_trip_last_day_despite_stock": sum(r["no_trip_last_day_with_stock"] for r in rows),
            "mean_false_zero_unobserved": _average(rows, "unobserved_but_estimated_zero"),
        }
    deltas = combined["pairwise"]
    aggregate["paired"] = {
        "mean_survival_delta_days": _average(deltas, "survival_delta_days"),
        "mean_fuel_found_delta": _average(deltas, "found_delta"),
        "mean_unused_loot_delta": _average(deltas, "unused_delta"),
        "mean_search_delta_minutes": _average(deltas, "search_delta_minutes"),
        "longer": sum(x["survival_delta_days"] > 0 for x in deltas),
        "shorter": sum(x["survival_delta_days"] < 0 for x in deltas),
        "same_days": sum(x["survival_delta_days"] == 0 for x in deltas),
    }
    return {
        "design": {
            "run_count": len(deltas), "seeds_per_variant_profile": seeds,
            "days_horizon": days,
            "control": "recheck_policy=False, old zero-estimate rules",
            "treatment": "recheck_policy=True, ranked unconfirmed search, costs 30 minutes",
            "constants": "no change to fuel burn, air temperature, weather, real loot",
        },
        "aggregate": aggregate,
        "groups": stats,
        "checks": {
            "same_seed_weather_mismatches": weather_mismatch,
            "resource_conservation_failures": conservation_failures,
            "confirmed_empty_with_remaining_real_stock": empty_oracle_violations,
            "more_than_one_recheck_chunk_in_trip": single_visit_excess,
        },
        "examples": {k: rows["pairwise"][:2] for k, rows in samples.items()},
        "limits": [
            "Weather is paired by seed/day; sequential loot draws can diverge after different actions.",
            "A nonzero world stock ALWAYS yields 1..2 per 30-min search in this toy model.",
            "Therefore one empty search confirms emptiness only under this current search rule.",
            "Longer survival is not a mandatory outcome; no balancing or desired sign is assumed.",
            "Comparative action costs include search/travel/temperature and subsequent effects.",
            "No real human/player experience or UE runtime is simulated.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    report = study(a.seeds, a.days)
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"aggregate": report["aggregate"],
                      "checks": report["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
