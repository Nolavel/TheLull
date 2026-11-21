"""Falsification-oriented diagnosis of a uniform endpoint in the canonical loop.

Read-only interventions around survival_loop.run. No change to player rules,
state persistence, original seed/day weather, or finite-loot respawn. Each arm
changes ONE factor relative to a same-seed, same-variant, same-profile baseline.

This is evidence about a deterministic toy model, NOT survival balance.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

from . import evening, survival_loop
from .body import COMFORT_C, COOLING_COEF, effective_c, Body
from .world import World

# Pre-register all interventions here. Do not select arms after observing data.
ARMS = {
    "baseline": {},
    "air_plus_6c": {"air_delta_c": 6.0},
    "finite_start_fuel_plus_6": {"extra_start_fuel": 6},
    "fuel_burn_half": {"burn_multiplier": 0.5},
    "force_rest_B": {"policy": "B"},
}
VARIANTS = ("A_safe", "B_readable", "C_unreadable")
PROFILES = ("novice", "local")
HORIZON = 7


def simulate(seed: int, variant: str, profile: str, arm: str = "baseline",
             days: int = HORIZON, choice_trace: list | None = None) -> dict:
    """All patches are scoped to one invocation. The actual world is reloaded."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    params = ARMS[arm]
    original_load = World.load.__func__
    original_choose = survival_loop.choose
    original_burn = evening.FUEL_BURN_PER_H

    def changed_world(cls, name: str, v: str):
        w = original_load(cls, name, v)
        w.air_temp_c += params.get("air_delta_c", 0.0)
        w.start_fuel += params.get("extra_start_fuel", 0)
        return w

    def instrumented_choice(body, room, beliefs, tomorrow, outside_c, *,
                            daylight_hours, night_hours):
        pick, why, revised = original_choose(
            body, room, beliefs, tomorrow, outside_c,
            daylight_hours=daylight_hours, night_hours=night_hours
        )
        if choice_trace is not None:
            alternatives = []
            for op in evening.options(
                body, room, beliefs, tomorrow, outside_c,
                daylight_hours=daylight_hours, night_hours=night_hours
            ):
                if not op["available"]:
                    continue
                if op["option"].startswith("D:") and not op["ready_for_tomorrow_expected"]:
                    # Same candidate filter as the actual planner.
                    continue
                # The next block is auditor-only: it knows actual room parameters.
                # Copies prevent oracle outcomes from becoming agent knowledge.
                true_outcome = survival_loop.play(
                    op["option"], outside_c, deepcopy(room),
                    deepcopy(body), deepcopy(beliefs),
                    hours_of_night=night_hours
                )
                alternatives.append({
                    "action": op["option"][0],
                    "core_next_c": true_outcome["morning_core_c"],
                    "wake_events": true_outcome["woke_cold"],
                    "fatigue_next": true_outcome["morning_fatigue"],
                    "fuel_left": true_outcome["fuel_left"],
                    "available_by_policy": True,
                })
            chosen = pick["option"][0]
            chosen_effect = next((x for x in alternatives if x["action"] == chosen), None)
            # This is NOT "regret" against overall utility; core temperature
            # ignores material conservation, travel and future options.
            higher_core = bool(chosen_effect and any(
                x["core_next_c"] > chosen_effect["core_next_c"] + 0.5
                for x in alternatives if x["action"] != chosen
            ))
            choice_trace.append({
                "day_index": len(choice_trace) + 1,
                "chosen": chosen,
                "core_before": round(body.core_c, 4),
                "fuel_before": round(room.fuel, 4),
                "furniture_before": room.furniture,
                "night_hours": round(night_hours, 3),
                "alternatives": alternatives,
                "other_option_gives_0_5c_more": higher_core,
            })
        if params.get("policy") == "B":
            opt = next(o for o in evening.options(
                body, room, beliefs, tomorrow, outside_c,
                daylight_hours=daylight_hours, night_hours=night_hours
            ) if o["option"].startswith("B:"))
            return opt, "контрольная абляция: без вечерней работы", tomorrow
        return pick, why, revised

    with ExitStack() as stack:
        stack.enter_context(patch.object(World, "load", classmethod(changed_world)))
        if "burn_multiplier" in params:
            stack.enter_context(patch.object(
                evening, "FUEL_BURN_PER_H",
                original_burn * params["burn_multiplier"]
            ))
        if choice_trace is not None or params.get("policy"):
            stack.enter_context(patch.object(
                survival_loop, "choose", instrumented_choice
            ))
        return survival_loop.run(seed, days, variant=variant, profile=profile)


def _description_of_unheated_room() -> dict:
    """Trace the model's own unheated thermal load, not a real-world estimate."""
    ans = {}
    for variant in VARIANTS:
        world = World.load("district_v0", variant)
        unheated_effective = effective_c(world.air_temp_c + evening.PASSIVE_OFFSET_C)
        hourly_loss = max(0.0, COMFORT_C - unheated_effective) * COOLING_COEF
        ans[variant] = {
            "air_c": world.air_temp_c,
            "effective_no_fire_c": round(unheated_effective, 3),
            "unheated_core_loss_c_per_h": round(hourly_loss, 4),
            "unheated_14h_loss_c": round(hourly_loss * world.night_hours, 3),
            "world_nominal_fuel_per_night": world.fuel_per_night,
            "world_night_hours": world.night_hours,
            "fuel_burn_per_h": evening.FUEL_BURN_PER_H,
            "nominal_fuel_hours": world.fuel_per_night / evening.FUEL_BURN_PER_H,
        }
    return ans


