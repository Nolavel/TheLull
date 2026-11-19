"""Evening cycle: work → heat the room → night → morning.

Structure taken from Hoarbound (patterns, not code, not approved balance):
- `docs/technical/THERMAL_MODEL.md`: everything billed per in-game hour; a room has passive warmth plus
  `max_heated_offset` the player *earns* with a fire — warmth accumulates at a rate up to a cap and bleeds
  back once the fire dies; indoors kills the wind-chill term; `basal_heat` is load-bearing, because without
  it no configuration lets the body rewarm at all (Hoarbound found this on a debug chart).
- `scripts/systems/save/sleep_controller.gd`: sleep is refused with a named reason, not silently.
- `scripts/.../StaminaManager.gd` + `docs/research/xk/APPLIED_2026-11-13_...`: stamina (breath, back in
  seconds) and fatigue (energy, back over a night) are separate; fatigue slows stamina recovery.
  Cold does **not** touch stamina in Hoarbound — that was left as an owner decision, so it is not modelled here.
- `scripts/systems/actions/time_costed_action_system.gd`: a long action owns elapsed game time; the world
  keeps running while it happens.

Numbers are Hoarbound's documented tuning or plain placeholders. Nothing here is TheLull balance, and
nothing was tuned to make the three options come out even — if one dominates, the report says so.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

HOURS_OF_NIGHT = 10.0
STEP_H = 0.25

# --- room (Hoarbound ThermalZone shape) ---------------------------------
PASSIVE_OFFSET_C = 3.0  # a roof and walls, no fire: Hoarbound's "ruin with a roof, maybe +3"
MAX_HEATED_OFFSET_C = 12.0  # the part the player earns
HEATING_RATE_C_PER_H = 6.0
COOLING_RATE_C_PER_H = 3.0
FUEL_BURN_PER_H = 1.0

# --- body ---------------------------------------------------------------
COMFORT_C = 12.0
BASAL_HEAT_C = 5.0  # load-bearing: without it nothing rewarms (Hoarbound §2)
CLOTHING_INSULATION_C = 6.0
# A lit stove is both a zone heater and a point heat source beside the sleeper; Hoarbound sums the two,
# and without that term there is no reachable configuration where the body rewarms at -18 °C.
HEAT_SOURCE_OFFSET_C = 10.0
# Both coefficients are solved from Hoarbound's documented behaviour, not picked by hand:
# 1.5 °C/h lost exposed at -18 °C dry; a sheltered fire brings 35 °C back to 37 °C in about two hours.
COOLING_COEF = 0.079
REWARM_COEF = 0.167
START_CORE_C = 37.0
HYPOTHERMIC_C = 35.0
DEATH_C = 28.8  # Hoarbound: death after about 5.5 h of that exposure

# --- work ---------------------------------------------------------------
@dataclass(frozen=True)
class Work:
    name: str
    hours: float
    fuel: int
    stamina_cost: float
    fatigue_per_h: float


HEAVY = Work("разобрать мебель", 1.5, 4, 55.0, 7.0)
MODERATE = Work("распилить то, что уже сломано", 0.75, 2, 25.0, 4.5)
IDLE_FATIGUE_PER_H = 2.0  # just being awake and cold


@dataclass
class Body:
    core_c: float = START_CORE_C
    stamina: float = 100.0
    fatigue: float = 45.0  # 0 = rested, 100 = spent; evening after a trip

    def stamina_recovery_per_h(self) -> float:
        """Fatigue slows breath coming back (Hoarbound: recovery pace × energy)."""
        return 60.0 * max(0.2, 1.0 - self.fatigue / 100.0)


@dataclass
class Room:
    heated_offset_c: float = 0.0
    fuel: int = 3
    fire_lit: bool = False
    cooling_rate: float = COOLING_RATE_C_PER_H

    def felt_c(self, outside_c: float) -> float:
        # Indoors the wind-chill term is gone entirely (Hoarbound §4). What is left: the structure's passive
        # warmth, the warmth the room has accumulated, and the stove itself while it burns.
        source = HEAT_SOURCE_OFFSET_C if self.fire_lit and self.fuel > 0 else 0.0
        return outside_c + PASSIVE_OFFSET_C + self.heated_offset_c + source

    def step(self, hours: float) -> None:
        if self.fire_lit and self.fuel > 0:
            self.fuel -= FUEL_BURN_PER_H * hours
            self.heated_offset_c = min(MAX_HEATED_OFFSET_C, self.heated_offset_c + HEATING_RATE_C_PER_H * hours)
            if self.fuel <= 0:
                self.fuel, self.fire_lit = 0, False
        else:
            self.heated_offset_c = max(0.0, self.heated_offset_c - self.cooling_rate * hours)


def step_body(body: Body, room: Room, outside_c: float, hours: float, asleep: bool,
              fatigue_per_h: float = 0.0) -> None:
    effective = room.felt_c(outside_c) + CLOTHING_INSULATION_C + BASAL_HEAT_C
    if effective < COMFORT_C:
        body.core_c = max(DEATH_C, body.core_c - (COMFORT_C - effective) * COOLING_COEF * hours)
    else:
        body.core_c = min(START_CORE_C, body.core_c + (effective - COMFORT_C) * REWARM_COEF * hours)
    if asleep:
        # Sleep pays back fatigue, but being cold while asleep eats the recovery (not a separate formula:
        # the same core temperature that the thermal model produced).
        recovered = 6.0 * hours
        if body.core_c < HYPOTHERMIC_C:
            recovered *= 0.25
        elif body.core_c < 36.0:
            recovered *= 0.6
        body.fatigue = max(0.0, body.fatigue - recovered)
        body.stamina = min(100.0, body.stamina + body.stamina_recovery_per_h() * hours)
    else:
        body.fatigue = min(100.0, body.fatigue + fatigue_per_h * hours)
        body.stamina = min(100.0, body.stamina + body.stamina_recovery_per_h() * hours * 0.5)


def sleep_refusal(room: Room, body: Body, outside_c: float) -> str | None:
    """Named reason, as Hoarbound's SleepController does. Not a save gate: the lab never blocks progress."""
    if room.felt_c(outside_c) < 5.0:
        return "слишком холодно, чтобы ложиться"
    if body.fatigue < 15.0:
        return "ещё не устал настолько, чтобы заснуть"
    return None


