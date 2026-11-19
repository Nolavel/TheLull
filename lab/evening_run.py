"""Run the evening cycle: force each option, or let the player choose for three days.

  python3 -m lab.evening_run --compare            # A/B/C under identical weather
  python3 -m lab.evening_run --days 3             # the player chooses; beliefs update from the morning
  python3 -m lab.evening_run --compare --cooling 6  # one factor: a room that loses heat twice as fast
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace

from .evening import (COOLING_RATE_C_PER_H, HEAVY, HOURS_OF_NIGHT, HYPOTHERMIC_C, IDLE_FATIGUE_PER_H,
                      MODERATE, STEP_H, Body, EveningBeliefs, Room, choose, options, sleep_refusal,
                      step_body)

OUTSIDE_C = -18.0  # Hoarbound's reference exposure figure; placeholder, not TheLull balance


def play(option_label: str, outside_c: float, room: Room, body: Body, beliefs: EveningBeliefs) -> dict:
    work = {"A": HEAVY, "B": None, "C": MODERATE}[option_label[0]]
    log, hour = [], 0.0

    if work is not None:
        # A long action owns game time: the room keeps cooling and the body keeps tiring while it runs.
        worked = 0.0
        while worked < work.hours:
            step = min(STEP_H, work.hours - worked)
            room.step(step)
            step_body(body, room, outside_c, step, asleep=False, fatigue_per_h=work.fatigue_per_h)
            worked += step
            hour += step
        body.stamina = max(0.0, body.stamina - work.stamina_cost)
        room.fuel += work.fuel
        log.append(f"{hour:4.1f} ч: {work.name} — {work.fuel} топлива, "
                   f"выносливость {body.stamina:.0f}, усталость {body.fatigue:.0f}")
    else:
        log.append(f"{hour:4.1f} ч: работать не стал — выносливость {body.stamina:.0f}, "
                   f"усталость {body.fatigue:.0f}")

    refusal = sleep_refusal(room, body, outside_c)
    room.fire_lit = room.fuel > 0
    if refusal == "слишком холодно, чтобы ложиться" and room.fire_lit:
        # Warm the room first, as Hoarbound's sleep refusal intends: prepare, then sleep.
        waited = 0.0
        while sleep_refusal(room, body, outside_c) and room.fire_lit and waited < 3.0:
            room.step(STEP_H)
            step_body(body, room, outside_c, STEP_H, asleep=False, fatigue_per_h=IDLE_FATIGUE_PER_H)
            waited += STEP_H
            hour += STEP_H
        log.append(f"{hour:4.1f} ч: ждал, пока комната прогреется ({waited:.1f} ч), "
                   f"в комнате {room.felt_c(outside_c):.0f}°")
    refusal = sleep_refusal(room, body, outside_c)
    if refusal:
        log.append(f"{hour:4.1f} ч: лечь не вышло — {refusal}")

    night_hours = max(0.0, HOURS_OF_NIGHT - hour)
    fire_out_at, coldest, hypo_hours = None, body.core_c, 0.0
    slept = 0.0
    while slept < night_hours:
        was_lit = room.fire_lit
        room.step(STEP_H)
        step_body(body, room, outside_c, STEP_H, asleep=True)
        if was_lit and not room.fire_lit and fire_out_at is None:
            fire_out_at = hour + slept
        if body.core_c < HYPOTHERMIC_C:
            hypo_hours += STEP_H
        coldest = min(coldest, body.core_c)
        slept += STEP_H

    if fire_out_at is not None:
        log.append(f"{fire_out_at:4.1f} ч: огонь погас, комната начала остывать")
    log.append(f"утро: тело {body.core_c:.1f}°, в комнате {room.felt_c(outside_c):.0f}°, "
               f"усталость {body.fatigue:.0f}, выносливость {body.stamina:.0f}")

    return {"option": option_label, "slept_hours": round(slept, 1), "went_to_bed_at": round(hour, 1),
            "fire_out_at": round(fire_out_at, 1) if fire_out_at is not None else None,
            "hours_below_hypothermic": round(hypo_hours, 1), "coldest_core_c": round(coldest, 1),
            "morning_fatigue": round(body.fatigue), "morning_stamina": round(body.stamina),
            "morning_core_c": round(body.core_c, 1), "fuel_left": round(room.fuel, 1),
            "sleep_refused": refusal, "log": log}


def fresh(cooling: float) -> tuple[Room, Body, EveningBeliefs]:
    return Room(cooling_rate=cooling), Body(), EveningBeliefs(cooling_rate_est=COOLING_RATE_C_PER_H)


def compare(outside_c: float, cooling: float) -> dict:
    runs = []
    for label in ("A: разобрать мебель, топить дольше", "B: лечь раньше на том, что есть",
                  "C: немного работы и ранний сон"):
        room, body, beliefs = fresh(cooling)
        runs.append(play(label, outside_c, room, body, beliefs))
    # A real choice means no option wins on every axis. Check all three, and say plainly if one dominates.
    def dominates(x: dict, y: dict) -> bool:
        return (x["morning_fatigue"] <= y["morning_fatigue"]
                and x["morning_core_c"] >= y["morning_core_c"]
                and x["hours_below_hypothermic"] <= y["hours_below_hypothermic"]
                and (x["morning_fatigue"], -x["morning_core_c"]) != (y["morning_fatigue"], -y["morning_core_c"]))
    dominant = next((r["option"] for r in runs if all(dominates(r, o) for o in runs if o is not r)), None)
    return {"scenario": {"outside_c": outside_c, "cooling_rate_c_per_h": cooling,
                         "night_hours": HOURS_OF_NIGHT},
            "runs": runs,
            "dominant_option": dominant,
            "morning_fatigue_spread": max(r["morning_fatigue"] for r in runs) - min(r["morning_fatigue"] for r in runs),
            "morning_core_spread_c": round(max(r["morning_core_c"] for r in runs)
                                           - min(r["morning_core_c"] for r in runs), 1),
            "reading": (f"«{dominant}» выигрывает по всем показателям — это не выбор, а правильный ответ."
                        if dominant else
                        "Ни один вариант не лучше остальных по всем показателям: цена решения разная."),
            "limitations": [
                "Числа — из документации Hoarbound и заглушки; не баланс TheLull.",
                "Ничего не подгонялось, чтобы варианты вышли равными.",
                "Одна комната, один дом, одна ночь; погода постоянна в течение ночи.",
            ]}


def three_days(outside_c: float, cooling: float, days: int) -> dict:
    room, body, beliefs = fresh(cooling)
    out = []
    for day in range(1, days + 1):
        room = replace(room, heated_offset_c=0.0, fire_lit=False, cooling_rate=cooling)
        considered = options(body, room, beliefs, 0.0)
        pick, why = choose(body, room, beliefs)
        before = dict(beliefs.work_hours_est)
        result = play(pick["option"], outside_c, room, body, beliefs)

        # Morning lesson: the fire did not last as long as expected, or the room went cold faster.
        lesson = ""
        if result["fire_out_at"] is not None and result["fire_out_at"] < HOURS_OF_NIGHT - 1:
            old = beliefs.burn_rate_est
            beliefs.burn_rate_est = min(2.5, beliefs.burn_rate_est * 1.25)
            lesson = f"огонь кончился раньше: расход топлива {old:.2f}→{beliefs.burn_rate_est:.2f} в час"
        elif result["hours_below_hypothermic"] > 0:
            old = beliefs.cooling_rate_est
            beliefs.cooling_rate_est = min(8.0, beliefs.cooling_rate_est * 1.3)
            lesson = f"ночью замёрз: комната остывает быстрее, чем думал ({old:.1f}→{beliefs.cooling_rate_est:.1f})"

        body.fatigue = min(100.0, body.fatigue + 25.0)  # the next day's trip, outside this experiment
        room.fuel = max(room.fuel, 2)  # one day's haul, so the evening question repeats
        out.append({"day": day, "considered": considered, "chose": pick["option"], "why": why,
                    "result": {k: v for k, v in result.items() if k != "log"},
                    "log": result["log"], "lesson": lesson or "ничего нового не узнал",
                    "work_hours_before": before})
    return {"scenario": {"outside_c": outside_c, "cooling_rate_c_per_h": cooling, "days": days},
            "days": out,
            "limitations": ["Поведение модели, не доказательство интереса для игрока.",
                            "Утренняя усталость и добыча следующего дня — заглушки."]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--outside", type=float, default=OUTSIDE_C)
    ap.add_argument("--cooling", type=float, default=COOLING_RATE_C_PER_H)
    ap.add_argument("--json")
    a = ap.parse_args()
    res = three_days(a.outside, a.cooling, a.days) if a.days else compare(a.outside, a.cooling)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