def analyze(seeds: int = 30, days: int = HORIZON) -> dict:
    if not (1 <= seeds <= 200) or not (1 <= days <= 30):
        raise ValueError("choose 1..200 paired seeds and 1..30 days")
    grid = [(v, p, i) for v in VARIANTS for p in PROFILES
            for i in range(1, seeds + 1)]
    original_burn = evening.FUEL_BURN_PER_H

    results = {}
    for variant, profile, seed in grid:
        key = (variant, profile, seed)
        results[key] = {arm: simulate(seed, variant, profile, arm, days)
                        for arm in ARMS}
    assert evening.FUEL_BURN_PER_H == original_burn, "patch leaked into the model"

    # The world-weather baseline and all interventions use the same seed/day.
    weather_mismatches = 0
    loot_mismatches_at_first_trip = 0
    per_arm = {}
    for arm in ARMS:
        endings = Counter()
        completed = []
        choices = Counter()
        colder_next_dawn = []
        fuel_next_dawn = []
        first_day_cores = []
        relative_days = Counter()
        weather_pairs = 0
        for key, cases in results.items():
            baseline = cases["baseline"]
            changed = cases[arm]
            completed.append(changed["days_completed"])
            endings[changed["end_reason"] or "horizon"] += 1
            relative_days[changed["days_completed"] - baseline["days_completed"]] += 1
            choices.update(d["evening"]["chose"][0] for d in changed["history"])
            if changed["history"]:
                first_day_cores.append(changed["history"][0]["core_next_dawn"])
                fuel_next_dawn.append(changed["history"][0]["fuel_next_dawn"])
            for d0, d1 in zip(baseline["history"], changed["history"]):
                weather_pairs += 1
                if d0["world_weather"] != d1["world_weather"]:
                    weather_mismatches += 1
        per_arm[arm] = {
            "runs": len(completed),
            "mean_completed_days": round(statistics.mean(completed), 3),
            "mean_core_after_day1_c": round(statistics.mean(first_day_cores), 3),
            "mean_fuel_after_day1": round(statistics.mean(fuel_next_dawn), 3),
            "end_reasons": dict(sorted(endings.items())),
            "evening_choices": dict(sorted(choices.items())),
            "paired_days_difference": dict(sorted(relative_days.items())),
            "paired_weather_days_compared": weather_pairs,
        }

    traces = []
    # Observe real alternatives from a copy of an *unchanged* evening state.
    for variant, profile, seed in grid:
        individual = []
        simulate(seed, variant, profile, "baseline", days,
                 choice_trace=individual)
        for row in individual:
            row.update({"variant": variant, "profile": profile, "seed": seed})
        traces.extend(individual)

    by_action = Counter()
    alt_counts = Counter()
    no_fire = 0
    higher_core_any = 0
    first_evening = []
    for row in traces:
        by_action[row["chosen"]] += 1
        alt_counts[len(row["alternatives"])] += 1
        no_fire += row["fuel_before"] <= 0
        higher_core_any += row["other_option_gives_0_5c_more"]
        if row["day_index"] == 1:
            first_evening.append(row)
    return {
        "design": {
            "type": "paired one-factor counterfactual ablations",
            "unit": "(world variant, agent profile, seed)",
            "horizon_days": days, "seeds_per_cell": seeds,
            "cases_per_arm": len(grid),
            "arms_pre_registered": ARMS,
            "rules_untouched": "survival_loop, choose, body, resource conservation",
            "comparison": "same seed/day weather; loot RNG may diverge after actions differ",
        },
        "thermal_exposure": _description_of_unheated_room(),
        "arms": per_arm,
        "counterfactual_evening": {
            "observed_evenings": len(traces),
            "chosen": dict(sorted(by_action.items())),
            "number_of_available_choices": dict(sorted(alt_counts.items())),
            "evenings_without_fuel": no_fire,
            "evenings_with_alternative_raising_core_by_half_degree": higher_core_any,
            "first_evening_examples": first_evening[:6],
        },
        "checks": {
            "weather_mismatches_across_paired_cases": weather_mismatches,
            "burn_constant_restored": evening.FUEL_BURN_PER_H == original_burn,
        },
        "limits": [
            "Thresholded day count masks secondary differences in body core/fuel.",
            "Thermal alternatives compare only morning core: not globally superior decisions.",
            "Finite +6 starting fuel does not represent renewable fuel.",
            "Changing the evening policy can change visits and sequence-based loot RNG.",
            "Weather is paired and unchanged; loot sequence can diverge after choices differ.",
            "No human satisfaction, TLD formula, or Unreal runtime is measured.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", required=True)
    args = ap.parse_args()
    result = analyze(args.seeds, args.days)
    with open(args.json, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print("Paired experiment:", result["design"])
    print("Thermal exposure:", result["thermal_exposure"])
    for arm, row in result["arms"].items():
        print(f"{arm}: days={row['mean_completed_days']}, "
              f"first_morning_core={row['mean_core_after_day1_c']}C, "
              f"endings={row['end_reasons']}, changes={row['paired_days_difference']}")
    print("Paired weather mismatches:", result["checks"]["weather_mismatches_across_paired_cases"])
    print("True alternative actions:", {
        k: v for k, v in result["counterfactual_evening"].items()
        if k != "first_evening_examples"
    })


if __name__ == "__main__":
    main()
