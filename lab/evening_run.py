"""Run the evening cycle: force each option, or let the player choose for three days.

  python3 -m lab.evening_run --compare            # A/B/C under identical weather
  python3 -m lab.evening_run --days 3             # the player chooses; beliefs update from the morning
  python3 -m lab.evening_run --compare --cooling 6  # one factor: a room that loses heat twice as fast
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace

from .evening import (COOLING_RATE_C_PER_H, EXPEDITION, HEAVY, HOURS_OF_NIGHT, HYPOTHERMIC_C,
                      IDLE_FATIGUE_PER_H, SEAL, SEAL_COOLING_FACTOR, SHORT_WALK, STEP_H, UNDECIDED,
                      RECOVERY_PER_H, WAKE_COLD_C, Body, EveningBeliefs, Room, Tomorrow, choose,
                      options, sleep_refusal, step_body)

OUTSIDE_C = -18.0  # Hoarbound's reference exposure figure; placeholder, not TheLull balance


def play(option_label: str, outside_c: float, room: Room, body: Body, beliefs: EveningBeliefs) -> dict:
    work = {"A": HEAVY, "B": None, "C": SEAL}[option_label[0]]
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
        if work is HEAVY:
            room.furniture = max(0, room.furniture - 1)
        if work is SEAL:
            room.cooling_rate *= SEAL_COOLING_FACTOR
            gained = f"комната теперь остывает вдвое медленнее ({room.cooling_rate:.1f}°/ч)"
        else:
            gained = f"{work.fuel} топлива"
        log.append(f"{hour:4.1f} ч: {work.name} — {gained}, "
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
    slept, awake_h, wakes = 0.0, 0.0, []
    while slept + awake_h < night_hours:
        was_lit = room.fire_lit
        asleep = True
        # Author's rule: the cold wakes the sleeper, it does not kill them in their sleep.
        if body.core_c < WAKE_COLD_C:
            at, woke_at_c = hour + slept + awake_h, body.core_c
            if room.fuel > 0 and not room.fire_lit:
                room.fire_lit = True
                wakes.append({"at": round(at, 1), "core_c": round(woke_at_c, 1), "did": "разжёг остаток дров"})
                log.append(f"{at:4.1f} ч: проснулся от холода ({woke_at_c:.1f}°) — разжёг остаток дров")
                asleep = False
            elif room.furniture > 0:
                room.furniture -= 1
                room.fuel += HEAVY.fuel
                room.fire_lit = True
                body.stamina = max(0.0, body.stamina - HEAVY.stamina_cost)
                body.fatigue = min(100.0, body.fatigue + HEAVY.fatigue_per_h * HEAVY.hours)
                step_body(body, room, outside_c, HEAVY.hours, asleep=False, fatigue_per_h=0.0)
                awake_h += HEAVY.hours
                wakes.append({"at": round(at, 1), "core_c": round(woke_at_c, 1),
                              "did": "ломал мебель среди ночи"})
                log.append(f"{at:4.1f} ч: проснулся от холода ({woke_at_c:.1f}°) — "
                           f"ломает мебель в темноте, {HEAVY.hours} ч без сна")
                continue
            else:
                wakes.append({"at": round(at, 1), "core_c": round(woke_at_c, 1),
                              "did": "жечь нечего — сидит до утра"})
                log.append(f"{at:4.1f} ч: проснулся от холода ({woke_at_c:.1f}°) — жечь нечего, "
                           f"досиживает ночь без сна")
                while slept + awake_h < night_hours:
                    room.step(STEP_H)
                    step_body(body, room, outside_c, STEP_H, asleep=False, fatigue_per_h=IDLE_FATIGUE_PER_H)
                    awake_h += STEP_H
                    coldest = min(coldest, body.core_c)
                    if body.core_c < HYPOTHERMIC_C:
                        hypo_hours += STEP_H
                break
        room.step(STEP_H)
        step_body(body, room, outside_c, STEP_H, asleep=asleep)
        if asleep:
            slept += STEP_H
        else:
            awake_h += STEP_H
        if was_lit and not room.fire_lit and fire_out_at is None:
            fire_out_at = hour + slept + awake_h
            log.append(f"{fire_out_at:4.1f} ч: огонь погас, комната начала остывать")
        if body.core_c < HYPOTHERMIC_C:
            hypo_hours += STEP_H
        coldest = min(coldest, body.core_c)

    log.append(f"утро: тело {body.core_c:.1f}°, в комнате {room.felt_c(outside_c):.0f}°, "
               f"усталость {body.fatigue:.0f}, выносливость {body.stamina:.0f}, "
               f"спал {slept:.1f} ч" + (f", не спал {awake_h:.1f} ч" if awake_h else ""))

    return {"option": option_label, "slept_hours": round(slept, 1), "awake_at_night_h": round(awake_h, 1),
            "woke_cold": len(wakes), "wake_events": wakes, "went_to_bed_at": round(hour, 1),
            "fire_out_at": round(fire_out_at, 1) if fire_out_at is not None else None,
            "hours_below_hypothermic": round(hypo_hours, 1), "coldest_core_c": round(coldest, 1),
            "morning_fatigue": round(body.fatigue), "morning_stamina": round(body.stamina),
            "morning_core_c": round(body.core_c, 1), "fuel_left": round(room.fuel, 1),
            "sleep_refused": refusal, "log": log}


def fresh(cooling: float, fuel: int = 3, recovery: float = RECOVERY_PER_H
          ) -> tuple[Room, Body, EveningBeliefs]:
    return (Room(cooling_rate=cooling, fuel=fuel), Body(recovery_per_h=recovery),
            EveningBeliefs(cooling_rate_est=COOLING_RATE_C_PER_H, recovery_est=recovery))


def viable(run: dict) -> bool:
    """An option that ends the night hypothermic is not an alternative, whatever its other numbers."""
    return run["morning_core_c"] >= HYPOTHERMIC_C


def compare(outside_c: float, cooling: float, fuel: int = 3) -> dict:
    runs = []
    for label in ("A: разобрать мебель, топить дольше", "B: лечь раньше на том, что есть",
                  "C: утеплить комнату и лечь раньше"):
        room, body, beliefs = fresh(cooling, fuel)
        runs.append(play(label, outside_c, room, body, beliefs))

    ok = [r for r in runs if viable(r)]

    def outcome(r: dict) -> tuple[float, float, float]:
        return (-r["morning_fatigue"], r["morning_core_c"], -r["hours_below_hypothermic"])

    def dominates(x: dict, y: dict) -> bool:
        """Better or equal on every axis, and strictly better on at least one."""
        a, b = outcome(x), outcome(y)
        return all(i >= j for i, j in zip(a, b)) and a != b

    # The front is what a player could sensibly argue for: nothing else beats it outright.
    front = [r for r in ok if not any(dominates(o, r) for o in ok if o is not r)]
    dominant = front[0]["option"] if len(front) == 1 and len(ok) > 1 else None

    if len(ok) <= 1:
        verdict = "одна вынужденная работа"
        reading = (f"Пережить ночь даёт только «{ok[0]['option']}»" if ok
                   else "Ни один вариант не доводит до утра без переохлаждения") + " — это не выбор."
    elif dominant:
        verdict = "правильный ответ"
        reading = f"«{dominant}» не хуже остальных ни по одной оси — это не выбор."
    elif len({outcome(r) for r in front}) == 1:
        verdict = "давления нет"
        reading = "Лучшие варианты дают одинаковое утро — решение ни на что не влияет."
    else:
        verdict = "настоящий выбор"
        reading = ("Пригодных вариантов больше одного, и они расходятся по цене: "
                   + "; ".join(f"{r['option'][:1]} — усталость {r['morning_fatigue']}, тело {r['morning_core_c']}°"
                               for r in front))

    return {"scenario": {"outside_c": outside_c, "cooling_rate_c_per_h": cooling,
                         "start_fuel": fuel, "night_hours": HOURS_OF_NIGHT},
            "runs": runs,
            "viable_options": [r["option"] for r in ok],
            "front_options": [r["option"] for r in front],
            "dominant_option": dominant,
            "verdict": verdict,
            "reading": reading,
            "limitations": [
                "Числа — из документации Hoarbound и заглушки; не баланс TheLull.",
                "Ничего не подгонялось, чтобы варианты вышли равными.",
                "Одна комната, один дом, одна ночь; погода постоянна в течение ночи.",
            ]}


def sweep(cooling: float) -> dict:
    """Where does a choice exist at all? Cold and starting fuel, one grid, no tuning."""
    rows = []
    for outside in (-24, -18, -12, -6, -2):
        for fuel in (3, 5, 7):
            res = compare(outside, cooling, fuel)
            rows.append({"outside_c": outside, "start_fuel": fuel, "verdict": res["verdict"],
                         "viable": [o[:1] for o in res["viable_options"]],
                         "morning_core_c": {r["option"][:1]: r["morning_core_c"] for r in res["runs"]}})
    real = [r for r in rows if r["verdict"] == "настоящий выбор"]
    return {"scenario": {"cooling_rate_c_per_h": cooling},
            "rows": rows,
            "cells_with_a_real_choice": len(real),
            "reading": ("Выбор живёт в полосе между «слишком холодно, выход один» и «тепло, решение не важно»."
                        if real else "Ни в одной клетке сетки выбора нет."),
            "limitations": ["Сетка грубая; это карта условий, а не баланс."]}


def plans(outside_c: float, cooling: float, fuel: int, recovery: float = RECOVERY_PER_H) -> dict:
    """Same house, same weather, same fuel — three different plans for tomorrow. Does the evening change?"""
    out = []
    for tomorrow in (SHORT_WALK, EXPEDITION, UNDECIDED):
        room, body, beliefs = fresh(cooling, fuel, recovery)
        considered = options(body, room, beliefs, tomorrow, outside_c)
        pick, why, after = choose(body, room, beliefs, tomorrow, outside_c)
        result = play(pick["option"], outside_c, room, body, beliefs)
        dropped = after.name != tomorrow.name
        went = result["morning_fatigue"] <= after.max_morning_fatigue
        out.append({"tomorrow": tomorrow.name, "considered": considered, "chose": pick["option"],
                    "why": why, "gave_up_the_plan_in_the_evening": dropped,
                    "plan_after_evening": after.name,
                    "morning_fatigue": result["morning_fatigue"],
                    "morning_core_c": result["morning_core_c"],
                    "went_in_the_morning": went,
                    "morning_note": ("вышел по плану" if went else
                                     f"утром отказался: усталость {result['morning_fatigue']} "
                                     f"выше предела {after.max_morning_fatigue:.0f}"),
                    "log": result["log"]})
    distinct = {r["chose"] for r in out}
    return {"scenario": {"outside_c": outside_c, "cooling_rate_c_per_h": cooling, "start_fuel": fuel,
                         "recovery_per_h": recovery},
            "plans": out,
            "distinct_evening_choices": len(distinct),
            "reading": ("Разные планы на завтра дают разный вечер." if len(distinct) > 1 else
                        "План на завтра вечер не изменил: выбор пока определяется только ночью."),
            "limitations": ["Правило выбора не сопоставляет план с вариантом напрямую: план задаёт лишь то, "
                            "сколько отдыха игрок считает нужным.",
                            "Завтрашняя вылазка не моделируется — проверяется только готовность к ней."]}


def three_days(outside_c: float, cooling: float, days: int) -> dict:
    room, body, beliefs = fresh(cooling)
    out = []
    for day in range(1, days + 1):
        room = replace(room, heated_offset_c=0.0, fire_lit=False, cooling_rate=cooling)
        considered = options(body, room, beliefs, UNDECIDED, outside_c)
        pick, why, _ = choose(body, room, beliefs, UNDECIDED, outside_c)
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
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--plans", action="store_true")
    ap.add_argument("--fuel", type=int, default=3)
    ap.add_argument("--recovery", type=float, default=RECOVERY_PER_H)
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--outside", type=float, default=OUTSIDE_C)
    ap.add_argument("--cooling", type=float, default=COOLING_RATE_C_PER_H)
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.sweep:
        res = sweep(a.cooling)
    elif a.plans:
        res = plans(a.outside, a.cooling, a.fuel, a.recovery)
    elif a.days:
        res = three_days(a.outside, a.cooling, a.days)
    else:
        res = compare(a.outside, a.cooling, a.fuel)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
