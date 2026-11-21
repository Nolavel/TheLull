"""First connected 24-hour survival loop. Pure Python research harness.

One World, one Agent/Beliefs, one Body and one Room survive across dawns.
`sim.run_day` owns travel/search; `evening_run.play` owns the entire night.
No second weather generator, night billing or synthetic resource replenishment.
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Callable
from collections import Counter
from dataclasses import asdict
from statistics import mean

from .agent import Agent
from .body import DEATH_C, Body
from .evening import Room, Tomorrow, UNDECIDED, SHORT_WALK, choose, options, step_body
from .evening_run import play
from .heat_choice import LIGHT, DecisionProvider, make_heat_decision
from .coupled_microloop import Equipment
from .clothing_followthrough import followup_work
from .overnight_goal_policy import (
    PROTECT, FUEL, WORK, GOALS, RECOVER, FORAGE, FINISH,
    pressure as goal_pressure, choose_morning,
)
from .sim import DEPART_AFTER_DAWN_MIN, DayRecord, Decision, clock, run_day
from .world import DAY_MINUTES, World

STEP_H = 0.25
HEATING_POLICIES = ("dusk", "at_dawn", "on_return", "cold_trigger_36c")


def _light_fire(room: Room, body: Body, events: list[dict], reason: str) -> bool:
    """A decision can use only the current room fuel and observable body state."""
    if body.terminal or room.fire_lit or room.fuel <= 0:
        return False
    room.fire_lit = True
    events.append({"elapsed_minute": round(body.elapsed_minutes, 4),
                   "reason": reason, "fuel_at_ignition": round(room.fuel, 3),
                   "core_at_ignition_c": round(body.core_c, 4)})
    return True


def _shelter_wait(room: Room, body: Body, outside_c: float, minutes: float,
                  *, heating_policy: str = "dusk",
                  ignition_events: list[dict] | None = None,
                  before_tick: Callable[[], None] | None = None,
                  after_tick: Callable[[float, float, float, bool], None] | None = None) -> float:
    """Only actually elapsed minutes are billed, including partial terminal ticks."""
    if minutes < -1e-8:
        raise ValueError("time cannot move backwards")
    left = max(0.0, minutes / 60.0)
    used = 0.0
    while left > 1e-9 and not body.terminal:
        if before_tick is not None:
            before_tick()
        if (heating_policy == "cold_trigger_36c" and body.core_c <= 36.0
                and ignition_events is not None):
            _light_fire(room, body, ignition_events, "observed_core_at_or_below_36c")
        step = min(STEP_H, left)
        core_before = body.core_c
        burning_before = room.fire_lit and room.fuel > 0
        room.step(step)
        actual = step_body(body, room, outside_c, step, asleep=False, fatigue_per_h=2.0)
        if after_tick is not None and actual > 0:
            after_tick(core_before, body.core_c, actual, burning_before)
        if actual <= 0:
            break
        used += actual
        left -= actual
    return used * 60.0


def run(seed: int, days: int = 3, *, variant: str = "B_readable",
        profile: str = "local", intentions: list[Tomorrow] | None = None,
        initial_furniture: int = 2, recheck_policy: bool = True,
        heating_policy: str = "dusk",
        decision_provider: DecisionProvider | None = None,
        carry_night_intent: bool = False,
        goal_policy: str | None = None,
        initial_goal: str = FUEL,
        work_deadline_minute: float = 2880.0) -> dict:
    """Advance one shared state. Partial days are NOT credited as dawns."""
    if days < 1:
        raise ValueError("days must be positive")
    if initial_furniture < 0:
        raise ValueError("furniture must be non-negative")
    if heating_policy not in (*HEATING_POLICIES, "agent"):
        raise ValueError(f"unknown heating policy: {heating_policy}")
    if decision_provider is not None and heating_policy != "agent":
        raise ValueError("human decisions are only accepted in heating_policy=agent")
    if goal_policy not in (None,"adaptive","frozen"):
        raise ValueError("goal_policy must be None/adaptive/frozen")
    if goal_policy is not None and initial_goal not in GOALS:
        raise ValueError("unknown initial goal")
    if goal_policy is not None and (intentions or carry_night_intent):
        raise ValueError("D1.9 cannot be combined with legacy intent controls")
    if work_deadline_minute <= 0:
        raise ValueError("deadline must be positive")
    world = World.load("district_v0", variant)
    agent = Agent(profile, world, allow_rechecks=recheck_policy)
    body = Body()
    room = Room(fuel=world.start_fuel, furniture=initial_furniture)
    # Persistent dry equipment across actual days. The canonical outdoor
    # controller does not yet wet clothing; we do not pretend otherwise.
    gear = Equipment()
    pending_work = goal_policy is not None
    active_goal = initial_goal if goal_policy is not None else None
    previous_goal_report = None
    loot_rng = random.Random(f"{seed}:loot")
    history = []
    end_reason = None
    from_previous_night = None

    for day in range(1, days + 1):
        weather = world.roll_weather(random.Random(f"{seed}:weather:{day}"))
        start_clock = world.dawn_min + (day - 1) * DAY_MINUTES
        start_elapsed = body.elapsed_minutes
        fuel_at_dawn = room.fuel
        core_at_dawn = body.core_c
        fatigue_at_dawn = body.fatigue
        furniture_at_dawn = room.furniture
        fuel_burned_at_dawn = room.burned_fuel_total
        fire_hours_at_dawn = room.fire_hours_total
        day_record = DayRecord(day=day, fuel_morning=room.fuel)
        plan = intentions[(day - 1) % len(intentions)] if intentions else UNDECIDED
        arriving_intent = from_previous_night
        dawn_goal_choice = None
        goal_at_dawn = active_goal
        dawn_pressure = None
        work_action = None
        before_night_goal_pressure = None
        after_night_goal_pressure = None
        overnight_goal_trace = None
        if goal_policy is not None and not body.terminal:
            dawn_pressure = goal_pressure(
                body,room,world,pending_work=pending_work,
                deadline_minute=work_deadline_minute
            )
            if day>1:
                active_goal=(
                    previous_goal_report["after_night"]["goal"]
                    if goal_policy=="adaptive" and previous_goal_report
                    else initial_goal
                )
            goal_at_dawn=active_goal
            dawn_goal_choice=(
                choose_morning(active_goal,body,room,agent,world,
                               pending_work=pending_work,
                               deadline_minute=work_deadline_minute)
                if active_goal is not None else None
            )
            if active_goal==PROTECT:
                plan=SHORT_WALK
        # Preserve the author's explicit plans. Under the opt-in experiment
        # only, a disrupted night can revise an otherwise undecided next day.
        if (carry_night_intent and not intentions and arriving_intent is not None
                and arriving_intent["wants_recovery"]):
            plan = SHORT_WALK
        revised = plan
        proposed = None
        why = "до вечернего выбора не дошёл"
        night = None
        learned = "ночных наблюдений нет"
        evening_trace = None
        night_next_intent = None
        departure = world.dawn_min + max(
            0, DEPART_AFTER_DAWN_MIN - (15 if body.packed else 0)
        )
        return_minute = None
        evening_start = None
        actual_night_h = 0.0
        packed_before_departure = body.packed
        phase = "morning_shelter"
        ignitions: list[dict] = []
        stove_decisions = []
        stove_outcomes = []
        pending = None
        last_prompt_at = None
        last_prompt_core = None

        def settle_previous() -> None:
            nonlocal pending
            if pending is None:
                return
            d, when, before_burn, before_fire_hours, before_core = pending
            outcome = {
                "decision_index": len(stove_decisions) - 1,
                "observed_at_elapsed_minute": round(body.elapsed_minutes, 5),
                "elapsed_since_decision_h": round(
                    (body.elapsed_minutes - when) / 60.0, 5
                ),
                "observed_core_delta_c": round(body.core_c - before_core, 5),
                "realized_fuel_burned": round(
                    room.burned_fuel_total - before_burn, 5
                ),
                "realized_fire_hours": round(
                    room.fire_hours_total - before_fire_hours, 5
                ),
                "fuel_after": round(room.fuel, 5),
                "next_intention": plan.name,
            }
            stove_outcomes.append(outcome)
            d.outcome = (
                f"наблюдение через {(body.elapsed_minutes - when) / 60.0:.2f} ч: "
                f"тело {before_core:.2f}→{body.core_c:.2f}°C; "
                f"печь сожгла {room.burned_fuel_total - before_burn:.3f} топлива "
                f"за {room.fire_hours_total - before_fire_hours:.3f} ч; "
                f"дров осталось {room.fuel:.3f}"
            )
            pending = None

        def decide_stove(point: str, window_h: float,
                         away_h: float = 0.0) -> bool:
            nonlocal pending, last_prompt_at, last_prompt_core
            if body.terminal or room.fire_lit or room.fuel <= 0:
                return False
            settle_previous()
            d = make_heat_decision(
                body, room, agent.beliefs, plan, room.felt_c(world.air_temp_c),
                point, window_h, away_h=away_h, dawn_min=world.dawn_min,
                provider=decision_provider,
            )
            stove_decisions.append(d)
            last_prompt_at = body.elapsed_minutes
            last_prompt_core = body.core_c
            pending = (d, body.elapsed_minutes, room.burned_fuel_total,
                       room.fire_hours_total, body.core_c)
            if d.choice == LIGHT:
                return _light_fire(room, body, ignitions, f"choice:{point}")
            return False

        def poll_stove() -> None:
            if last_prompt_at is None or last_prompt_core is None:
                return
            delta_m = body.elapsed_minutes - last_prompt_at
            # A meaningful second observation, not a 15-minute prompt flood.
            if (delta_m >= 90.0 or
                (delta_m >= 30.0 and last_prompt_core - body.core_c >= 0.65)):
                decide_stove("повторная оценка в убежище", 1.0)

        def observe_thermal(before: float, after: float, used_h: float,
                            burning: bool) -> None:
            if not burning and not room.fire_lit:
                lesson = agent.beliefs.observe_shelter_cooling(
                    before, after, used_h
                )
                if lesson and stove_decisions:
                    stove_decisions[-1].belief_update = lesson

        if heating_policy == "agent":
            # Real initial point: the current fire/fuel/body and the known
            # departure plan; not future weather or unknown house inventory.
            estimated_trip = agent.rank_targets()
            likely_away = (
                (2 * estimated_trip[0]["minutes"] + 30) / 60.0
                if estimated_trip else 0.0
            )
            decide_stove("утро", (departure - world.dawn_min) / 60.0,
                         away_h=likely_away)
        if heating_policy == "at_dawn":
            _light_fire(room, body, ignitions, "first_light")
        _shelter_wait(
            room, body, world.air_temp_c, departure - world.dawn_min,
            heating_policy=heating_policy, ignition_events=ignitions,
            before_tick=poll_stove if heating_policy == "agent" else None,
            after_tick=observe_thermal if heating_policy == "agent" else None,
        )
        fuel_at_departure = room.fuel

        if not body.terminal:
            phase = "trip"
            if (goal_policy is not None and dawn_goal_choice is not None
                    and dawn_goal_choice["choice"]==FINISH):
                phase="shelter_task"
                work_action=followup_work(
                    body,room,world,rest_if_tired=False,gear=gear
                )
                pending_work=pending_work and not work_action["completed"]
                day_record.decisions.append(Decision(
                    time=clock(world.dawn_min+DEPART_AFTER_DAWN_MIN),
                    point="задача в убежище",intention=goal_at_dawn,
                    cues=dawn_goal_choice["cues"],
                    alternatives=dawn_goal_choice["alternatives"],
                    choice=FINISH,reason=dawn_goal_choice["reason"],
                    outcome=f"выполнено={work_action['completed']}; "
                            f"оплачено={work_action['total_minutes']:.2f}мин, "
                            f"stamina={body.stamina:.2f}",
                    belief_update="реальное исполнение без внезапной награды"
                ))
                day_record.next_intention=(
                    "работа выполнена" if work_action["completed"]
                    else "задача осталась открытой"
                )
            else:
                shelter_recovery = (
                    goal_policy is not None
                    and dawn_goal_choice is not None
                    and dawn_goal_choice["choice"]==RECOVER
                ) or bool(
                    carry_night_intent and arriving_intent is not None
                    and arriving_intent["wants_recovery"]
                    and room.fuel > 0
                    and (body.core_c < 35.8 or body.fatigue > 80.0)
                )
                day_record, _ = run_day(
                    world, agent, weather, loot_rng, day, fuel_at_departure,
                    body=body, charge_legacy_night=False,
                    stay_home_for_recovery=shelter_recovery,
                )
                if shelter_recovery and goal_policy is not None:
                    d=day_record.decisions[0]
                    d.intention=goal_at_dawn
                    d.reason=dawn_goal_choice["reason"]
                    d.cues=dawn_goal_choice["cues"]
                    d.alternatives=dawn_goal_choice["alternatives"]
                    d.choice=RECOVER

        if not body.terminal:
            # A returned trip deposits only what actually made it home.
            if day_record.went_out:
                if day_record.actual_return is None:
                    raise AssertionError("nonterminal trip has no actual return")
                elapsed_out = day_record.actual_return - departure
                if elapsed_out < -1e-8:
                    raise ValueError("return precedes departure")
                room.step(elapsed_out / 60.0)
                room.fuel += day_record.carried
                body.packed = False
                return_minute = float(day_record.actual_return)
            else:
                # Real morning task may have billed time after planned departure.
                return_minute=float(world.dawn_min+body.elapsed_minutes-start_elapsed)

            phase = "day_shelter"
            if heating_policy == "on_return":
                _light_fire(room, body, ignitions, "returned_or_stayed_home")
            elif heating_policy == "agent":
                decide_stove("возвращение в убежище", 1.0)
            evening_start = max(float(world.day_length), return_minute)
            _shelter_wait(
                room, body, world.air_temp_c, evening_start - return_minute,
                heating_policy=heating_policy, ignition_events=ignitions,
                before_tick=poll_stove if heating_policy == "agent" else None,
                after_tick=observe_thermal if heating_policy == "agent" else None,
            )

        if not body.terminal:
            actual_night_h = (
                world.dawn_min + DAY_MINUTES - evening_start
            ) / 60.0
            if actual_night_h <= 0:
                end_reason = "не вернулся к следующему рассвету"
            else:
                phase = "evening_and_night"
                proposed, why, revised = choose(
                    body, room, agent.beliefs, plan, world.air_temp_c,
                    daylight_hours=world.daylight_hours,
                    night_hours=actual_night_h
                )
                # Single shared actual outcome, not forecast pretending to
                # be real. Alternatives are forecast from CURRENT beliefs.
                candidate_options = options(
                    body, room, agent.beliefs, plan, world.air_temp_c,
                    daylight_hours=world.daylight_hours,
                    night_hours=actual_night_h
                )
                evening_trace = Decision(
                    time=clock(world.day_length),
                    point="вечер",
                    intention=plan.name,
                    cues=[f"тело {body.core_c:.2f}°C",
                          f"усталость {body.fatigue:.1f}",
                          f"топливо {room.fuel:.2f}",
                          f"план на завтра: {plan.name}"],
                    alternatives=candidate_options,
                    choice=proposed["option"],
                    reason=why,
                )
                if heating_policy == "agent":
                    decide_stove("вечер перед работой", 1.5)
                night_args = {"hours_of_night": actual_night_h}
                if heating_policy == "agent":
                    night_args["automatic_ignition"] = False
                    night_args["on_fire_opportunity"] = (
                        lambda point, hours: decide_stove(point, min(hours, 2.0))
                    )
                if goal_policy is not None:
                    before_night_goal_pressure=goal_pressure(
                        body,room,world,pending_work=pending_work,
                        deadline_minute=work_deadline_minute
                    )
                    night_args["clothing_c"]=gear.clothing_c
                night = play(
                    proposed["option"], world.air_temp_c, room, body,
                    agent.beliefs, **night_args
                )
                if not body.terminal:
                    if night["observed_burn_rate"] is not None:
                        learned = agent.beliefs.observe_burn_rate(
                            night["observed_burn_rate"]
                        )
                    elif night["burn_rate_lower_bound"] is not None:
                        learned = agent.beliefs.observe_rate_lower_bound(
                            night["burn_rate_lower_bound"]
                        )

        settle_previous()
        if evening_trace is not None:
            if night is None:
                evening_trace.outcome = "ночной цикл не был достигнут"
            else:
                evening_trace.outcome = (
                    f"ночь прошла {night['night_elapsed_h']:.2f} ч; "
                    f"пробуждений от холода {night['woke_cold']}; "
                    f"тело {body.core_c:.2f}°C; "
                    f"усталость {body.fatigue:.1f}; "
                    f"топливо осталось {room.fuel:.2f}"
                )
                evening_trace.belief_update = learned

        # The next goal is formed AFTER experiencing this night. On the
        # following dawn this exact record becomes observable incoming intent.
        # It is deliberately a simple policy hypothesis, NOT human agency.
        if not body.terminal:
            disrupted = bool(night and (
                night["woke_cold"] > 0
                or night.get("sleep_refused") in (
                    "слишком холодно, чтобы ложиться", "сначала нужно согреться"
                )
            ))
            wants_recovery = disrupted and room.fuel > 0 and (
                body.core_c < 36.0 or body.fatigue > 75.0
            )
            if wants_recovery:
                intended = "восстановить тепло и силы перед следующей вылазкой"
                origin = "реальный холод и пробуждения прошлой ночью"
            elif day_record.next_intention:
                intended = day_record.next_intention
                origin = "дневной опыт и проверенные доступные запасы"
            else:
                intended = "рассмотреть новый маршрут"
                origin = "прежняя цель остаётся доступной"
            night_next_intent = {
                "intention": intended, "origin": origin,
                "wants_recovery": wants_recovery,
                "night_wakes_observed": night["woke_cold"] if night else 0,
                "core_at_decision_c": round(body.core_c, 4),
                "fatigue_at_decision": round(body.fatigue, 4),
                "fuel_at_decision": round(room.fuel, 4),
            }
        from_previous_night = night_next_intent
        if goal_policy is not None:
            after_night_goal_pressure=goal_pressure(
                body,room,world,pending_work=pending_work,
                deadline_minute=work_deadline_minute
            )
            after_goal=after_night_goal_pressure["goal"]
            def preview(next_goal):
                return (choose_morning(next_goal,body,room,agent,world,
                                       pending_work=pending_work,
                                       deadline_minute=work_deadline_minute)
                        if next_goal is not None and not body.terminal else None)
            chosen_next=preview(after_goal)
            frozen_next=preview(initial_goal)
            pressure_control_next=preview(
                before_night_goal_pressure["goal"]
                if before_night_goal_pressure is not None else None
            )
            overnight_goal_trace={
                "policy":goal_policy,
                "assigned_initial_goal":initial_goal,
                "goal_at_this_dawn":goal_at_dawn,
                "morning_decision":dawn_goal_choice,
                "work_action":work_action,
                "before_night":before_night_goal_pressure,
                "after_night":after_night_goal_pressure,
                "changed_pressure_during_night":bool(
                    before_night_goal_pressure is not None
                    and before_night_goal_pressure["goal"]!=after_goal
                    and after_goal is not None
                ),
                "next_dawn_adaptive_preview":chosen_next,
                "next_dawn_frozen_preview":frozen_next,
                "next_dawn_pre_night_pressure_preview":pressure_control_next,
                "next_goal_causal_reason":after_night_goal_pressure["reason"],
                "night_observed_wakes":night["woke_cold"] if night else None,
                "night_actual_fuel_spent":round(
                    room.burned_fuel_total-fuel_burned_at_dawn,5
                ),
                "no_future_weather_used":True,
            }
            previous_goal_report={"after_night":after_night_goal_pressure}
        elapsed_today = body.elapsed_minutes - start_elapsed
        if body.terminal:
            end_reason = body.terminal_reason
        elif end_reason is None:
            if abs(elapsed_today - DAY_MINUTES) > 1e-5:
                raise AssertionError(
                    f"missing or double-billed time: {elapsed_today} / 1440 minutes"
                )
            if body.fatigue >= 100.0:
                end_reason = "усталость достигла предела"
            elif (room.fuel <= 0 and room.furniture <= 0
                  and not any(v > 0 for v in world.loot.values())):
                end_reason = "исчерпаны доступные в районе источники топлива"

        if room.fuel < -1e-9 or room.furniture < 0 or any(v < 0 for v in world.loot.values()):
            raise AssertionError("world created negative resources")
        complete_dawn = not body.terminal and abs(elapsed_today - DAY_MINUTES) < 1e-5
        elapsed_rounded = round(elapsed_today, 6)
        history.append({
            "day": day, "world_weather": asdict(weather),
            "starting_dawn_minute": start_clock,
            # None is intentional: a partial day must not invent the next dawn.
            "next_dawn_minute": start_clock + DAY_MINUTES if complete_dawn else None,
            "completed_dawn": complete_dawn,
            "phase_at_end": phase,
            "minutes_accounted": elapsed_rounded,
            "stop_at_minute": round(start_clock + elapsed_today, 6),
            "terminal_at_minute": body.terminal_at_minute,
            "departure_minute": round(departure, 3)
                if phase != "morning_shelter" else None,
            "return_minute": round(return_minute, 3)
                if return_minute is not None else None,
            "night_start_minute": round(evening_start, 3)
                if evening_start is not None and phase == "evening_and_night" else None,
            "night_hours": round(actual_night_h, 6),
            "fuel_at_dawn": round(fuel_at_dawn, 3),
            "fuel_at_departure": round(fuel_at_departure, 3),
            "arriving_intention": arriving_intent,
            "goal_continuity":overnight_goal_trace,
            "pending_work_at_next_dawn":pending_work if goal_policy is not None else None,
            "gear_wetness_at_next_dawn":gear.wetness if goal_policy is not None else None,
            "night_formed_next_intention": night_next_intent,
            "evening_decision": asdict(evening_trace) if evening_trace else None,
            "stove_decisions": [asdict(d) for d in stove_decisions],
            "stove_outcomes": stove_outcomes,
            "fuel_burned_today": round(
                room.burned_fuel_total - fuel_burned_at_dawn, 5
            ),
            "fire_hours_today": round(
                room.fire_hours_total - fire_hours_at_dawn, 5
            ),
            "heating_policy": heating_policy,
            "early_ignitions": ignitions,
            "fuel_delivered": day_record.carried if return_minute is not None
                and day_record.went_out else 0,
            "carried": day_record.carried,
            "fuel_next_dawn": round(room.fuel, 3),
            "furniture_at_dawn": furniture_at_dawn,
            "furniture_next_dawn": room.furniture,
            "core_at_dawn": round(core_at_dawn, 4),
            "core_next_dawn": round(body.core_c, 4),
            "fatigue_at_dawn": round(fatigue_at_dawn, 3),
            "fatigue_next_dawn": round(body.fatigue, 3),
            "packed_before_departure": packed_before_departure,
            "day_trip": {
                "went_out": day_record.went_out,
                "target": day_record.target,
                "carried": day_record.carried,
                "search_minutes": day_record.search_minutes,
                "recheck_searches": day_record.recheck_searches,
                "empty_searches": day_record.empty_searches,
                "terminal_minute": day_record.terminal_minute,
                "events": day_record.events,
                "next_intention": day_record.next_intention,
                "decisions": [asdict(d) for d in day_record.decisions],
            },
            "evening": {
                "intention": plan.name, "revision": revised.name,
                "chose": proposed["option"] if proposed else "NOT_REACHED",
                "why": why,
                "predicted_ready": (proposed["ready_for_tomorrow_expected"]
                                    if proposed else None),
                "lesson": learned,
            },
            "night": night if night is not None else {
                "night_elapsed_h": 0.0,
                "slept_hours": 0.0,
                "woke_cold": 0,
                "fire_out_at": None,
                "terminal": body.terminal_reason,
            },
            "beliefs_after": {
                "cooling_rate_est": round(agent.beliefs.cooling_rate_est, 4),
                "burn_rate_est": round(agent.beliefs.burn_rate_est, 4),
                "known_locations": sorted(agent.beliefs.loot),
                "estimated_loot": dict(sorted(agent.beliefs.loot.items())),
                "confirmed_empty": sorted(agent.beliefs.confirmed_empty),
            },
            "remaining_loot": dict(sorted(world.loot.items())),
            "end_reason": end_reason,
        })
        if end_reason:
            break

    return {
        "seed": seed, "variant": variant, "profile": profile,
        "days_requested": days,
        "days_started": len(history),
        "days_completed": sum(d["completed_dawn"] for d in history),
        "elapsed_minutes": round(body.elapsed_minutes, 6),
        "elapsed_days": round(body.elapsed_minutes / DAY_MINUTES, 6),
        "terminal_at_minute": body.terminal_at_minute,
        "recheck_policy": recheck_policy,
        "heating_policy": heating_policy,
        "carry_night_intent": carry_night_intent,
        "goal_policy":goal_policy,
        "assigned_initial_goal":initial_goal if goal_policy is not None else None,
        "pending_work_at_end":pending_work if goal_policy is not None else None,
        "decision_source": (
            "human" if decision_provider is not None
            else "agent" if heating_policy == "agent"
            else "scripted_baseline"
        ),
        "end_reason": end_reason, "history": history,
        "limits": [
            "Partial days are counted in elapsed_minutes, NOT days_completed.",
            "The terminal threshold is a game-model stop, not a physiological prediction.",
            "Heat policies are controlled counterfactuals, not a validated agent choice.",
            "Night-to-dawn replan is opt-in experimental policy, not human intent.",
            "Daytime choices still optimize fuel, not water/food.",
            "A fixed dawn+dusk schedule, no interpolated weather across midnight.",
            "No resource respawn or balance calibration.",
            "Legacy sim.run and standalone linked_days remain separate baselines.",
            "D1.9 opt-in goal continuity carries dry Equipment; outdoor controller does not implement wet clothing changes.",
            "D1.9 uses a research heuristic for goal priorities, not emergent human desires.",
            "Next-dawn preview uses same real post-night state, not the researcher's future weather."
        ],
    }


def study(seeds: int = 30, days: int = 7) -> dict:
    runs = [run(seed=i, days=days) for i in range(1, seeds + 1)]
    completed = [r["days_completed"] for r in runs]
    return {
        "seeds": seeds, "days": days,
        "mean_days_completed": round(mean(completed), 2),
        "end_reasons": dict(Counter(r["end_reason"] or "horizon" for r in runs)),
        "evening_choices": dict(Counter(d["evening"]["chose"][0]
                                for r in runs for d in r["history"])),
        "mean_trips": round(mean(sum(d["day_trip"]["went_out"] for d in r["history"])
                                 for r in runs), 2),
        "one_example": runs[0]["history"], "limits": runs[0]["limits"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--seeds", type=int, default=0)
    parser.add_argument("--variant", choices=("A_safe", "B_readable", "C_unreadable"),
                        default="B_readable")
    parser.add_argument("--profile", choices=("local", "novice"), default="local")
    parser.add_argument("--json")
    args = parser.parse_args()
    result = study(args.seeds, args.days) if args.seeds else run(
        args.seed, args.days, variant=args.variant, profile=args.profile)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
