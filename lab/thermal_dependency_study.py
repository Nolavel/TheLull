"""What dominates B/C survival: outdoor exposure, shelter, fire, night window, or body response?

Controlled, reproducible *diagnostics*, not changes to gameplay balance.
Each arm is independently compared with the unmodified canonical survival_loop
at the SAME (variant, profile, seed). The dusk arm is explicitly a coupled
calendar change, not advertised as an isolated night-duration intervention.

Instrumentation tracks ONLY the one actual Body/Room; shadow-forecast runs
must not appear in the thermal ledger. No oracle information reaches the agent.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from contextlib import ExitStack
from statistics import mean
from unittest.mock import patch

from . import body as physiology
from . import evening, evening_run, sim, survival_loop
from .world import World

VARIANTS = ("A_safe", "B_readable", "C_unreadable")
PROFILES = ("novice", "local")
ARMS = (
    "baseline",
    "day_outdoor_air_plus_6c",
    "night_only_air_plus_6c",
    "shelter_passive_plus_6c",
    "fire_heat_source_plus_6c",
    "fuel_burn_half",
    "body_cooling_half",
    "dusk_two_hours_later",  # day/night boundary changes together
)
PHASES = ("outside_trip", "shelter_day", "night")
HORIZON = 7


def _mean(rows, key):
    return round(mean(row[key] for row in rows), 4)


def simulate(seed: int, variant: str, profile: str, arm: str = "baseline",
             days: int = HORIZON, *, record: bool = True) -> dict:
    """One run, reversible patches and non-invasive state/phase counters."""
    if arm not in ARMS:
        raise ValueError(f"Unknown registered experiment: {arm}")
    original_body_factory = survival_loop.Body
    original_room_factory = survival_loop.Room
    original_step_trip = sim.step_core
    original_step_day = survival_loop.step_body
    original_step_night = evening_run.step_body
    original_room_step = evening.Room.step
    original_choose = survival_loop.choose
    original_play = survival_loop.play
    original_felt = World.felt_outdoors_c
    original_load = World.load.__func__
    tracker = {"body": None, "room": None}
    segments = {p: {"h": 0.0, "lost_c": 0.0, "gained_c": 0.0,
                    "at_temperature_floor_h": 0.0, "burned_fuel": 0.0,
                    "fire_hours": 0.0} for p in PHASES}
    choices = []

    def capture_body(*args, **kwargs):
        x = original_body_factory(*args, **kwargs)
        tracker["body"] = x
        return x

    def capture_room(*args, **kwargs):
        x = original_room_factory(*args, **kwargs)
        tracker["room"] = x
        return x

    def measure(phase, person, old_core, hours):
        if not record or person is not tracker["body"]:
            return
        delta = person.core_c - old_core
        metric = segments[phase]
        metric["h"] += hours
        if delta < 0:
            metric["lost_c"] -= delta
        else:
            metric["gained_c"] += delta
        # Temperature is capped at a floor in this toy model; do not
        # interpret the flat trace as genuine thermal stability.
        if old_core <= physiology.DEATH_C + 1e-7:
            metric["at_temperature_floor_h"] += hours

    def traced_trip(person, felt_c, hours, *args, **kwargs):
        before = person.core_c
        result = original_step_trip(person, felt_c, hours, *args, **kwargs)
        measure("outside_trip", person, before, hours)
        return result

    def traced_day(person, room, outside, hours, asleep, fatigue_per_h=0.0):
        before = person.core_c
        result = original_step_day(person, room, outside, hours, asleep,
                                   fatigue_per_h=fatigue_per_h)
        measure("shelter_day", person, before, hours)
        return result

    def traced_night(person, room, outside, hours, asleep, fatigue_per_h=0.0):
        before = person.core_c
        result = original_step_night(person, room, outside, hours, asleep,
                                     fatigue_per_h=fatigue_per_h)
        measure("night", person, before, hours)
        return result

    # Used only to label fire duration; actual Room.step still owns burn and heat.
    night_playing = {"active": False}
    def traced_room_step(room, hours):
        pre_fuel = room.fuel
        was_lit = room.fire_lit
        result = original_room_step(room, hours)
        if record and room is tracker["room"] and night_playing["active"]:
            consumed = max(0.0, pre_fuel - room.fuel)
            segments["night"]["burned_fuel"] += consumed
            rate = evening.FUEL_BURN_PER_H
            if was_lit and pre_fuel > 0 and rate > 0:
                segments["night"]["fire_hours"] += min(hours, pre_fuel / rate)
        return result

    night_delta = 6.0 if arm == "night_only_air_plus_6c" else 0.0

    def traced_choose(person, room, beliefs, tomorrow, outside_c, *,
                      daylight_hours, night_hours):
        believed_air = outside_c + night_delta
        if record:
            options = evening.options(person, room, beliefs, tomorrow,
                                      believed_air, daylight_hours, night_hours)
            available = [o for o in options if o["available"]]
            viable = [o for o in available
                      if o["core_at_morning_if_uninterrupted"] is not None
                      and o["core_at_morning_if_uninterrupted"] >= physiology.HYPOTHERMIC_C]
            choices.append({
                "available": len(available),
                "forecast_viable": len(viable),
                "predicted_cores": {
                    o["option"][:1]: o["core_at_morning_if_uninterrupted"]
                    for o in available
                },
                "fuel_before": round(room.fuel, 3),
                "core_before": round(person.core_c, 4),
                "night_hours": night_hours,
            })
        return original_choose(person, room, beliefs, tomorrow, believed_air,
                               daylight_hours=daylight_hours,
                               night_hours=night_hours)

    def traced_play(option_label, outside_c, room, person, beliefs, *,
                    hours_of_night):
        night_playing["active"] = True
        try:
            return original_play(option_label, outside_c + night_delta, room,
                                 person, beliefs, hours_of_night=hours_of_night)
        finally:
            night_playing["active"] = False

    def day_air(self, exposure, minute, weather):
        return original_felt(self, exposure, minute, weather) + 6.0

    def dusk_shift(cls, name, chosen_variant):
        world = original_load(cls, name, chosen_variant)
        world.day_length += 120
        return world

    with ExitStack() as stack:
        if record:
            stack.enter_context(patch.object(survival_loop, "Body", capture_body))
            stack.enter_context(patch.object(survival_loop, "Room", capture_room))
            stack.enter_context(patch.object(sim, "step_core", traced_trip))
            stack.enter_context(patch.object(survival_loop, "step_body", traced_day))
            stack.enter_context(patch.object(evening_run, "step_body", traced_night))
            stack.enter_context(patch.object(evening.Room, "step", traced_room_step))
        stack.enter_context(patch.object(survival_loop, "choose", traced_choose))
        stack.enter_context(patch.object(survival_loop, "play", traced_play))
        if arm == "day_outdoor_air_plus_6c":
            stack.enter_context(patch.object(World, "felt_outdoors_c", day_air))
        elif arm == "shelter_passive_plus_6c":
            stack.enter_context(patch.object(
                evening, "PASSIVE_OFFSET_C", evening.PASSIVE_OFFSET_C + 6.0))
        elif arm == "fire_heat_source_plus_6c":
            stack.enter_context(patch.object(
                evening, "HEAT_SOURCE_OFFSET_C", evening.HEAT_SOURCE_OFFSET_C + 6.0))
        elif arm == "fuel_burn_half":
            stack.enter_context(patch.object(
                evening, "FUEL_BURN_PER_H", evening.FUEL_BURN_PER_H / 2.0))
        elif arm == "body_cooling_half":
            stack.enter_context(patch.object(
                physiology, "COOLING_COEF", physiology.COOLING_COEF / 2.0))
        elif arm == "dusk_two_hours_later":
            stack.enter_context(patch.object(World, "load", classmethod(dusk_shift)))
        story = survival_loop.run(seed, days=days, variant=variant,
                                  profile=profile, recheck_policy=True)

    if not record:
        return {"story": story}
    trace = story["history"]
    last = trace[-1] if trace else None
    starting_core = trace[0]["core_at_dawn"] if trace else 37.0
    ending_core = last["core_next_dawn"] if last else starting_core
    measured_core = starting_core + sum(
        x["gained_c"] - x["lost_c"] for x in segments.values()
    )
    observed_delta_error = abs(measured_core - ending_core)
    # The ledger must represent ONLY physical state changes of the actual body.
    if observed_delta_error > 0.001:
        raise AssertionError(f"thermal ledger included a forecast: {observed_delta_error:.6f}C")
    return {
        "days": story["days_completed"],
        "end_reason": story["end_reason"] or "horizon",
        "first_dawn_end_core_c": trace[0]["core_next_dawn"] if trace else None,
        "last_core_c": ending_core,
        "real_fuel_collected": sum(d["carried"] for d in trace),
        "unused_world_stock": sum(last["remaining_loot"].values()) if last else 0,
        "search_minutes": sum(d["day_trip"]["search_minutes"] for d in trace),
        "trip_count": sum(bool(d["day_trip"]["went_out"]) for d in trace),
        "nights": len(trace),
        "sleep_h": sum(d["night"]["slept_hours"] for d in trace),
        "wake_events": sum(d["night"]["woke_cold"] for d in trace),
        "total_fire_out_observations": sum(d["night"]["fire_out_at"] is not None for d in trace),
        "thermal_phases": segments,
        "evening_options": choices,
        "ledger_error": observed_delta_error,
        "weather": [d["world_weather"] for d in trace],
    }


def analyze(seeds: int = 30, days: int = HORIZON) -> dict:
    if not 1 <= seeds <= 150 or not 1 <= days <= 20:
        raise ValueError("Use 1..150 seeds, 1..20 day horizon")
    paired = defaultdict(dict)
    for variant in VARIANTS:
        for profile in PROFILES:
            for seed in range(1, seeds + 1):
                key = (variant, profile, seed)
                for arm in ARMS:
                    paired[key][arm] = simulate(seed, variant, profile, arm, days)

    stats = {}
    for variant in VARIANTS:
        stats[variant] = {}
        for arm in ARMS:
            group = [arms[arm] for (v, profile, seed), arms in paired.items()
                     if v == variant]
            baseline = [(arms["baseline"], arms[arm])
                        for (v, profile, seed), arms in paired.items() if v == variant]
            endings = Counter(x["end_reason"] for x in group)
            changes = Counter(
                "longer" if x["days"] > base["days"] else
                "shorter" if x["days"] < base["days"] else "same"
                for base, x in baseline
            )
            ledger = {}
            for phase in PHASES:
                ledger[phase] = {
                    "mean_hours": _mean(
                        [{"v": x["thermal_phases"][phase]["h"]} for x in group], "v"
                    ),
                    "mean_core_loss_c": _mean(
                        [{"v": x["thermal_phases"][phase]["lost_c"]} for x in group], "v"
                    ),
                    "mean_core_gain_c": _mean(
                        [{"v": x["thermal_phases"][phase]["gained_c"]} for x in group], "v"
                    ),
                    "mean_floor_hours": _mean(
                        [{"v": x["thermal_phases"][phase]["at_temperature_floor_h"]}
                         for x in group], "v"
                    ),
                }
            available = [c for x in group for c in x["evening_options"]]
            stats[variant][arm] = {
                "cases": len(group),
                "mean_days": _mean(group, "days"),
                "mean_first_morning_core_c": _mean(group, "first_dawn_end_core_c"),
                "mean_fuel_found": _mean(group, "real_fuel_collected"),
                "mean_unused_world_stock": _mean(group, "unused_world_stock"),
                "mean_sleep_h": _mean(group, "sleep_h"),
                "mean_wakes": _mean(group, "wake_events"),
                "mean_night_fire_h": round(mean(
                    x["thermal_phases"]["night"]["fire_hours"] for x in group
                ), 4),
                "mean_night_fuel_burned": round(mean(
                    x["thermal_phases"]["night"]["burned_fuel"] for x in group
                ), 4),
                "mean_eligible_actions_per_evening": round(mean(
                    c["available"] for c in available
                ), 4) if available else 0,
                "fraction_evenings_with_two_viable_options": round(
                    sum(c["forecast_viable"] >= 2 for c in available) /
                    len(available), 4
                ) if available else 0,
                "fraction_evenings_with_any_viable_option": round(
                    sum(c["forecast_viable"] >= 1 for c in available) /
                    len(available), 4
                ) if available else 0,
                "end_reasons": dict(sorted(endings.items())),
                "vs_baseline_count": dict(sorted(changes.items())),
                "phases": ledger,
            }
    mismatches = 0
    ledger_violations = 0
    extra_night = 0
    for key, cases in paired.items():
        base = cases["baseline"]
        for name, x in cases.items():
            mismatch_days = sum(
                # Storm truth is invariant across all cases even when a
                # later dusk legitimately shifts the *false-sign* timing.
                (a["storm_start"], a["storm_end"]) !=
                (b["storm_start"], b["storm_end"])
                for a,b in zip(base["weather"], x["weather"])
            )
            mismatches += mismatch_days
            ledger_violations += x["ledger_error"] > 0.001
            extra_night += x["nights"] != x["days"]
    return {
        "design": {
            "kind": "paired one-factor interventions + coupled dusk-shift reference",
            "cases_per_arm": seeds * len(VARIANTS) * len(PROFILES),
            "seeds_per_variant_profile": seeds,
            "days_horizon": days,
            "registered_arms": ARMS,
            "constant_rules": "canonical survival_loop, unchanged real loot and core start",
            "dusk_note": "dusk +2h extends daylight and shortens night; false-signal timing may also shift",
        },
        "by_variant": stats,
        "checks": {
            "storm_schedule_mismatches": mismatches,
            "actual_body_thermal_ledger_failures": ledger_violations,
            "night_sequence_failures": extra_night,
        },
        "limitations": [
            "Temperature and death thresholds come from provisional toy-model tuning.",
            "Days completed is a capped count; 7-day horizon is right-censored.",
            "Day/night exposures are compared by phase, not inferred from one global mean.",
            "Counterfactual forecast viability uses the AGENT's own prediction, not the real next-day outcome.",
            "More than one viable forecast is necessary but not sufficient for meaningful player choice.",
            "Dusk change is coupled with longer daylight and altered false-sign timing.",
            "Randomized loot draws are sequential; trajectories can diverge after choice changes.",
            "No human playtest, game fun metric, Unreal runtime, real-world physiological claim.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", required=True)
    args = ap.parse_args()
    result = analyze(args.seeds, args.days)
    with open(args.json, "w", encoding="utf-8") as dest:
        json.dump(result, dest, ensure_ascii=False, indent=2)
    print(json.dumps({
        "design": result["design"], "checks": result["checks"],
        "by_variant": {v: {name: {
            "mean_days": z["mean_days"],
            "mean_first_morning_core_c": z["mean_first_morning_core_c"],
            "mean_night_fire_h": z["mean_night_fire_h"],
            "fraction_evenings_with_any_viable_option":
                z["fraction_evenings_with_any_viable_option"],
            "vs_baseline_count": z["vs_baseline_count"],
            "end_reasons": z["end_reasons"],
            "phases": z["phases"],
        } for name,z in arms.items()} for v, arms in result["by_variant"].items()}
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
