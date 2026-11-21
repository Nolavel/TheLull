"""An explicit, observable stove decision — not a prescribed ignition time.

The deliberator sees ONLY the present body, room, elapsed time, known plan and
learned beliefs. It cannot inspect unsearched loot, next day's weather, or run a
physical counterfactual on the true future. No free actions or future oracle.
"""
from __future__ import annotations

from typing import Callable

from .agent import Beliefs
from .body import Body, WAKE_COLD_C
from .evening import Room, Tomorrow
from .sim import Decision, clock

LIGHT, SAVE = "топить сейчас", "сохранить топливо"
DecisionProvider = Callable[[Decision], str]


def make_heat_decision(
    body: Body, room: Room, beliefs: Beliefs, plan: Tomorrow,
    observed_room_c: float, phase: str, horizon_h: float,
    *, away_h: float = 0.0, dawn_min: int = 480,
    provider: DecisionProvider | None = None,
) -> Decision:
    """Produce both alternatives, their estimated costs, and a reason.

    horizon_h is the interval until the NEXT opportunity the actor expects
    to assess shelter conditions (not a future environmental prediction).
    away_h is the anticipated absence from home, if currently preparing to
    leave. Neither knows weather or actual hidden loot.
    """
    if body.terminal:
        raise ValueError("terminal body cannot decide")
    if room.fuel <= 0 or room.fire_lit:
        raise ValueError("no meaningful ignition choice without fuel and an unlit stove")
    horizon_h = max(0.25, min(4.0, horizon_h))
    cooling = max(0.05, beliefs.shelter_core_cooling_est)
    before = body.core_c
    projected_core = before - cooling * horizon_h
    # The present room state is an observable cue, not a prediction of weather.
    cold_margin = max(0.0, WAKE_COLD_C + 0.5 - projected_core)
    # One prior for the felt benefit of lighting the stove; learned heat data
    # can update it later, but no real Room.step() forecast is run here.
    heat_benefit = min(2.5, beliefs.stove_effect_est / 8.0) * horizon_h
    residual_cold = max(0.0, cold_margin - heat_benefit)
    # Burning while away costs fuel without heating the travelling body.
    cost_hours = horizon_h + max(0.0, away_h)
    expected_burn = min(room.fuel, beliefs.burn_rate_est * cost_hours)
    save_cost = cold_margin * 6.0
    light_cost = residual_cold * 6.0 + expected_burn * (
        2.5 + 0.10 * plan.hours_out
    )
    # If the stove is too cold to sleep by now, delay is itself costly.
    if phase in ("before_sleep", "cold_wake") and observed_room_c < 5.0:
        save_cost += 8.0
    options = [
        {"option": LIGHT, "available": True,
         "expected_fuel_spent": round(expected_burn, 3),
         "expected_core_c_after_window": round(
             max(projected_core, before - max(0.0, cooling * horizon_h - heat_benefit)), 3
         ),
         "expected_cost": round(light_cost, 3),
         "basis": "обогрев сейчас, цена в конечных дровах"},
        {"option": SAVE, "available": True,
         "expected_fuel_spent": 0.0,
         "expected_core_c_after_window": round(projected_core, 3),
         "expected_cost": round(save_cost, 3),
         "basis": "дрова останутся, но тело продолжит остывать"},
    ]
    heuristic = LIGHT if light_cost < save_cost else SAVE
    t = clock(dawn_min + body.elapsed_minutes)
    reason = (f"сравнил оценку холода {save_cost:.2f} и расход топлива "
              f"{light_cost:.2f}; ожидал пересмотр через {horizon_h:.2f} ч")
    decision = Decision(
        time=t, point="печь:" + phase, intention="обогреться или сохранить конечное топливо",
        cues=[
            f"тело сейчас {body.core_c:.2f} °C",
            f"комната сейчас {observed_room_c:.2f} °C",
            f"топлива сейчас {room.fuel:.3f}",
            f"ожидаемый расход {beliefs.burn_rate_est:.3f} ед/ч",
            f"предполагаемое охлаждение тела {cooling:.3f} °C/ч",
            f"план на завтра: {plan.name}",
            f"ожидаемая разлука с печью {max(0.0, away_h):.2f} ч",
        ], alternatives=options, choice=heuristic, reason=reason,
    )
    if provider is not None:
        requested = provider(decision)
        resolved = {"light": LIGHT, "save": SAVE, LIGHT: LIGHT, SAVE: SAVE}.get(requested)
        if resolved is None:
            raise ValueError("expected light/save; choices must be explicit")
        decision.choice = resolved
        decision.reason += "; решение живого участника (не агентская эвристика)"
    return decision
