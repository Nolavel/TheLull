"""One-factor experiment: do visible weather signs change decisions?

Paired design: for each seed the two conditions share the same world, start and weather truth.
Only the visibility of signs differs. Output is observation, not a significance test.

  python3 -m lab.experiment --variant B_readable --profile local --days 8 --seeds 200 [--json out.json] [--md]
"""
from __future__ import annotations

import argparse
import json
from statistics import mean

from .sim import DayRecord, run


def metrics(records: list[DayRecord]) -> dict:
    trips = [r for r in records if r.went_out]
    return {
        "storm_days": sum(r.storm_start is not None for r in records),
        "trips": len(trips),
        "caught_in_storm": sum(r.caught_in_storm for r in records),
        "plan_changes": sum(r.plan_changes for r in records),
        "scares": sum(bool(r.after_dark or r.crisis or r.caught_in_storm) for r in trips),
        "carried_per_day": round(mean(r.carried for r in records), 2),
        "cold_nights": sum(r.cold_night for r in records),
        "signal_decisions": sum(d.point == "сигнал" for r in records for d in r.decisions),
    }


def day_choices(r: DayRecord) -> tuple:
    return tuple((d.point, d.choice) for d in r.decisions)


def compare(variant: str, profile: str, days: int, seeds: int) -> dict:
    on_m, off_m = [], []
    differing_seeds, first_day_differs, stories = 0, 0, []
    for seed in range(1, seeds + 1):
        on = run("district_v0", variant, profile, days, seed, signals_visible=True)
        off = run("district_v0", variant, profile, days, seed, signals_visible=False)
        on_m.append(metrics(on))
        off_m.append(metrics(off))
        diverge = next((i for i, (a, b) in enumerate(zip(on, off)) if day_choices(a) != day_choices(b)), None)
        if diverge is not None:
            differing_seeds += 1
            first_day_differs += diverge == 0
            if len(stories) < 3:
                a_d, b_d = _first_difference(on[diverge], off[diverge])
                stories.append({"seed": seed, "day": on[diverge].day,
                                "signs_visible": a_d, "signs_hidden": b_d})

    def avg(ms: list[dict], key: str) -> float:
        return round(mean(m[key] for m in ms), 2)

    keys = list(on_m[0])
    return {
        "scenario": {"world": "district_v0", "variant": variant, "profile": profile,
                     "days": days, "seeds": seeds, "factor": "видимость признаков погоды"},
        "mean_per_seed": {k: {"signs_visible": avg(on_m, k), "signs_hidden": avg(off_m, k)} for k in keys},
        "seeds_with_any_different_decision": differing_seeds,
        "seeds_differing_on_day_1": first_day_differs,
        "stories": stories,
        "limitations": [
            "Observation of simulated decisions only; no claim about player emotion.",
            "No significance test; differences in counts are descriptive.",
            "Economy is starved (cold nights are frequent); conclusions are about this world, not balance.",
        ],
    }


def _first_difference(a: DayRecord, b: DayRecord) -> tuple[dict | None, dict | None]:
    """The first decision where the two versions of the same day part ways (a missing one counts)."""
    for i in range(max(len(a.decisions), len(b.decisions))):
        x = a.decisions[i] if i < len(a.decisions) else None
        y = b.decisions[i] if i < len(b.decisions) else None
        if (x and (x.point, x.choice)) != (y and (y.point, y.choice)):
            return (_brief(x) if x else None), (_brief(y) if y else None)
    return None, None


def _brief(d) -> dict:
    return {"time": d.time, "point": d.point, "choice": d.choice, "reason": d.reason, "outcome": d.outcome}


def to_markdown(res: dict) -> str:
    sc = res["scenario"]
    lines = [f"### Эксперимент: {sc['factor']} — {sc['variant']}, {sc['profile']}, {sc['seeds']} seed × {sc['days']} дней",
             "", "| Показатель (среднее на seed) | Признаки видны | Признаки скрыты |", "|---|---|---|"]
    for k, v in res["mean_per_seed"].items():
        lines.append(f"| {k} | {v['signs_visible']} | {v['signs_hidden']} |")
    lines += ["", f"Seed с любым отличием решений: **{res['seeds_with_any_different_decision']}** из {sc['seeds']}; "
              f"отличие уже в первый день: **{res['seeds_differing_on_day_1']}**.", "",
              "Ограничения: " + " ".join(res["limitations"])]
    for st in res["stories"]:
        lines += ["", f"**Seed {st['seed']}, день {st['day']}**"]
        for label in ("signs_visible", "signs_hidden"):
            d = st[label]
            text = (f"{d['time']} [{d['point']}] выбрал «{d['choice']}» — {d['reason']}" if d
                    else "решения в этой точке нет (уже в другом сценарии дня)")
            lines.append(f"- {label}: {text}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="B_readable")
    ap.add_argument("--profile", default="local")
    ap.add_argument("--days", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--json")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    res = compare(a.variant, a.profile, a.days, a.seeds)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(to_markdown(res) if a.md else json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
