"""Pre-registered 2x2: initial wetness x water preparation, same finite district.

Factorial contrast is descriptive. It is NOT an estimate of player enjoyment,
and the candidate agent is not a human substitute.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from statistics import mean

from .body import Body
from .coupled_microloop import CONDITIONS, POLICIES, Equipment, _advance, run
from .evening import Room
from .world import World

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
    # Physical comparison, with ACTION and ROUTE held fixed. The ordinary
    # agent-run 2x2 cannot isolate the effect of gear from different decisions.
    mobility_pairs = []

    for variant in VARIANTS:
        for profile in PROFILES:
            for seed in range(1, seeds + 1):
                block = {}
                world = World.load("district_v0", variant)
                weather = world.roll_weather(random.Random(f"{seed}:weather:1"))
                edge = world.edge("home", "house_a")
                clock = world.dawn_min
                base_travel = world.travel_minutes(edge, clock, weather)
                wind = weather.wind(clock)
                paired = {}
                for wet_factor in (0.0, 1.0):
                    body, room, gear = Body(), Room(fuel=0), Equipment(wetness=wet_factor)
                    costs = {"stamina_demand":0.0,"extra_fatigue":0.0,
                             "walked_h":0.0,"minimum_stamina":body.stamina,
                             "wet_pace_delay_min":0.0}
                    expected = gear.travel_minutes(
                        base_travel, wind=wind, exposure=edge.exposure
                    )
                    used = _advance(
                        body, room, world, gear, expected, at_home=False,
                        weather=weather, exposure=edge.exposure,
                        travelling=True, walking_costs=costs
                    )
                    paired[wet_factor] = {
                        "elapsed_min": used,
                        "stamina": body.stamina,
                        "fatigue": body.fatigue,
                        "core_c": body.core_c,
                        "movement_stability": gear.movement_stability(
                            wind=wind, exposure=edge.exposure
                        ),
                        "stamina_demand": costs["stamina_demand"],
                        "terminal": body.terminal,
                    }
                dry_probe, wet_probe = paired[0.0], paired[1.0]
                mobility_pairs.append({"variant":variant, "profile":profile,
                                       "seed":seed,"dry":dry_probe,"wet":wet_probe})
                if dry_probe["terminal"] or wet_probe["terminal"]:
                    checks["mobility_probe_terminal"] += 1
                if not (
                    dry_probe["elapsed_min"] < wet_probe["elapsed_min"]
                    and dry_probe["stamina"] > wet_probe["stamina"]
                    and dry_probe["fatigue"] < wet_probe["fatigue"]
                    and dry_probe["core_c"] > wet_probe["core_c"]
                    and dry_probe["movement_stability"] > wet_probe["movement_stability"]
                ):
                    checks["mobility_advantage_broken"] += 1
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
                            if dec["choice"] not in valid:
                                checks["invalid_choice"] += 1
                            if len(valid)<2:
                                checks["forced_choice_observations"] += 1
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
            "mean_walk_stamina_demand": avg(r["walking_stamina_demand"] for r in data),
            "mean_minimum_walk_stamina": avg(r["minimum_walking_stamina"] for r in data),
            "mean_stamina_at_dusk": avg(r["stamina_at_dusk"] for r in data),
            "mean_extra_walking_fatigue": avg(r["walking_extra_fatigue"] for r in data),
            "mean_pace_delay_min": avg(r["wet_pace_delay_minutes"] for r in data),
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
    physical_advantages = {}
    for variant in VARIANTS:
        sample = [x for x in mobility_pairs if x["variant"] == variant]
        dry = [x["dry"] for x in sample]
        wet = [x["wet"] for x in sample]
        physical_advantages[variant] = {
            "n_paired": len(sample),
            "same_route": "home→house_a",
            "dry_core_c": avg(x["core_c"] for x in dry),
            "wet_core_c": avg(x["core_c"] for x in wet),
            "dry_stamina_after_walk": avg(x["stamina"] for x in dry),
            "wet_stamina_after_walk": avg(x["stamina"] for x in wet),
            "dry_fatigue_after_walk": avg(x["fatigue"] for x in dry),
            "wet_fatigue_after_walk": avg(x["fatigue"] for x in wet),
            "dry_travel_min": avg(x["elapsed_min"] for x in dry),
            "wet_travel_min": avg(x["elapsed_min"] for x in wet),
            "dry_pace_stability": avg(x["movement_stability"] for x in dry),
            "wet_pace_stability": avg(x["movement_stability"] for x in wet),
            "stamina_saved_by_dry": avg(
                x["wet"]["stamina_demand"] - x["dry"]["stamina_demand"]
                for x in sample
            ),
        }
    return {
        "physical_advantages_same_route": physical_advantages,
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
        "observations":{"forced_choice_observations":checks["forced_choice_observations"]},
        "checks":{name:checks[name] for name in (
            "weather_not_paired","loot_conservation",
            "deposited_more_than_found","negative_fuel","free_fuel",
            "water_conservation","invalid_wetness","clock_bounds",
            "terminal_clock","fabricated_dawn","invalid_choice",
            "missing_decision_observation","mobility_probe_terminal",
            "mobility_advantage_broken"
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
            "The fixed route probes directly compare dry/wet core, stamina and travel time under identical seed/weather/actions.",
            "Travel pace stability is a small deterministic time proxy; no animation, slips or UE controller simulated.",
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
                      "physical_advantages_same_route":result["physical_advantages_same_route"],
                      "interactions":result["factorial_interactions"],
                      "checks":result["checks"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
