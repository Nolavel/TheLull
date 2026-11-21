"""The one body and the one thermal model, shared by the day and by the night.

Initial model by Claude, now maintained by Codex. Before this, the trip tracked an abstract `warmth` 0..100 that reset every morning, while
the evening tracked `core_c` in degrees — two sources of truth about the same person. Everything that
touches body temperature now goes through `step_core` here, outdoors and indoors alike.

The shape and the coefficients come from Hoarbound's `docs/technical/THERMAL_MODEL.md` (patterns, not code):
felt temperature, then clothing and basal heat on top, then cooling or rewarming billed per in-game hour.
The two coefficients are solved from Hoarbound's documented behaviour — about 1.5 °C of core lost per hour
exposed at -18 °C dry, and a sheltered fire bringing 35 °C back to 37 °C in roughly two hours — not tuned
by hand. Placeholders, not TheLull balance.
"""
from __future__ import annotations

from dataclasses import dataclass

COMFORT_C = 12.0
BASAL_HEAT_C = 5.0  # load-bearing: without it no configuration rewarms (Hoarbound §2)
CLOTHING_INSULATION_C = 6.0
COOLING_COEF = 0.079
REWARM_COEF = 0.167

START_CORE_C = 37.0
HYPOTHERMIC_C = 35.0
WAKE_COLD_C = 35.5  # author's rule: the cold wakes the sleeper, it does not kill them asleep
DEATH_C = 28.8  # Hoarbound: death after about 5.5 h of exposure at -18 °C

RECOVERY_PER_H = 6.0  # fatigue paid back by an hour of warm sleep
IDLE_FATIGUE_PER_H = 2.0  # awake and doing nothing in particular
TRAVEL_FATIGUE_PER_H = 4.0  # walking with a load


@dataclass
class Body:
    """Carried across days. Nothing resets it at dawn — that was the continuity hole."""

    core_c: float = START_CORE_C
    fatigue: float = 0.0  # 0 rested, 100 spent
    stamina: float = 100.0
    recovery_per_h: float = RECOVERY_PER_H
    packed: bool = False  # One-use evening preparation survives through the night until departure.
    # Monotonic stop: reached once, never reset by subsequent heating.
    terminal_reason: str | None = None
    terminal_at_minute: float | None = None  # elapsed simulation minutes since initial dawn
    elapsed_minutes: float = 0.0
    last_step_hours: float = 0.0  # actual billed interval (may end inside a time step)

    @property
    def terminal(self) -> bool:
        return self.terminal_reason is not None

    def hours_until_terminal(self, felt_c: float, hours: float,
                             clothing_c: float = CLOTHING_INSULATION_C) -> float:
        """Clip a proposed interval at the FIRST crossing of the terminal boundary."""
        if hours < 0:
            raise ValueError("time cannot move backwards")
        if self.terminal:
            return 0.0
        thermal = effective_c(felt_c, clothing_c)
        cooling_rate = max(0.0, COMFORT_C - thermal) * COOLING_COEF
        if cooling_rate == 0:
            return hours
        return min(hours, max(0.0, (self.core_c - DEATH_C) / cooling_rate))

    def stamina_recovery_per_h(self) -> float:
        """Fatigue slows breath coming back (Hoarbound: recovery pace x energy)."""
        return 60.0 * max(0.2, 1.0 - self.fatigue / 100.0)

    def is_hypothermic(self) -> bool:
        return self.core_c < HYPOTHERMIC_C

    def must_wake(self) -> bool:
        return self.core_c < WAKE_COLD_C


def effective_c(felt_c: float, clothing_c: float = CLOTHING_INSULATION_C) -> float:
    """What the body actually has to work with: felt temperature plus insulation plus metabolism."""
    return felt_c + clothing_c + BASAL_HEAT_C


def step_core(body: Body, felt_c: float, hours: float, clothing_c: float = CLOTHING_INSULATION_C) -> float:
    """The only place core temperature changes. Returns the change in degrees."""
    before = body.core_c
    body.last_step_hours = 0.0
    if body.terminal:
        return 0.0
    used = body.hours_until_terminal(felt_c, hours, clothing_c)
    effective = effective_c(felt_c, clothing_c)
    if effective < COMFORT_C:
        body.core_c = max(DEATH_C, body.core_c - (COMFORT_C - effective) * COOLING_COEF * used)
    else:
        body.core_c = min(START_CORE_C, body.core_c + (effective - COMFORT_C) * REWARM_COEF * used)
    body.last_step_hours = used
    body.elapsed_minutes += used * 60.0
    if body.core_c <= DEATH_C + 1e-9:
        body.core_c = DEATH_C
        body.terminal_reason = "температурный предел"
        body.terminal_at_minute = body.elapsed_minutes
    return body.core_c - before


def step_fatigue(body: Body, hours: float, *, asleep: bool, per_hour: float = IDLE_FATIGUE_PER_H) -> None:
    """Sleep pays fatigue back; being cold while asleep eats most of that payment."""
    if asleep:
        recovered = body.recovery_per_h * hours
        if body.core_c < HYPOTHERMIC_C:
            recovered *= 0.25
        elif body.core_c < 36.0:
            recovered *= 0.6
        body.fatigue = max(0.0, body.fatigue - recovered)
        body.stamina = min(100.0, body.stamina + body.stamina_recovery_per_h() * hours)
    else:
        body.fatigue = min(100.0, body.fatigue + per_hour * hours)
        body.stamina = min(100.0, body.stamina + body.stamina_recovery_per_h() * hours * 0.5)