# --- what the player believes -------------------------------------------
@dataclass
class EveningBeliefs:
    """Guesses, which may be wrong. Updated by what the morning actually showed."""
    cooling_rate_est: float = COOLING_RATE_C_PER_H
    burn_rate_est: float = FUEL_BURN_PER_H
    work_hours_est: dict[str, float] = field(default_factory=dict)

    def hours_of_fire(self, fuel: float) -> float:
        return fuel / max(0.1, self.burn_rate_est)

    def expected_work_hours(self, work: Work) -> float:
        return self.work_hours_est.get(work.name, work.hours)


@dataclass
class EveningOption:
    label: str
    work: Work | None
    reason: str


def options(body: Body, room: Room, beliefs: EveningBeliefs, hour: float) -> list[dict]:
    """Three real options with the player's own expectation of each. No option is scored as 'correct'."""
    out = []
    for opt in (EveningOption("A: разобрать мебель, топить дольше", HEAVY, "больше топлива, но поздно лечь"),
                EveningOption("B: лечь раньше на том, что есть", None, "сохранить силы, рискнуть остыть"),
                EveningOption("C: немного работы и ранний сон", MODERATE, "середина")):
        work = opt.work
        work_h = beliefs.expected_work_hours(work) if work else 0.0
        fuel_after = room.fuel + (work.fuel if work else 0)
        out.append({
            "option": opt.label,
            "work_hours_expected": round(work_h, 2),
            "fuel_after": fuel_after,
            "fire_hours_expected": round(beliefs.hours_of_fire(fuel_after), 1),
            "night_hours": round(HOURS_OF_NIGHT - work_h, 1),
            "covers_night_expected": beliefs.hours_of_fire(fuel_after) >= HOURS_OF_NIGHT - work_h,
            "stamina_cost": work.stamina_cost if work else 0.0,
            "basis": opt.reason,
        })
    return out


def choose(body: Body, room: Room, beliefs: EveningBeliefs) -> tuple[dict, str]:
    """The player's own rule: cover the night if it can, and not at any price in strength."""
    opts = options(body, room, beliefs, 0.0)
    affordable = [o for o in opts if o["stamina_cost"] <= body.stamina]
    covering = [o for o in affordable if o["covers_night_expected"]]
    if covering:
        pick = min(covering, key=lambda o: o["work_hours_expected"])
        return pick, "рассчитывает, что огня хватит на ночь, и выбирает меньшую работу"
    if affordable:
        pick = max(affordable, key=lambda o: o["fire_hours_expected"])
        return pick, "на всю ночь огня не хватит — берёт то, что греет дольше"
    return opts[1], "сил на работу не осталось"
