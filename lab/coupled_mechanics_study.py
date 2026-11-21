"""Pre-registered 2x2: initial wetness x water preparation, same finite district.

Factorial contrast is descriptive. It is NOT an estimate of player enjoyment,
and the candidate agent is not a human substitute.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from statistics import mean

from .coupled_microloop import CONDITIONS, POLICIES, run

VARIANTS = ("A_safe", "B_readable", "C_unreadable")
PROFILES = ("novice", "local")


def avg(values) -> float:
    return round(mean(values), 4) if values else 0.0


def study(seeds: int = 30) -> dict:
    if not 1 <= seeds <= 150:
        raise ValueError("1..150 seeds")
    grouped = defaultdict(list)
    checks = Counter()
    matched = {}

    for variant in VARIANTS:
        for profile in PROFILES:
            for seed in range(1, seeds + 1):
                block = {}
                for wet, water in CONDITIONS:
                    for policy in POLICIES:
                        result = run(seed, variant, profile, wet=wet,
                                     need_water=water, policy=policy)
                        block[(wet,water,policy)] = result
                        grouped[(variant, wet, water, policy)].append(result)
                        if result["weather"] != block.get((False,False,"agent"), result)["weather"]:
                            checks["weather_not_paired"] += 1
                        if result["loot_before"]-result["loot_after"] != result["found"]:
                            checks["loot_conservation"] += 1
                        if result["delivered"] > result["found"]:
                            checks["deposited_more_than_found"] += 1
                        if result["fuel_final"] < -1e-8:
                            checks["negative_fuel"] += 1
                        if (result["fuel_final"] + result["fuel_burned"]
                            > result["initial_fuel"] + result["delivered"] + 1e-3):
                            checks["free_fuel"] += 1
                        if result["raw_water_left"]+result["safe_water_final"] != int(water):
                            checks["water_conservation"] += 1
                        if not 0 <= result["wet_final"] <= int(wet):
                            checks["invalid_wetness"] += 1
                        if result["elapsed_minutes"] > 1440.0001 or result["elapsed_minutes"] <= 0:
                            checks["clock_bounds"] += 1
                        if result["terminal_at_minute"] is not None:
                            if abs(result["terminal_at_minute"]-result["elapsed_minutes"]) > .001:
                                checks["terminal_clock"] += 1
                        if result["completed_dawn"] != (
                            result["terminal_at_minute"] is None
                            and abs(result["elapsed_minutes"]-1440)<1e-5
                        ):
                            checks["fabricated_dawn"] += 1
                        for dec in result["decisions"]:
                            valid = {x["option"] for x in dec["alternatives"] if x["available"]}
                            if dec["choice"] not in valid or len(valid)<2:
                                checks["no_real_alternatives"] += 1
                            if not dec["reason"] or not dec["outcome"]:
                                checks["missing_decision_observation"] += 1
                matched[(variant,profile,seed)] = block

    rows = {}
    for (variant,wet,water,policy), data in grouped.items():
        key = f"wet={int(wet)}/water={int(water)}"
        if variant not in rows:
            rows[variant] = {}
        if key not in rows[variant]:
            rows[variant][key] = {}
        decisions = [d for r in data for d in r["decisions"]]
        rows[variant][key][policy] = {
            "runs":len(data),
            "mean_elapsed_h":avg(r["elapsed_minutes"]/60 for r in data),
            "reached_dawn":sum(r["completed_dawn"] for r in data),
            "mean_fuel_burned":avg(r["fuel_burned"] for r in data),
            "mean_fuel_at_end":avg(r["fuel_final"] for r in data),
            "mean_wetness_at_dusk":avg(r["wet_at_dusk"] for r in data),
            "water_prepared":sum(r["safe_water_final"]>0 for r in data),
            "mean_core_at_dusk":avg(r["core_at_dusk"] for r in data),
            "decisions":len(decisions),
            "choices":dict(sorted(Counter(d["choice"] for d in decisions).items())),
            "next_intentions":dict(sorted(Counter(r["next_intention_rule_based"]
                                               for r in data).items())),
            "end_reasons":dict(sorted(Counter(r["end_reason"] or "horizon"
                                             for r in data).items())),
        }

    interactions = {}
    # 2x2 difference in differences: (both - water_only) -
    # (wet_only - neither). This is NOT an affect/fun metric.
    for variant in VARIANTS:
        interactions[variant] = {}
        for policy in POLICIES:
            cells = [rows[variant][f"wet={int(w)}/water={int(q)}"][policy]
                     for w,q in CONDITIONS]
            interactions[variant][policy] = {
                "elapsed_h_did":round(
                    cells[3]["mean_elapsed_h"]-cells[2]["mean_elapsed_h"]-
                    cells[1]["mean_elapsed_h"]+cells[0]["mean_elapsed_h"],4),
                "fuel_burned_did":round(
                    cells[3]["mean_fuel_burned"]-cells[2]["mean_fuel_burned"]-
                    cells[1]["mean_fuel_burned"]+cells[0]["mean_fuel_burned"],4),
                "core_at_dusk_did":round(
                    cells[3]["mean_core_at_dusk"]-cells[2]["mean_core_at_dusk"]-
                    cells[1]["mean_core_at_dusk"]+cells[0]["mean_core_at_dusk"],4),
            }
    return {
        "design": {
            "blocks":len(matched),"runs":sum(len(v) for v in grouped.values()),
            "variants":VARIANTS,"profiles":PROFILES,"seeds_per_profile":seeds,
            "conditions":[{"wet":w,"need_water":q} for w,q in CONDITIONS],
            "policies":POLICIES,
            "source":"simulated_agent / scripted_control; human participants=0",
            "constant":"seed/day weather; start fuel/loot; same Body/Room/World integrator",
        },
        "groups":rows,
        "factorial_interactions":interactions,
        "checks":{name:checks[name] for name in (
            "weather_not_paired","loot_conservation",
            "deposited_more_than_found","negative_fuel","free_fuel",
            "water_conservation","invalid_wetness","clock_bounds",
            "terminal_clock","fabricated_dawn","no_real_alternatives",
            "missing_decision_observation"
        )},
        "examples":{
            f"{v}/{p}/seed1": [
                {"condition":{"wet":w,"water":q},"policy":policy,
                 "choices":[d["choice"] for d in matched[(v,p,1)][(w,q,policy)]["decisions"]],
                 "next_intention":matched[(v,p,1)][(w,q,policy)]["next_intention_rule_based"]}
                for w,q in CONDITIONS for policy in ("agent","explore_first")
            ] for v in VARIANTS for p in PROFILES
        },
        "limits":[
            "A distinct dawn-to-dawn controlled greybox, NOT survival_loop.run day integration.",
            "One known search point and predetermined 60-min search, no human route choice.",
            "Prepared water creates a future goal only; no thirst meter or dehydration outcome.",
            "Wetness is initialized by scenario, not generated from storms.",
            "The fireplace has assumed available ignition; matches are NOT yet implemented.",
            "All numerical coefficients are provisional and not calibrated.",
            "Factorial contrasts of agent behavior do not measure fun or authentic human intent.",
            "Horizon is one dawn; successful runs are right-censored at 24h.",
        ],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seeds",type=int,default=30)
    ap.add_argument("--json",required=True)
    a=ap.parse_args()
    result=study(a.seeds)
    with open(a.json,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({"design":result["design"],
                      "interactions":result["factorial_interactions"],
                      "checks":result["checks"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
