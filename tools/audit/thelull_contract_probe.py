"""Independent, read-only audit of the TheLull candidate gameplay contracts.

Runs against an explicitly checked-out GitHub branch; it does not modify
Claude/Codex-owned code. Claims are behavioural probes or labelled structural
checks, not a playtest or an endorsement of game balance.
"""
from __future__ import annotations

import argparse
import collections
import inspect
import json
import random
import sys
from pathlib import Path


def audit(candidate: Path) -> dict:
    sys.path.insert(0, str(candidate.resolve()))
    from lab import agent, body, evening, evening_run, loop_bridge, sim, world

    findings = []
    metrics = {}

    def check(name: str, ok: bool, evidence: str, group: str = "integration") -> None:
        findings.append({"contract": name, "group": group,
                         "status": "PASS" if ok else "BLOCKED", "evidence": evidence})

    w = world.World.load("district_v0", "B_readable")
    daytime = w.daylight_hours
    night = w.night_hours
    check("24h_world_windows", abs(daytime + night - 24) < 1e-8,
          f"daylight={daytime}h; darkness={night}h; total={daytime + night}h",
          "world")
    metrics["world_hours"] = {"daylight": daytime, "darkness": night}

    check("world_run_accepts_shared_body",
          "body" in inspect.signature(sim.run_day).parameters
          and "body" in inspect.signature(sim.run).parameters,
          "run_day/run must accept a persistent lab.body.Body", "world")

    b = body.Body(core_c=36.0, fatigue=31.0)
    a = agent.Agent("local", w)
    weather = w.roll_weather(random.Random("7:weather:1"))
    rec, _ = sim.run_day(w, a, weather, random.Random("7:loot"), 1, 0, body=b)
    check("day_updates_supplied_body", b.core_c != 36.0 and b.fatigue > 31.0,
          f"core=36 -> {b.core_c:.3f}; fatigue=31 -> {b.fatigue:.3f}; trip={rec.went_out}", "world")
    metrics["day_body_proof"] = {"core_after": round(b.core_c, 3),
                                 "fatigue_after": round(b.fatigue, 3)}

    w2 = world.World.load("district_v0", "B_readable")
    wea = w2.roll_weather(random.Random("3:weather:2"))
    check("world_weather_reproducible",
          vars(wea) == vars(w2.roll_weather(random.Random("3:weather:2"))),
          "weather depends only on seed and day", "world")

    hours = getattr(evening, "HOURS_OF_NIGHT", None)
    check("evening_uses_world_night_window",
          hours is None or abs(float(hours) - night) < 1e-8,
          f"evening.HOURS_OF_NIGHT={hours}; world.night_hours={night}")

    ebody = getattr(evening, "Body", None)
    check("single_body_class_for_day_and_night",
          ebody is body.Body,
          f"lab.evening.Body is lab.body.Body: {ebody is body.Body}")

    esrc = (candidate / "lab" / "evening.py").read_text(encoding="utf-8")
    bridge = (candidate / "lab" / "loop_bridge.py").read_text(encoding="utf-8")
    check("no_second_evening_beliefs_instance",
          "EveningBeliefs()" not in bridge and "EveningBeliefs()" not in esrc,
          "separate beliefs instance in bridge or evening source: "
          f"{'EveningBeliefs()' in bridge or 'EveningBeliefs()' in esrc}")
    check("bridge_passes_world_body_to_day",
          "body=" in bridge,
          "loop_bridge uses run_day(... body=shared_body) rather than local Body()")

    check("no_legacy_departure_time_arithmetic",
          "(record.actual_return or DEPART_MIN) - DEPART_MIN" not in bridge,
          "old DEPART_MIN=60 now means offset after 08:00 dawn; "
          "subtracting it from absolute return fabricates ~8h of activity")

    check("no_flat_night_double_accounting",
          "recovered_pre_night" not in bridge and "legacy_fuel_after_night" not in bridge,
          "legacy _night bill must be removed instead of reversed by a temporary bridge")

    check("no_second_fatigue_charge",
          "activity_h * 5.0" not in bridge,
          "day now charges shared Body; adapter's heuristic must disappear")

    class FuelTracedRoom(evening.Room):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.peak_fuel = float(self.fuel)

        def step(self, hours):
            self.peak_fuel = max(self.peak_fuel, float(self.fuel))
            return super().step(hours)

    # Exercise owned evening implementation directly, not the adapter's guards.
    room = FuelTracedRoom(fuel=0, furniture=0)
    eb = ebody() if ebody is not None else body.Body()
    beliefs_type = getattr(evening, "EveningBeliefs", None)
    if beliefs_type is None:
        beliefs = agent.Agent("local", w).beliefs
    else:
        beliefs = beliefs_type()
    evening_run.play("A: разобрать мебель", -6.0, room, eb, beliefs)
    check("no_fuel_from_absent_furniture", room.peak_fuel == 0,
          f"furniture initially=0, fuel initially=0; peak fuel={room.peak_fuel:g}")

    room2 = evening.Room(fuel=7, furniture=2)
    eb2 = ebody() if ebody is not None else body.Body()
    b2 = beliefs_type() if beliefs_type else agent.Agent("local", w).beliefs
    evening_run.play("C: утеплить комнату", -6.0, room2, eb2, b2)
    once = room2.cooling_rate
    evening_run.play("C: утеплить комнату", -6.0, room2, eb2, b2)
    twice = room2.cooling_rate
    check("no_repeated_free_insulation", abs(once - twice) < 1e-8,
          f"cooling after first C={once:.3f}; after second C={twice:.3f}")

    # The loop probe may still execute, but its old scale must not be advertised
    # as proof of shared continuity when the owner models diverge.
    c = loop_bridge.linked(seed=2, days=3)
    metrics["old_bridge_example"] = [{
        "day": row["day"], "return_min": row["return_min"],
        "fuel_next_dawn": row["fuel_next_dawn"],
        "fatigue_next_dawn": round(row["fatigue_next_dawn"], 1),
    } for row in c["days"]]
    check("single_world_clock_in_bridge",
          "HOURS_OF_NIGHT" not in esrc and "DEPART_MIN" not in bridge,
          "old bridge imports a legacy departure offset and/or evening hardcodes a night length")

    summary = collections.Counter()
    days_by_variant = collections.defaultdict(list)
    for variant in ("A_safe", "B_readable", "C_unreadable"):
        for profile in ("novice", "local"):
            for seed in range(1, 31):
                records = sim.run("district_v0", variant, profile, 30, seed)
                reason = records[-1].run_end_reason or "30-day horizon"
                summary[reason] += 1
                days_by_variant[variant].append(len(records))
    metrics["run_end_reasons"] = dict(summary)
    metrics["run_lengths"] = {
        k: {"min": min(v), "max": max(v),
            "mean": round(sum(v) / len(v), 2)} for k, v in days_by_variant.items()
    }
    check("outcome_not_single_fixed_failure",
          len(summary) > 1,
          "180 runs / 3 variants / 2 profiles / 30 seeds; reasons: " + str(dict(summary)),
          "research_signal")

    return {
        "candidate": str(candidate),
        "scope": "read-only branch audit; candidate may be mid-integration",
        "findings": findings,
        "counts": dict(collections.Counter(x["status"] for x in findings)),
        "metrics": metrics,
        "limitations": [
            "The legacy loop_bridge is temporary and not an accepted UE runtime.",
            "Structural checks are signposts, not a substitute for integration tests.",
            "No new TLD mechanics or tuned survival balance were introduced.",
            "World tests and evening tests passing separately cannot prove a shared clock/body.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = audit(Path(args.candidate))
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Independent contract audit: {result['counts']}")
    for finding in result["findings"]:
        print(f"{finding['status']:7} {finding['group']:16} {finding['contract']}: {finding['evidence']}")
    print("Run outcomes:", result["metrics"]["run_end_reasons"])


if __name__ == "__main__":
    main()
