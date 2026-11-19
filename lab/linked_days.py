"""Connected evening -> sleep -> morning -> next-day opportunity experiment.

No game engine or third-party dependencies. An illustrative *day effort* bridge,
NOT a surrogate for TheLull's future map, thermal exposure or player psychology.
State (fuel, furniture, insulation, fatigue) persists; no free daily refill.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .evening import (COOLING_RATE_C_PER_H, EXPEDITION, HYPOTHERMIC_C,
                      SHORT_WALK, UNDECIDED, Body, EveningBeliefs, Room, Tomorrow, choose)
from .evening_run import fresh, play


@dataclass
class Depot:
    """Finite fuel available to retrieve; not an unexplained daily grant."""
    fuel: int = 10


@dataclass
class DayResult:
    intended: str
    actual: str
    decision: str
    estimated_fatigue_after: float
    actual_fatigue_after: float
    hours_spent: float
    fuel_collected: int
    depot_left: int
    attempted: bool


def effort(plan: Tomorrow, wind: float = 0.5) -> float:
    """Placeholder long-term fatigue budget for travel/carry: wind and load matter."""
    return plan.hours_out * (3.0 + 0.9 * plan.load + 1.5 * wind)


def do_next_day(plan: Tomorrow, body: Body, room: Room, depot: Depot,
                wind: float = 0.5) -> DayResult:
    """Agent can voluntarily shorten or cancel when it thinks the trip is unaffordable.

    This intentionally does not invent a full spatial/weather/day-body simulation;
    travel effort is an explicit, inspectable abstraction.
    """
    if not 0.0 <= wind <= 1.0:
        raise ValueError("wind must be between 0 and 1")
    morning = body.fatigue
    projected = morning + effort(plan, wind)
    actual = plan
    if body.core_c < HYPOTHERMIC_C or morning > plan.max_morning_fatigue or projected > 90.0:
        if plan is SHORT_WALK or morning + effort(SHORT_WALK, wind) > 90.0 or body.core_c < HYPOTHERMIC_C:
            room.step(8.0)  # the world clock keeps running if the player stays home
            return DayResult(plan.name, "остался дома", "сам решил восстановиться до выхода",
                             round(projected, 1), round(morning, 1), 0.0, 0, depot.fuel, False)
        actual = SHORT_WALK

    cost = effort(actual, wind)
    # The world continues while the hero travels: the unattended stove burns.
    room.step(8.0)
    body.fatigue = min(100.0, body.fatigue + cost)
    body.stamina = max(0.0, body.stamina - min(50.0, actual.load * 4.0))
    # No infinite replenishment. A larger excursion has a chance to bring back
    # more, but also demands more long-term energy. Supply is finite.
    requested = max(1, round(actual.load / 2.0))
    found = min(requested, depot.fuel)
    depot.fuel -= found
    room.fuel += found
    decision = ("вышел по плану" if actual is plan else
                "отложил дальнюю вылазку и выбрал короткую")
    return DayResult(plan.name, actual.name, decision, round(projected, 1),
                     round(body.fatigue, 1), round(actual.hours_out, 1),
                     found, depot.fuel, True)


def run_cycle(plans: list[Tomorrow], temperatures: list[float] | None = None,
              fuel: int = 5, depot_fuel: int = 10, recovery_per_h: float = 6.0,
              cooling: float = COOLING_RATE_C_PER_H, wind: float = 0.5,
              axe: bool = True) -> dict:
    if fuel < 0 or depot_fuel < 0 or recovery_per_h <= 0 or not plans:
        raise ValueError("invalid starting state or empty plan sequence")
    temperatures = temperatures or [-18.0] * len(plans)
    if len(temperatures) != len(plans):
        raise ValueError("temperatures must match plans")
    room, body, beliefs = fresh(cooling, fuel=fuel, recovery=recovery_per_h)
    room.has_axe = axe
    depot = Depot(depot_fuel)
    records = []
    for day, (plan, outside_c) in enumerate(zip(plans, temperatures), start=1):
        start = {"fuel": round(room.fuel, 2), "furniture": room.furniture, "sealed": room.sealed,
                 "fatigue": round(body.fatigue, 1), "core_c": round(body.core_c, 1)}
        pick, reason, revised_plan = choose(body, room, beliefs, plan, outside_c)
        night = play(pick["option"], outside_c, room, body, beliefs)
        # No learning from inaccessible truth (e.g. the exact moment a fire
        # expired while asleep). An unobserved outcome cannot update beliefs.
        lesson = "точного наблюдения расхода нет — оценка сохранена"
        observed = night.get("observed_burn_rate")
        if observed is not None:
            lesson = beliefs.observe_burn_rate(observed)
        next_day = do_next_day(revised_plan, body, room, depot, wind)
        records.append({
            "day": day, "outside_c": outside_c, "intention": plan.name,
            "before_evening": start, "choice": pick["option"], "why": reason,
            "forecast": pick, "after_evening_plan": revised_plan.name,
            "night": {k: v for k, v in night.items() if k != "log"},
            "daytime": asdict(next_day), "lesson": lesson,
            "after_day": {"fuel": round(room.fuel, 2), "furniture": room.furniture,
                          "sealed": room.sealed, "fatigue": round(body.fatigue, 1),
                          "core_c": round(body.core_c, 1)},
        })
    return {
        "scenario": {"plans": [p.name for p in plans], "temperatures": temperatures,
                     "fuel": fuel, "depot_fuel": depot_fuel, "recovery_per_h": recovery_per_h,
                     "cooling": cooling, "wind": wind, "axe": axe},
        "days": records,
        "summary": {"evening_choices": [d["choice"][:1] for d in records],
                    "trips_completed": sum(d["daytime"]["attempted"] for d in records),
                    "plans_changed": sum(d["daytime"]["actual"] != d["intention"] for d in records),
                    "cold_wakes": sum(d["night"]["woke_cold"] for d in records),
                    "depot_remaining": depot.fuel,
                    "furniture_remaining": room.furniture,
                    "fatigue_end": round(body.fatigue, 1)},
        "limits": [
            "Travel effort is a placeholder: not a city map, gear model or outdoor thermal simulation.",
            "Predictions depend on the agent's beliefs, not hindsight; outcomes are not emotions.",
            "Room preparation, resources and fatigue persist; no daily magic fuel or fatigue reset.",
            "Weather is fixed per scenario and wind is an explicit controlled parameter.",
            "A/B/C choice policy is a research heuristic; its scores are not human preference data.",
        ],
    }


def paired_plans(temperatures: list[float] | None = None, fuel: int = 5,
                 recovery: float = 6.0, cooling: float = COOLING_RATE_C_PER_H,
                 wind: float = 0.5) -> dict:
    """Counterfactual: same home, fuel, temperature, wind; only intent differs."""
    temp = temperatures[0] if temperatures else -18.0
    results = {}
    for plan in (SHORT_WALK, EXPEDITION, UNDECIDED):
        outcome = run_cycle([plan], [temp], fuel=fuel, recovery_per_h=recovery,
                            cooling=cooling, wind=wind)
        d = outcome["days"][0]
        results[plan.name] = {
            "choice": d["choice"][:1],
            "expected_morning_fatigue": d["forecast"]["morning_fatigue_expected"],
            "expected_day_fatigue": d["forecast"]["fatigue_after_trip_expected"],
            "actual_morning_fatigue": d["night"]["morning_fatigue"],
            "actual_day_fatigue": d["daytime"]["actual_fatigue_after"],
            "actual_day_plan": d["daytime"]["actual"],
            "reason": d["why"],
        }
    distinct = len({x["choice"] for x in results.values()})
    return {"scenario": {"outside_c": temp, "fuel": fuel, "recovery": recovery,
                         "cooling": cooling, "wind": wind},
            "by_intention": results, "distinct_evening_choices": distinct,
            "reading": ("разные планы изменили вечернюю подготовку" if distinct > 1 else
                        "вечер одинаков — в этих условиях намерение пока не меняет решение")}


def sweep_plans() -> dict:
    """Scan rather than cherry-pick cases where a future plan changes the evening."""
    cells = []
    for temp in (-24.0, -18.0, -12.0, -6.0, -2.0):
        for fuel in (3, 5, 7):
            for recovery in (3.0, 6.0, 9.0):
                row = paired_plans([temp], fuel=fuel, recovery=recovery)
                cells.append({"temp": temp, "fuel": fuel, "recovery": recovery,
                              "choices": {k: v["choice"] for k, v in row["by_intention"].items()},
                              "distinct": row["distinct_evening_choices"]})
    differs = [c for c in cells if c["distinct"] > 1]
    return {"cells": len(cells), "different_plan_changes_evening": len(differs),
            "examples": differs[:6], "counterexamples": [c for c in cells if c["distinct"] == 1][:3],
            "limitation": "Differences are simulated under a heuristic policy; no player preference proof."}


def to_markdown(result: dict) -> str:
    s = result["summary"]
    lines = ["### Связанный опыт: вечер → ночь → следующий день", "",
             f"Вечерние решения: {', '.join(s['evening_choices'])}; "
             f"изменил дневной план {s['plans_changed']} раз; "
             f"просыпался от холода {s['cold_wakes']} раз.", "",
             "| День | Намерение | Вечер | Сон | Реальный выход | Запасы и усталость |",
             "|---|---|---|---:|---|---|"]
    for d in result["days"]:
        lines.append(f"| {d['day']} | {d['intention']} | {d['choice'][:1]} | "
                     f"{d['night']['slept_hours']} ч | {d['daytime']['actual']} | "
                     f"дрова {d['after_day']['fuel']}; усталость {d['after_day']['fatigue']} |")
    lines += ["", "Ограничения: " + " ".join(result["limits"])]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--fuel", type=int, default=5)
    ap.add_argument("--stock", type=int, default=10)
    ap.add_argument("--recovery", type=float, default=6.0)
    ap.add_argument("--temp", type=float, default=-18)
    ap.add_argument("--wind", type=float, default=0.5)
    ap.add_argument("--no-axe", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--paired", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()
    if args.sweep:
        result = sweep_plans()
    elif args.paired:
        result = paired_plans([args.temp], fuel=args.fuel, recovery=args.recovery, wind=args.wind)
    else:
        schedule = [EXPEDITION, SHORT_WALK, UNDECIDED]
        plans = [schedule[i % len(schedule)] for i in range(args.days)]
        result = run_cycle(plans, [args.temp] * args.days, args.fuel, args.stock,
                           args.recovery, wind=args.wind, axe=not args.no_axe)
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(to_markdown(result) if args.md and "summary" in result else
          json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
