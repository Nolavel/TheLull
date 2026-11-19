"""Behavior-only audit of TheLull lab day records.

No emotion or fun score: signals are diagnostics requiring human playtests.
Does not modify the world or agent (Claude's domain).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Iterable, Protocol


class DayLike(Protocol):
    day: int
    went_out: bool
    target: str | None
    carried: int
    plan_changes: int
    caught_in_storm: bool
    after_dark: bool
    crisis: bool
    cold_night: bool
    min_warmth: float
    margin: float
    return_error: float | None


@dataclass(frozen=True)
class ExperienceAudit:
    days: int
    trip_days: int
    no_trip_days: int
    longest_no_trip_streak: int
    distinct_targets: int
    replanned_trip_days: int
    pressure_without_replan_days: int
    unchallenged_repeat_target_days: int
    resource_return_days: int
    cold_nights: int
    departure_error_first_half_min: float | None
    departure_error_second_half_min: float | None
    margin_first_trip_min: float | None
    margin_last_trip_min: float | None


def audit(records: Iterable[DayLike]) -> ExperienceAudit:
    """Return observable signals, not psychological judgments.

    'Pressure' is a rough post-hoc label, not proof a meaningful choice existed.
    Error uses the original departure estimate and includes mid-trip replanning.
    """
    days = list(records)
    trips = [d for d in days if d.went_out]
    longest_idle = idle = 0
    repeat_target: str | None = None
    repeated_unchallenged = 0
    for d in days:
        if not d.went_out:
            idle += 1
            longest_idle = max(longest_idle, idle)
            repeat_target = None
            continue
        idle = 0
        pressured = d.caught_in_storm or d.after_dark or d.crisis or d.min_warmth < 25
        if not pressured and d.plan_changes == 0 and d.target is not None and d.target == repeat_target:
            repeated_unchallenged += 1
        repeat_target = d.target if not pressured and d.plan_changes == 0 else None

    # At least two estimates per half are needed for a trend, not a single anecdote.
    errors = [abs(d.return_error) for d in trips if d.return_error is not None]
    first_error = second_error = None
    if len(errors) >= 4:
        split = len(errors) // 2
        first_error = round(mean(errors[:split]), 2)
        second_error = round(mean(errors[split:]), 2)

    return ExperienceAudit(
        days=len(days),
        trip_days=len(trips),
        no_trip_days=len(days) - len(trips),
        longest_no_trip_streak=longest_idle,
        distinct_targets=len({d.target for d in trips if d.target is not None}),
        replanned_trip_days=sum(d.plan_changes > 0 for d in trips),
        pressure_without_replan_days=sum(
            (d.caught_in_storm or d.after_dark or d.crisis or d.min_warmth < 25)
            and d.plan_changes == 0 for d in trips
        ),
        unchallenged_repeat_target_days=repeated_unchallenged,
        resource_return_days=sum(d.carried > 0 for d in trips),
        cold_nights=sum(d.cold_night for d in days),
        departure_error_first_half_min=first_error,
        departure_error_second_half_min=second_error,
        margin_first_trip_min=round(trips[0].margin, 2) if trips else None,
        margin_last_trip_min=round(trips[-1].margin, 2) if trips else None,
    )


def compare(world: str, variants: list[str], profiles: list[str], days: int, seeds: int) -> dict:
    """Compare initial seed IDs; these are NOT guaranteed matched weather traces."""
    if days < 1 or seeds < 1:
        raise ValueError("days and seeds must be >= 1")
    from .sim import run

    result = {}
    for profile in profiles:
        for variant in variants:
            runs = [asdict(audit(run(world, variant, profile, days, seed))) for seed in range(seeds)]
            agg = {}
            for key in runs[0]:
                values = [r[key] for r in runs if r[key] is not None]
                agg[key] = {"mean": round(mean(values), 2) if values else None, "samples": len(values)}
            result[f"{profile}/{variant}"] = agg
    return {
        "scenario": {"world": world, "days": days, "seeds": seeds, "profiles": profiles, "variants": variants},
        "limitations": [
            "Signals describe simulated actions, not fear, enjoyment or confidence.",
            "Departure error mixes path forecasting with plan changes and search time.",
            "Matching seed IDs does not guarantee identical weather across variants.",
            "Current v0 lacks structured intentions, choices, cues and causal consequences.",
            "No-trip days are not automatically boredom; waiting can be a valid choice.",
        ],
        "metrics": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare experience signals, without assigning a fun score")
    parser.add_argument("--world", default="district_v0")
    parser.add_argument("--variants", nargs="+", default=["A_safe", "B_readable", "C_unreadable"])
    parser.add_argument("--profiles", nargs="+", default=["novice", "local"])
    parser.add_argument("--days", type=int, default=8)
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(
        compare(args.world, args.variants, args.profiles, args.days, args.seeds),
        ensure_ascii=False, indent=2
    ))


if __name__ == "__main__":
    main()
