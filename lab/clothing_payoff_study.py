"""D1.4: Does preparation *pay* across heat, stamina and pace?

Ablation is applied only AFTER identical physical drying. Compare the same
route, storm, departure time and room state to identify each contribution.
An immediate wet departure is a separate practical tradeoff, NOT the causal
drying effect: it leaves earlier and avoids spending scarce fuel.

Human enjoyment is not measured. Coefficients are still provisional.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from statistics import mean

from .agent import Agent
from .body import (Body, CLOTHING_INSULATION_C, TRAVEL_FATIGUE_PER_H)
from .coupled_microloop import (
    DRY, BASE_WALK_STAMINA_PER_H, WET_EXTRA_FATIGUE_PER_H,
    WET_EXTRA_STAMINA_PER_H, WET_INSULATION_LOSS_C,
    WET_PACE_INSTABILITY, WET_EXPOSED_PACE_VARIATION,
    Equipment, _advance, _choose,
)
from .evening import Room
from .world import Edge, World

VARIANTS = ("A_safe", "B_readable", "C_unreadable")
DISTANCE_MULTIPLIERS = (1, 8, 24, 40)
ARMS = ("wet_now", "heated_wet", "prepared_all",
        "prepared_no_thermal", "prepared_no_stamina",
        "prepared_no_movement", "prepared_heat_only")
DRYING_MINUTES = 90


class AblatedEquipment(Equipment):
    """Research controls; production/ordinary Equipment are never affected."""

    def __init__(self, wetness: float, disabled: tuple[str, ...] = ()):
        super().__init__(wetness=wetness)
        self.disabled = frozenset(disabled)

    def _wear(self, channel: str) -> float:
        return 1.0 if channel in self.disabled else self.wetness

    @property
    def clothing_c(self) -> float:
        return CLOTHING_INSULATION_C - WET_INSULATION_LOSS_C * self._wear("thermal")

    @property
    def walk_stamina_per_h(self) -> float:
        return BASE_WALK_STAMINA_PER_H + WET_EXTRA_STAMINA_PER_H * self._wear("stamina")

    @property
    def walk_fatigue_per_h(self) -> float:
        return TRAVEL_FATIGUE_PER_H + WET_EXTRA_FATIGUE_PER_H * self._wear("stamina")

    def movement_stability(self, *, wind: float = 0.0, exposure: float = 0.0) -> float:
        return 1.0 - self._wear("movement") * (
            WET_PACE_INSTABILITY + WET_EXPOSED_PACE_VARIATION * wind * exposure
        )


def evaluate(seed: int, variant: str, multiplier: int) -> dict:
    """Seven paired outcomes, with all exogenous variables held fixed."""
    if multiplier not in DISTANCE_MULTIPLIERS:
        raise ValueError("unregistered route length")
    world = World.load("district_v0", variant)
    weather = world.roll_weather(random.Random(f"{seed}:weather:1"))
    reference = world.edge("home", "house_a")
    # Same mapped edge, stretched only for a CONTROLLED route-length probe;
    # this is not a claim that the actual building is 8 km away.
    edge = Edge(reference.a, reference.b,
                reference.length_m * multiplier, reference.exposure)

    results = {}
    for arm in ARMS:
        body = Body()
        room = Room(fuel=world.start_fuel, furniture=0)
        disabled = {
            "prepared_no_thermal": ("thermal",),
            "prepared_no_stamina": ("stamina",),
            "prepared_no_movement": ("movement",),
            "prepared_heat_only": ("stamina", "movement"),
        }.get(arm, ())
        gear = AblatedEquipment(wetness=1.0)  # all initial physical preparations identical
        fuel_at_start = room.fuel
        if arm != "wet_now":
            room.fire_lit = room.fuel > 0
            _advance(body, room, world, gear, DRYING_MINUTES,
                     at_home=True, work=(DRY if arm != "heated_wet" else ""))
        # Only the EXPEDITION is ablated. Every prepared arm must have the
        # exact same body, clothing wetness, clock and spent fuel at departure.
        gear.disabled = frozenset(disabled)
        departed_at = body.elapsed_minutes
        core_at_departure = body.core_c
        stamina_at_departure = body.stamina
        fuel_at_departure = room.fuel
        available_fire_hours = room.fire_hours_total
        activity = {"stamina_demand": 0.0, "extra_fatigue": 0.0,
                    "walked_h": 0.0, "minimum_stamina": body.stamina,
                    "wet_pace_delay_min": 0.0}
        legs = []
        for leg in ("outbound", "homebound"):
            if body.terminal:
                break
            absolute = world.dawn_min + body.elapsed_minutes
            wind = weather.wind(absolute)
            nominal = world.travel_minutes(edge, absolute, weather)
            target = gear.travel_minutes(
                nominal, wind=wind, exposure=edge.exposure
            )
            used = _advance(body, room, world, gear, target, at_home=False,
                            exposure=edge.exposure, weather=weather,
                            travelling=True, walking_costs=activity)
            legs.append({"leg": leg, "minutes_billed": round(used, 5),
                         "minutes_required": round(target, 5),
                         "completed": used >= target - 1e-6 and not body.terminal})
            if used < target - 1e-6 or body.terminal:
                break
        completed = len(legs) == 2 and all(x["completed"] for x in legs)
        results[arm] = {
            "completed_return": completed,
            "completed_before_11": completed and body.elapsed_minutes <= 180,
            "elapsed_minutes": round(body.elapsed_minutes, 5),
            "departure_minute": round(departed_at, 5),
            "travel_minutes": round(sum(x["minutes_billed"] for x in legs), 5),
            "core_at_departure": round(core_at_departure, 5),
            "fuel_at_departure": round(fuel_at_departure, 5),
            "core_after_route": round(body.core_c, 5),
            "stamina_at_departure": round(stamina_at_departure, 5),
            "stamina_after_route": round(body.stamina, 5),
            "walking_stamina_demand": round(activity["stamina_demand"], 5),
            "fatigue_after_route": round(body.fatigue, 5),
            "fuel_remaining": round(room.fuel, 5),
            "fuel_burned": round(room.burned_fuel_total, 5),
            "fire_hours_before_route": round(available_fire_hours, 5),
            "wetness_after_preparation": round(gear.wetness, 5),
            "terminal_at_minute": body.terminal_at_minute,
            "legs": legs,
            "fuel_initial": fuel_at_start,
        }
    return {"seed": seed, "variant": variant, "multiplier": multiplier,
            "weather": {"storm_start": weather.storm_start,
                        "storm_end": weather.storm_end},
            "arms": results}


def _average(values) -> float:
    return round(mean(values), 5) if values else 0.0


def study(seeds: int = 30) -> dict:
    if not 1 <= seeds <= 100:
        raise ValueError("seeds must be 1..100")
    checks = Counter()
    rows = {}
    illustrative = {}
    conditional = Counter()
    agent_choice = Counter()
    # A preserved meter is not yet a causal gameplay consequence. Record
    # which channels actually change return success or elapsed route time.
    ablation_changes = Counter()
    for variant in VARIANTS:
        rows[variant] = {}
        for multiplier in DISTANCE_MULTIPLIERS:
            blocks = [evaluate(seed, variant, multiplier) for seed in range(1, seeds+1)]
            values = [b["arms"] for b in blocks]
            for b in blocks:
                v = b["arms"]
                control = v["heated_wet"]
                dry = v["prepared_all"]
                for arm, r in v.items():
                    if r["fuel_remaining"] < -0.00001 or (
                        abs(r["fuel_initial"] - r["fuel_remaining"] - r["fuel_burned"]) > .001
                    ):
                        checks["fuel"] += 1
                    if r["elapsed_minutes"] > 1440 or r["elapsed_minutes"] < 0:
                        checks["clock"] += 1
                    if r["terminal_at_minute"] is not None and (
                        abs(r["elapsed_minutes"] - r["terminal_at_minute"]) > .001
                    ):
                        checks["terminal"] += 1
                # All prepared controls spend the same morning clock/fuel;
                # comparisons differ ONLY by clothing channel during exposure.
                for arm in ARMS[2:]:
                    r = v[arm]
                    if (abs(r["departure_minute"]-dry["departure_minute"]) > .0001
                        or abs(r["fuel_at_departure"]-dry["fuel_at_departure"]) > .001
                        or abs(r["core_at_departure"]-dry["core_at_departure"]) > .001
                        or abs(r["stamina_at_departure"]-dry["stamina_at_departure"]) > .001):
                        checks["preparation_not_matched"] += 1
                if abs(control["departure_minute"]-dry["departure_minute"]) > .0001:
                    checks["same_departure"] += 1
                # A completed route is required before comparing endpoint stats.
                if dry["completed_return"] and control["completed_return"]:
                    conditional["paired_complete"] += 1
                    if not (dry["core_after_route"] >= control["core_after_route"]-1e-6
                        and dry["stamina_after_route"] >= control["stamina_after_route"]-1e-6
                        and dry["travel_minutes"] <= control["travel_minutes"]+1e-6):
                        checks["dry_triangular_advantage"] += 1
                    if dry["core_after_route"] > control["core_after_route"] + 1e-5:
                        conditional["core_improved"] += 1
                    if dry["stamina_after_route"] > control["stamina_after_route"] + 1e-5:
                        conditional["stamina_improved"] += 1
                    if dry["travel_minutes"] < control["travel_minutes"] - 1e-5:
                        conditional["pace_improved"] += 1
                for channel, arm in (
                    ("thermal", "prepared_no_thermal"),
                    ("stamina", "prepared_no_stamina"),
                    ("movement", "prepared_no_movement"),
                ):
                    alternate = v[arm]
                    if alternate["completed_return"] != dry["completed_return"]:
                        ablation_changes[f"{channel}_completion"] += 1
                    if abs(alternate["elapsed_minutes"] - dry["elapsed_minutes"]) > .001:
                        ablation_changes[f"{channel}_clock"] += 1
                    if abs(alternate["stamina_after_route"] - dry["stamina_after_route"]) > .001:
                        ablation_changes[f"{channel}_stamina"] += 1
                    if abs(alternate["core_after_route"] - dry["core_after_route"]) > .001:
                        ablation_changes[f"{channel}_core"] += 1
                if dry["completed_return"] and v["wet_now"]["completed_return"]:
                    conditional["wet_and_prepped_complete"] += 1
                    if dry["elapsed_minutes"] < v["wet_now"]["elapsed_minutes"]:
                        conditional["prepared_faster_including_work"] += 1
                if dry["completed_return"] and not v["wet_now"]["completed_return"]:
                    conditional["prep_rescued_trip"] += 1
                if not dry["completed_return"] and v["wet_now"]["completed_return"]:
                    conditional["prep_lost_trip"] += 1

            # The actor currently predicts only 2h and has no route-length
            # input. Do NOT silently fix that before measuring its failure.
            world = World.load("district_v0", variant)
            agent = Agent("local", world)
            choice, reason = _choose(
                "agent", "morning", Body(), Room(fuel=world.start_fuel),
                Equipment(wetness=1.0), agent
            )
            agent_choice[f"{variant}/{multiplier}/{choice}"] += seeds

            rows[variant][str(multiplier)] = {
                "route_length_m": world.edge("home", "house_a").length_m * multiplier,
                "agent_morning_choice": choice,
                "agent_reason": reason,
                "arms": {
                    arm: {
                        "mean_capped_elapsed_h": _average(v[arm]["elapsed_minutes"]/60
                                                          for v in values),
                        "finished": sum(v[arm]["completed_return"] for v in values),
                        "before_11": sum(v[arm]["completed_before_11"] for v in values),
                        "mean_core_after": _average(v[arm]["core_after_route"] for v in values),
                        "mean_stamina_after": _average(v[arm]["stamina_after_route"] for v in values),
                        "mean_fatigue_after": _average(v[arm]["fatigue_after_route"] for v in values),
                        "mean_total_fuel_burned": _average(v[arm]["fuel_burned"] for v in values),
                        "mean_total_minutes": _average(v[arm]["elapsed_minutes"] for v in values),
                        "mean_travel_minutes": _average(v[arm]["travel_minutes"] for v in values),
                    } for arm in ARMS
                }
            }
            illustrative[f"{variant}/{multiplier}/seed1"] = blocks[0]
    return {
        "design": {
            "registered_distance_multipliers": DISTANCE_MULTIPLIERS,
            "seeds": seeds, "worlds": VARIANTS, "arms": ARMS,
            "cases": seeds*len(VARIANTS)*len(DISTANCE_MULTIPLIERS),
            "runs": seeds*len(VARIANTS)*len(DISTANCE_MULTIPLIERS)*len(ARMS),
            "same_weather": True, "no_human_participants": True,
            "causal_control": "heated_wet matches drying time and fire, not garment benefit",
            "net_control": "wet_now leaves immediately without fuel cost",
            "ablation": "benefits disabled ONLY after genuine drying; each other state matches",
        },
        "by_world_distance": rows,
        "observations": {k: conditional[k] for k in (
            "paired_complete","core_improved","stamina_improved",
            "pace_improved","wet_and_prepped_complete",
            "prepared_faster_including_work","prep_rescued_trip","prep_lost_trip"
        )},
        "actor_morning_choice": dict(agent_choice),
        "ablation_causal_changes": {
            f"{channel}_{metric}": ablation_changes[f"{channel}_{metric}"]
            for channel in ("thermal","stamina","movement")
            for metric in ("completion","clock","stamina","core")
        },
        "checks": {k: checks[k] for k in (
            "fuel","clock","terminal","preparation_not_matched",
            "same_departure","dry_triangular_advantage"
        )},
        "examples": illustrative,
        "limits": [
            "The same original edge is stretched by distance multiplier in an experimental probe, NOT a new actual map or a scripted player route.",
            "Temperature, wind and resource coefficients are placeholders.",
            "Movement stability is a deterministic walk-time penalty, NOT gameplay responsiveness.",
            "Same-departure physical comparisons isolate clothing benefits; wet_now includes opportunity costs and shifted storm exposure.",
            "An actor uses a hardcoded two-hour imagined trip today and does NOT learn route distance or empirically adjust clothing preferences here.",
            "Stamina currently affects the remaining stamina/fatigue meters but does NOT gate travel or alter move speed: preserving it is not yet a demonstrated direct success benefit.",
            "Study measures capability and decision mismatch, not fun or human intent.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=30)
    p.add_argument("--json", required=True)
    a = p.parse_args()
    result = study(a.seeds)
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "design":result["design"],
        "observations":result["observations"],
        "actor_morning_choice":result["actor_morning_choice"],
        "ablation_causal_changes":result["ablation_causal_changes"],
        "checks":result["checks"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
