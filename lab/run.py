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
        "travel_error_mean_min": round(mean(r.travel_error for r in trips), 1) if trips else None,
        "decision_points": {p: sum(d.point == p for r in records for d in r.decisions)
                            for p in ("выход", "цель", "разведка", "сигнал", "буря")},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="district_v0")
    ap.add_argument("--variant", default="B_readable")
    ap.add_argument("--profile", default="novice")
    ap.add_argument("--days", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json")
    ap.add_argument("--decisions", action="store_true", help="print the reasoning behind each decision")
    a = ap.parse_args()
    records = run(a.world, a.variant, a.profile, a.days, a.seed)
    for r in records:
        print(f"\nДень {r.day} (топливо утром {r.fuel_morning}, запас {r.margin:.0f} мин, доверие к приметам {r.signal_trust:.0%})")
        for e in r.events:
            print("  " + e)
        if a.decisions:
            for d in r.decisions:
                print(f"  ▸ {d.time} [{d.point}] хотел: {d.intention}")
                print(f"      видел: {'; '.join(d.cues)}")
                print("      рассматривал: " + ", ".join(
                    f"{x['option']} ({x.get('basis') or ('~' + str(x.get('predicted_min')) + ' мин')})" for x in d.alternatives))
                print(f"      выбрал: {d.choice} — {d.reason}")
                if d.outcome:
                    print(f"      итог: {d.outcome}")
                if d.belief_update:
                    print(f"      вера: {d.belief_update.strip('; ')}")
            print(f"  → следующее намерение: {r.next_intention}")
    s = summary(records)
    print("\nИтог:", json.dumps(s, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"args": vars(a), "summary": s, "days": [asdict(r) for r in records]}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
