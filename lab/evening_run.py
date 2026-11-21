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
                      IDLE_FATIGUE_PER_H, SEAL, PACK, SEAL_COOLING_FACTOR, SHORT_WALK, STEP_H, UNDECIDED,
                      RECOVERY_PER_H, WAKE_COLD_C, Body, EveningBeliefs, Room, Tomorrow, choose,
                      options, sleep_refusal, step_body)

OUTSIDE_C = -18.0  # Hoarbound's reference exposure figure; placeholder, not TheLull balance


def play(option_label: str, outside_c: float, room: Room, body: Body, beliefs: EveningBeliefs,
         *, hours_of_night: float = HOURS_OF_NIGHT) -> dict:
    if hours_of_night <= 0:
        raise ValueError("night duration must be positive")
    work = {"A": HEAVY, "B": None, "C": SEAL, "D": PACK}[option_label[0]]
    if work is HEAVY and (not room.has_axe or room.furniture <= 0):
        raise ValueError("нельзя разобрать мебель без топора и доступной мебели")
    if work is SEAL and room.sealed:
        raise ValueError("комната уже утеплена")
    if work is PACK and body.packed:
        raise ValueError("вещи уже собраны")
    if work is not None and body.stamina < work.stamina_cost:
        raise ValueError("недостаточно кратковременной выносливости для работы")
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
            room.sealed = True
            gained = f"комната теперь остывает вдвое медленнее ({room.cooling_rate:.1f}°/ч)"
        elif work is PACK:
            body.packed = True
            gained = "снаряжение и маршрут готовы к выходу"
        else:
            gained = f"{work.fuel} топлива"
        log.append(f"{hour:4.1f} ч: {work.name} — {gained}, "
                   f"выносливость {body.stamina:.0f}, усталость {body.fatigue:.0f}")
    else:
        log.append(f"{hour:4.1f} ч: работать не стал — выносливость {body.stamina:.0f}, "
                   f"усталость {body.fatigue:.0f}")

    refusal = sleep_refusal(room, body, outside_c)
    fuel_at_ignition = room.fuel
    fire_ignition_h = hour
    room.fire_lit = room.fuel > 0
    if refusal in ("слишком холодно, чтобы ложиться", "сначала нужно согреться") and room.fire_lit:
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

    night_hours = max(0.0, hours_of_night - hour)
    fire_out_at, coldest, hypo_hours = None, body.core_c, 0.0
    slept, awake_h, wakes = 0.0, 0.0, []
    burn_rate_lower_bound = None
    asleep = refusal is None
    while slept + awake_h + 1e-8 < night_hours:
        was_lit = room.fire_lit
        # Author's rule: the cold wakes the sleeper, it does not kill them in their sleep.
        if asleep and body.core_c < WAKE_COLD_C:
            asleep = False
            at, woke_at_c = hour + slept + awake_h, body.core_c
            # First wake: seeing an extinguished stove proves only that its
            # initial fuel lasted NO LONGER than elapsed time. Not exact time.
            if (not wakes and not room.fire_lit and room.fuel <= 0
                    and fuel_at_ignition > 0 and at > fire_ignition_h):
                burn_rate_lower_bound = round(fuel_at_ignition / (at - fire_ignition_h), 3)
            if room.fuel > 0 and not room.fire_lit:
                room.fire_lit = True
                wakes.append({"at": round(at, 1), "core_c": round(woke_at_c, 1), "did": "разжёг остаток дров"})
                log.append(f"{at:4.1f} ч: проснулся от холода ({woke_at_c:.1f}°) — разжёг остаток дров")
                asleep = False
            elif not room.fire_lit and room.furniture > 0 and room.has_axe and body.stamina >= HEAVY.stamina_cost and (
                night_hours - slept - awake_h >= HEAVY.hours):
                room.furniture -= 1
                body.stamina = max(0.0, body.stamina - HEAVY.stamina_cost)
                # Work progresses on the SAME game clock as fire and temperature.
                for _ in range(int(round(HEAVY.hours / STEP_H))):
                    room.step(STEP_H)
                    step_body(body, room, outside_c, STEP_H, asleep=False, fatigue_per_h=HEAVY.fatigue_per_h)
                    awake_h += STEP_H
                room.fuel += HEAVY.fuel
                room.fire_lit = True
                wakes.append({"at": round(at, 1), "core_c": round(woke_at_c, 1),
                              "did": "ломал мебель среди ночи"})
                log.append(f"{at:4.1f} ч: проснулся от холода ({woke_at_c:.1f}°) — "
                           f"ломает мебель в темноте, {HEAVY.hours} ч без сна")
                continue
            else:
                why = ("печь ещё горит — ждёт, пока тело согреется" if room.fire_lit
                       else "нет доступного топлива или инструмента — остаётся бодрствовать")
                wakes.append({"at": round(at, 1), "core_c": round(woke_at_c, 1), "did": why})
                log.append(f"{at:4.1f} ч: проснулся от холода ({woke_at_c:.1f}°) — {why}")
        if not asleep and body.core_c >= WAKE_COLD_C + 0.4 and sleep_refusal(room, body, outside_c) is None:
            asleep = True
            log.append(f"{hour + slept + awake_h:4.1f} ч: согрелся — снова лёг")
        room.step(STEP_H)
        step_body(body, room, outside_c, STEP_H, asleep=asleep,
                  fatigue_per_h=0.0 if asleep else IDLE_FATIGUE_PER_H)
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

    observed_burn_rate = None
    fire_elapsed = hours_of_night - fire_ignition_h
    if room.fire_lit and not wakes and fuel_at_ignition > room.fuel and fire_elapsed > 0.25:
        observed_burn_rate = round((fuel_at_ignition - room.fuel) / fire_elapsed, 3)

    return {"option": option_label, "observed_burn_rate": observed_burn_rate,
            "burn_rate_lower_bound": burn_rate_lower_bound,
            "night_elapsed_h": round(hours_of_night, 2),
            "slept_hours": round(slept, 1), "awake_at_night_h": round(awake_h, 1),
            "woke_cold": len(wakes), "wake_events": wakes, "went_to_bed_at": round(hour, 1),
            "fire_out_at": round(fire_out_at, 1) if fire_out_at is not None else None,
            "hours_below_hypothermic": round(hypo_hours, 1), "coldest_core_c": round(coldest, 1),
            "morning_fatigue": round(body.fatigue), "morning_stamina": round(body.stamina),
             "packed_for_morning": body.packed,
            "morning_core_c": round(body.core_c, 1), "fuel_left": round(room.fuel, 1),
            "sleep_refused": refusal, "log": log}


