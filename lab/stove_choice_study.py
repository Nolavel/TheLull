"""Paired experiment: agent-initiated stove decisions vs scripted and forced choices.

No balancing or oracle. Real survival times are capped at the requested horizon;
human intent / understanding requires a separate human session.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from statistics import mean

from .heat_choice import LIGHT, SAVE
from .ignition_timing_study import VARIANTS, PROFILES
from .survival_loop import HEATING_POLICIES, run
from .world import World

ARMS = (*HEATING_POLICIES, "agent", "forced_light", "forced_save")


def measure(seeds: int = 30, days: int = 7) -> dict:
    if not 1 <= seeds <= 100 or not 1 <= days <= 30:
        raise ValueError("seeds must be in 1..100 and days in 1..30")
    cases = {}
    invalid = Counter()
    for variant in VARIANTS:
        original_world = World.load("district_v0", variant)
        for profile in PROFILES:
            for seed in range(1, seeds + 1):
                key = (variant, profile, seed)
                results = {}
                for arm in ARMS:
                    if arm.startswith("forced_"):
                        forced = "light" if arm == "forced_light" else "save"
                        x = run(seed, days, variant=variant, profile=profile,
                                heating_policy="agent",
                                decision_provider=lambda _: forced)
                    else:
                        x = run(seed, days, variant=variant, profile=profile,
                                heating_policy=arm)
                    results[arm] = x
                    if x["terminal_at_minute"] is not None:
                        if abs(x["terminal_at_minute"] - x["elapsed_minutes"]) > 0.002:
                            invalid["terminal_clock"] += 1
                    if x["days_completed"] != sum(d["completed_dawn"] for d in x["history"]):
                        invalid["completed_day"] += 1
                    for d in x["history"]:
                        if d["completed_dawn"]:
                            if abs(d["minutes_accounted"] - 1440) > .002:
                                invalid["complete_day_clock"] += 1
                        elif not d["end_reason"] or d["next_dawn_minute"] is not None:
                            invalid["partial_day_clock"] += 1
                        if d["fuel_next_dawn"] > (d["fuel_at_dawn"] + d["fuel_delivered"]
                            + 4 * (d["furniture_at_dawn"] - d["furniture_next_dawn"]) + .002):
                            invalid["free_fuel"] += 1
                        if min(d["remaining_loot"].values()) < 0:
                            invalid["negative_loot"] += 1
                        if any(v > original_world.loot[node] for node,v in d["remaining_loot"].items()):
                            invalid["respawn"] += 1
                        if len(d["stove_decisions"]) != len(d["stove_outcomes"]):
                            invalid["unpaired_decisions"] += 1
                        for decision in d["stove_decisions"]:
                            if {o["option"] for o in decision["alternatives"]} != {LIGHT, SAVE}:
                                invalid["lost_alternative"] += 1
                            if not decision["reason"] or not decision["outcome"]:
                                invalid["unexplained_decision"] += 1
                        for event in d["early_ignitions"]:
                            if x["terminal_at_minute"] is not None and (
                                event["elapsed_minute"] > x["terminal_at_minute"] + .01
                            ):
                                invalid["post_terminal_ignition"] += 1
                for k, candidate in results.items():
                    for baseline_day, candidate_day in zip(results["dusk"]["history"],
                                                          candidate["history"]):
                        if baseline_day["world_weather"] != candidate_day["world_weather"]:
                            invalid["weather_divergence"] += 1
                cases[key] = results

    report = {}
    for variant in VARIANTS:
        report[variant] = {}
        for arm in ARMS:
            rows = [v[arm] for (vname,_,_),v in cases.items() if vname == variant]
            pair = [(v["dusk"],v[arm]) for (vname,_,_),v in cases.items()
                    if vname == variant]
            decisions = [d for r in rows for day in r["history"]
                         for d in day["stove_decisions"]]
            outcomes = [o for r in rows for day in r["history"]
                        for o in day["stove_outcomes"]]
            choice_counts = Counter(d["choice"] for d in decisions)
            phase_counts = Counter(d["point"] for d in decisions)
            total_fuel = [
                sum(d["fuel_burned_today"] for d in r["history"]) for r in rows
            ]
            report[variant][arm] = {
                "runs": len(rows),
                "mean_capped_elapsed_h": round(mean(r["elapsed_minutes"]/60 for r in rows),3),
                "mean_completed_dawns": round(mean(r["days_completed"] for r in rows),3),
                "mean_fuel_burned": round(mean(total_fuel),3),
                "mean_fuel_remaining": round(
                    mean(r["history"][-1]["fuel_next_dawn"] for r in rows),3),
                "mean_world_loot_remaining": round(
                    mean(sum(r["history"][-1]["remaining_loot"].values()) for r in rows),3),
                "end_causes": dict(Counter(r["end_reason"] or "horizon" for r in rows)),
                "decisions": len(decisions),
                "choices": dict(choice_counts),
                "choice_points": dict(phase_counts),
                "mean_realized_fuel_per_decision": (
                    round(mean(o["realized_fuel_burned"] for o in outcomes),3)
                    if outcomes else None
                ),
                "mean_realized_heat_h_per_decision": (
                    round(mean(o["realized_fire_hours"] for o in outcomes),3)
                    if outcomes else None
                ),
                "paired_to_dusk": {
                    "longer": sum(b["elapsed_minutes"] > a["elapsed_minutes"] + .001
                                  for a,b in pair),
                    "shorter": sum(b["elapsed_minutes"] < a["elapsed_minutes"] - .001
                                   for a,b in pair),
                    "same": sum(abs(b["elapsed_minutes"] - a["elapsed_minutes"]) <= .001
                                for a,b in pair),
                    "mean_delta_h": round(mean(
                        (b["elapsed_minutes"] - a["elapsed_minutes"]) / 60
                        for a,b in pair
                    ),3)
                },
            }
    return {
        "design": {
            "seeds": seeds, "days": days, "paired_cases_per_arm": len(cases),
            "arms": ARMS, "fixed_weather": "seed+day, shared across alternatives",
            "deliberation": "only current shelter/body, agent beliefs, known plan/time",
            "human_participant_count": 0,
        },
        "groups": report,
        "checks": {k:invalid[k] for k in (
            "terminal_clock", "completed_day", "complete_day_clock",
            "partial_day_clock", "free_fuel", "negative_loot", "respawn",
            "unpaired_decisions", "lost_alternative", "unexplained_decision",
            "post_terminal_ignition", "weather_divergence"
        )},
        "sample_agent_decisions": {
            f"{v}/{p}": [
                {"point": d["point"],"time":d["time"],"cues":d["cues"],
                 "alternatives": d["alternatives"],"choice": d["choice"],
                 "reason": d["reason"], "outcome": d["outcome"],
                 "belief_update": d["belief_update"]}
                for day in cases[(v,p,1)]["agent"]["history"]
                for d in day["stove_decisions"]
            ][:8] for v in VARIANTS for p in PROFILES
        },
        "limits": [
            "An engineered agent is not a human. No fun or meaningfulness claim.",
            "Forced-light and forced-save are scripted controls, not human responses.",
            "The next-day route and the evening work choice remain an automated policy.",
            "The nightly emergency furniture work remains automated.",
            "Changes to action sequence can shift subsequent loot RNG draws.",
            "Censored 7-day horizon: do not present mean capped hours as lifespan.",
            "The belief utility is an experimental heuristic, not a calibrated model.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()
    r = measure(args.seeds, args.days)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    for variant, arms in r["groups"].items():
        print(variant)
        for arm, row in arms.items():
            print(f"  {arm}: {row['mean_capped_elapsed_h']}h, "
                  f"choice={row['choices']}, fuel={row['mean_fuel_burned']}, "
                  f"delta={row['paired_to_dusk']}")
    print("Checks:",r["checks"])


if __name__ == "__main__":
    main()
