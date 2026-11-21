"""Independent evidence gate for TheLull's connected dawn-to-dawn Python laboratory.

Checks observable state transitions instead of requiring a specific decision or a
particular survival duration. Legacy world-only drivers are not the runtime tested.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def audit(candidate: Path) -> dict:
    sys.path.insert(0, str(candidate.resolve()))
    from lab import body, evening, evening_run, agent, sim, world, survival_loop
    checks: list[dict] = []
    samples: dict = {}

    def record(name: str, passed: bool, evidence: str, kind: str = "integration") -> None:
        checks.append({"contract": name, "group": kind,
                       "status": "PASS" if passed else "BLOCKED", "evidence": evidence})

    w = world.World.load("district_v0", "B_readable")
    record("exact_24h", abs(w.daylight_hours + w.night_hours - 24) < 1e-9,
           f"day={w.daylight_hours}h, dark={w.night_hours}h")
    record("single_body", evening.Body is body.Body,
           "evening.Body and body.Body are identical Python classes")
    record("single_memory", evening.EveningBeliefs is agent.Beliefs,
           "night beliefs and Agent.beliefs are identical Python classes")
    record("night_window", abs(evening.HOURS_OF_NIGHT - w.night_hours) < 1e-9,
           f"evening default night={evening.HOURS_OF_NIGHT}, world dark={w.night_hours}")

    # Direct exploit checks must refuse the operation, not merely stop negative counts.
    empty = evening.Room(fuel=0, furniture=0)
    observer = body.Body(fatigue=45)
    beliefs = agent.Beliefs()
    rejected = False
    try:
        evening_run.play("A: разобрать мебель", w.air_temp_c, empty, observer, beliefs,
                         hours_of_night=w.night_hours)
    except ValueError:
        rejected = True
    record("no_fuel_from_absent_furniture", rejected and empty.fuel == 0 and empty.furniture == 0,
           f"invalid conversion rejected={rejected}; fuel={empty.fuel}; furniture={empty.furniture}")

    room = evening.Room(fuel=7, furniture=2)
    observer = body.Body(fatigue=45)
    evening_run.play("C: утеплить комнату", w.air_temp_c, room, observer, agent.Beliefs(),
                     hours_of_night=w.night_hours)
    first_cooling = room.cooling_rate
    rejected = False
    try:
        evening_run.play("C: утеплить комнату", w.air_temp_c, room, observer, agent.Beliefs(),
                         hours_of_night=w.night_hours)
    except ValueError:
        rejected = True
    record("no_repeated_sealing", rejected and room.cooling_rate == first_cooling,
           f"second repair rejected={rejected}; cooling={room.cooling_rate}")

    # The integration explicitly opts out of the older flat night and calls
    # the owned evening night exactly once. This is a structural aid, not
    # a substitute for the runtime conservation checks below.
    integration_source = (candidate / "lab" / "survival_loop.py").read_text(encoding="utf-8")
    record("one_night_owner", "charge_legacy_night=False" in integration_source and
           integration_source.count("night = play(") == 1,
           "day-only sim.run_day + one evening_run.play night")

    violations = collections.Counter()
    reason_counts = collections.Counter()
    choices = collections.Counter()
    lengths = []
    cold_end_without_enough_resources = 0
    for variant in ("A_safe", "B_readable", "C_unreadable"):
        for profile in ("novice", "local"):
            for seed in range(1, 31):
                run = survival_loop.run(seed, 7, variant=variant, profile=profile)
                again = survival_loop.run(seed, 7, variant=variant, profile=profile)
                if run != again:
                    violations["determinism"] += 1
                length = len(run["history"])
                lengths.append(length)
                reason_counts[run["end_reason"] or "horizon"] += 1
                for index, day in enumerate(run["history"]):
                    choices[day["evening"]["chose"][0]] += 1
                    if abs(day["minutes_accounted"] - world.DAY_MINUTES) > 1e-5:
                        violations["minutes"] += 1
                    if day["night_hours"] <= 0 or day["night_hours"] > 14:
                        violations["night_window"] += 1
                    if day["fuel_next_dawn"] < 0 or day["furniture_next_dawn"] < 0:
                        violations["negative_resource"] += 1
                    yield_by_furniture = 4 * max(0, day["furniture_at_dawn"] - day["furniture_next_dawn"])
                    if day["fuel_next_dawn"] > day["fuel_at_dawn"] + day["carried"] + yield_by_furniture + 0.002:
                        violations["free_fuel"] += 1
                    if index:
                        prev = run["history"][index - 1]
                        if abs(day["fuel_at_dawn"] - prev["fuel_next_dawn"]) > 0.002:
                            violations["fuel_reset"] += 1
                        if day["furniture_at_dawn"] != prev["furniture_next_dawn"]:
                            violations["furniture_reset"] += 1
                        if abs(day["core_at_dawn"] - prev["core_next_dawn"]) > 0.0002:
                            violations["core_reset"] += 1
                        if abs(day["fatigue_at_dawn"] - prev["fatigue_next_dawn"]) > 0.002:
                            violations["fatigue_reset"] += 1
                if run["history"] and run["end_reason"] is None and length < 7:
                    violations["unexplained_end"] += 1

    samples["runs"] = 180
    samples["mean_days"] = round(sum(lengths) / len(lengths), 2)
    samples["end_reasons"] = dict(reason_counts)
    samples["evening_choices"] = dict(choices)
    samples["violations"] = dict(violations)
    for target in ("minutes","night_window","fuel_reset","furniture_reset","core_reset",
                   "fatigue_reset","free_fuel","negative_resource","unexplained_end","determinism"):
        record("runtime_" + target, violations[target] == 0,
               f"180 paired reproducible runs: {violations[target]} violations")

    # Hold objective weather fixed across different announced intentions.
    paired_a = survival_loop.run(11, 4, intentions=[evening.SHORT_WALK])
    paired_b = survival_loop.run(11, 4, intentions=[evening.EXPEDITION])
    matched = all(a["world_weather"] == b["world_weather"]
                  for a, b in zip(paired_a["history"], paired_b["history"]))
    record("counterfactual_weather", matched,
           "changing intended trip cannot change the seed/day weather generator")

    record("multiple_outcome_causes_emerge", len(reason_counts) > 1,
           f"ending causes in 180 runs: {dict(reason_counts)}",
           kind="research_signal")

    return {
        "candidate": str(candidate),
        "scope": "connected survival_loop runtime, not older world-only simulation",
        "findings": checks,
        "counts": dict(collections.Counter(row["status"] for row in checks)),
        "metrics": samples,
        "limitations": [
            "No controlled human playtest, save/load or real Unreal runtime.",
            "World remains fuel-only; scarcity and physiology are unbalanced placeholders.",
            "A single fixed termination reason is a research result, not a failing integration contract.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = audit(Path(args.candidate))
    result_path = Path(args.out)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Connected loop audit: {report['counts']}")
    for row in report["findings"]:
        print(f"{row['status']} {row['group']} {row['contract']}: {row['evidence']}")
    print("Study results:", report["metrics"]["end_reasons"])


if __name__ == "__main__":
    main()