def fresh(cooling: float, fuel: int = 3, recovery: float = RECOVERY_PER_H
          ) -> tuple[Room, Body, EveningBeliefs]:
    return (Room(cooling_rate=cooling, fuel=fuel), Body(fatigue=45.0, recovery_per_h=recovery),
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
        # This command models only the night. Actual departure is in lab.linked_days.
        went = (result["morning_fatigue"] <= after.max_morning_fatigue
                and result["morning_core_c"] >= HYPOTHERMIC_C
                and result["morning_fatigue"] + pick["day_effort_expected"] <= 90.0
                and pick["daylight_overrun_expected"] <= 1e-9)
        out.append({"tomorrow": tomorrow.name, "considered": considered, "chose": pick["option"],
                    "why": why, "gave_up_the_plan_in_the_evening": dropped,
                    "plan_after_evening": after.name,
                    "morning_fatigue": result["morning_fatigue"],
                    "morning_core_c": result["morning_core_c"],
                    "could_leave_in_the_morning": went,
                    "morning_note": ("план выглядит выполнимым (прогноз, не реальный выход)" if went else
                                     "план не проходит ограничения по усталости, теплу или свету"),
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
    """Legacy CLI entry: now uses persistent nights/days, never oracular lessons or free fuel."""
    if days < 1:
        raise ValueError("days must be positive")
    from .linked_days import run_cycle  # local import avoids import cycle with play()
    schedule = (UNDECIDED, EXPEDITION, SHORT_WALK)
    plans = [schedule[i % len(schedule)] for i in range(days)]
    linked = run_cycle(plans, [outside_c] * days, fuel=3, depot_fuel=10, cooling=cooling)
    return {
        "scenario": linked["scenario"],
        "days": [
            {
                "day": d["day"], "considered": [d["forecast"]],
                "chose": d["choice"], "why": d["why"],
                "before_evening": d["before_evening"],
                "result": d["night"], "log": d["night"].get("log", []),
                "lesson": d["lesson"], "daytime": d["daytime"],
                "after_day": d["after_day"]
            }
            for d in linked["days"]
        ],
        "limitations": linked["limits"],
    }


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
