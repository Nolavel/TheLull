"""CLI: python -m lab.run --variant B_readable --profile novice --days 12 --seed 1 [--json out.json]"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from statistics import mean

from .sim import DayRecord, run


def summary(records: list[DayRecord]) -> dict:
    trips = [r for r in records if r.went_out]
    half = len(trips) // 2 or 1
    err = lambda rs: round(mean(abs(r.return_error) for r in rs), 1) if rs else None
    return {
        "trips": len(trips),
        "return_error_first_half_min": err(trips[:half]),
        "return_error_second_half_min": err(trips[half:]),
        "margin_start_end": [round(records[0].margin), round(records[-1].margin)],
        "plan_changes": sum(r.plan_changes for r in records),
        "scares": sum(r.after_dark or r.crisis or r.caught_in_storm for r in trips),
        "cold_nights": sum(r.cold_night for r in records),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="district_v0")
    ap.add_argument("--variant", default="B_readable")
    ap.add_argument("--profile", default="novice")
    ap.add_argument("--days", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json")
    a = ap.parse_args()
    records = run(a.world, a.variant, a.profile, a.days, a.seed)
    for r in records:
        print(f"\nДень {r.day} (топливо утром {r.fuel_morning}, запас {r.margin:.0f} мин, доверие к приметам {r.signal_trust:.0%})")
        for e in r.events:
            print("  " + e)
    s = summary(records)
    print("\nИтог:", json.dumps(s, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"args": vars(a), "summary": s, "days": [asdict(r) for r in records]}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
