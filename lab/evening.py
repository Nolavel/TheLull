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
# Author's rule (19.11.2026): a cold night wakes the sleeper instead of killing them in their sleep.
# Bad preparation must hand the player a new problem they can answer, not a death with no reply.
WAKE_COLD_C = 35.5

# --- work ---------------------------------------------------------------
@dataclass(frozen=True)
class Work:
    name: str
    hours: float
    fuel: int
    stamina_cost: float
    fatigue_per_h: float


HEAVY = Work("разобрать мебель", 1.5, 4, 55.0, 7.0)
# Sealing gives no fuel at all: it changes the room instead, so the same fire lasts further into the night.
# This is the author's third path and Hoarbound's "a shelter is warm because you made it warm".
SEAL = Work("утеплить комнату", 0.75, 0, 25.0, 4.5)
SEAL_COOLING_FACTOR = 0.5
IDLE_FATIGUE_PER_H = 2.0  # just being awake and cold


RECOVERY_PER_H = 6.0  # how much fatigue a warm hour of sleep pays back; placeholder, and a real design lever


@dataclass
class Body:
    core_c: float = START_CORE_C
    stamina: float = 100.0
    fatigue: float = 45.0  # 0 = rested, 100 = spent; evening after a trip
    recovery_per_h: float = RECOVERY_PER_H

    def stamina_recovery_per_h(self) -> float:
        """Fatigue slows breath coming back (Hoarbound: recovery pace × energy)."""
        return 60.0 * max(0.2, 1.0 - self.fatigue / 100.0)


@dataclass
class Room:
    heated_offset_c: float = 0.0
    fuel: int = 3
    fire_lit: bool = False
    cooling_rate: float = COOLING_RATE_C_PER_H
    furniture: int = 2  # pieces left that could still be broken up for fuel
    has_axe: bool = True  # chopping is not available without the tool
    sealed: bool = False  # insulation is a persistent one-time repair

    def felt_c(self, outside_c: float) -> float:
        # Indoors the wind-chill term is gone entirely (Hoarbound §4). What is left: the structure's passive
        # warmth, the warmth the room has accumulated, and the stove itself while it burns.
        source = HEAT_SOURCE_OFFSET_C if self.fire_lit and self.fuel > 0 else 0.0
        return outside_c + PASSIVE_OFFSET_C + self.heated_offset_c + source

    def step(self, hours: float) -> None:
        if self.fire_lit and self.fuel > 0:
            burned_h = min(hours, self.fuel / FUEL_BURN_PER_H)
            self.fuel = max(0.0, self.fuel - FUEL_BURN_PER_H * burned_h)
            self.heated_offset_c = min(MAX_HEATED_OFFSET_C, self.heated_offset_c + HEATING_RATE_C_PER_H * burned_h)
            if self.fuel <= 0:
                self.fire_lit = False
            # Even a partial step after the last ember counts as cooling.
            remaining_h = hours - burned_h
            if remaining_h > 0:
                self.heated_offset_c = max(0.0, self.heated_offset_c - self.cooling_rate * remaining_h)
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
        recovered = body.recovery_per_h * hours
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
    if body.core_c < WAKE_COLD_C + 0.25:
        return "сначала нужно согреться"
    if body.fatigue < 15.0:
        return "ещё не устал настолько, чтобы заснуть"
    return None


# --- what the player believes -------------------------------------------
@dataclass
class EveningBeliefs:
    """Guesses, which may be wrong. Updated by what the morning actually showed."""
    cooling_rate_est: float = COOLING_RATE_C_PER_H
    burn_rate_est: float = FUEL_BURN_PER_H
    recovery_est: float = RECOVERY_PER_H
    work_hours_est: dict[str, float] = field(default_factory=dict)

    def hours_of_fire(self, fuel: float) -> float:
        return fuel / max(0.1, self.burn_rate_est)

    def expected_work_hours(self, work: Work) -> float:
        return self.work_hours_est.get(work.name, work.hours)

    def observe_burn_rate(self, measured_per_h: float) -> str:
        """Update in either direction ONLY after an observable, timed fuel reading."""
        if measured_per_h <= 0:
            raise ValueError("observed burn rate must be positive")
        old = self.burn_rate_est
        self.burn_rate_est = 0.5 * old + 0.5 * measured_per_h
        return f"наблюдаемый расход топлива: {old:.2f}→{self.burn_rate_est:.2f} в час"


@dataclass(frozen=True)
class Tomorrow:
    """What the player means to do tomorrow. The evening is judged against it, not in isolation."""
    name: str
    hours_out: float
    load: float
    max_morning_fatigue: float  # above this the player believes the plan is beyond them
    droppable: bool = True


SHORT_WALK = Tomorrow("короткая вылазка рядом", 2.0, 2.0, 85.0, droppable=False)
EXPEDITION = Tomorrow("дальняя экспедиция с грузом", 6.0, 6.0, 40.0)
UNDECIDED = Tomorrow("ещё не решил: рядом есть неизученное место", 4.0, 3.0, 60.0)


@dataclass
class EveningOption:
    label: str
    work: Work | None
    reason: str


def _forecast(opt: EveningOption, body: Body, room: Room, beliefs: EveningBeliefs,
              tomorrow: Tomorrow, outside_c: float) -> dict:
    """A mental dry-run against BELIEVED fuel/cooling and visible room state.

    Uses the same physical night integrator as the real run, but on copies
    with the agent's estimates. It never reads the future night result.
    This removes the earlier bug where one hour below comfort automatically
    meant waking despite the body's thermal inertia.
    """
    work = opt.work
    available = (work is None or (
        body.stamina >= work.stamina_cost
        and (work is not HEAVY or (room.has_axe and room.furniture > 0))
        and (work is not SEAL or not room.sealed)
    ))
    work_h = beliefs.expected_work_hours(work) if work else 0.0
    added_fuel = work.fuel if work else 0
    fuel_after = room.fuel + added_fuel
    fire_h = beliefs.hours_of_fire(fuel_after)
    # The next-day cost is explicit. There is no table mapping an intended
    # journey to an A/B/C action.
    day_effort = tomorrow.hours_out * (3.0 + 0.9 * tomorrow.load + 0.75)

    if not available:
        return {
            "option": opt.label, "available": False,
            "work_hours_expected": round(work_h, 2),
            "fuel_after": fuel_after, "fire_hours_expected": round(fire_h, 1),
            "night_hours": round(HOURS_OF_NIGHT - work_h, 1),
            "cold_hours_expected": None, "wake_hours_expected": None,
            "core_at_morning_if_uninterrupted": None,
            "expects_to_wake_cold": None, "morning_fatigue_expected": None,
            "day_effort_expected": round(day_effort, 1),
            "fatigue_after_trip_expected": None,
            "ready_for_tomorrow_expected": False,
            "stamina_cost": work.stamina_cost if work else 0.0,
            "basis": opt.reason,
        }

    # Convert the *believed* burn rate into virtual fuel-hours. With work
    # included, the shadow stove will last (known fuel + known yield) / rate.
    # Real room, furniture, body and the agent's beliefs remain untouched.
    rate = max(0.1, beliefs.burn_rate_est)
    virtual_fuel = max(0.0, fuel_after / rate - added_fuel)
    shadow_room = Room(
        heated_offset_c=room.heated_offset_c, fuel=virtual_fuel,
        fire_lit=room.fire_lit,
        cooling_rate=beliefs.cooling_rate_est * (SEAL_COOLING_FACTOR if room.sealed else 1.0),
        furniture=room.furniture, has_axe=room.has_axe, sealed=room.sealed
    )
    shadow_body = Body(core_c=body.core_c, stamina=body.stamina,
                       fatigue=body.fatigue, recovery_per_h=beliefs.recovery_est)

    # Local import: evening_run already depends on this module; the runtime
    # call is safe and avoids maintaining an inconsistent second night model.
    from .evening_run import play
    predicted = play(opt.label, outside_c, shadow_room, shadow_body, beliefs)
    morning_fatigue = predicted["morning_fatigue"]
    projected_fatigue_after_trip = morning_fatigue + day_effort
    return {
        "option": opt.label,
        "available": True,
        "work_hours_expected": round(work_h, 2),
        "fuel_after": fuel_after,
        "fire_hours_expected": round(fire_h, 1),
        "night_hours": round(HOURS_OF_NIGHT - work_h, 1),
        "cold_hours_expected": predicted["hours_below_hypothermic"],
        "wake_hours_expected": predicted["awake_at_night_h"],
        "core_at_morning_if_uninterrupted": predicted["morning_core_c"],
        "expects_to_wake_cold": predicted["woke_cold"] > 0,
        "morning_fatigue_expected": morning_fatigue,
        "day_effort_expected": round(day_effort, 1),
        "fatigue_after_trip_expected": round(projected_fatigue_after_trip, 1),
        "ready_for_tomorrow_expected": (morning_fatigue <= tomorrow.max_morning_fatigue
                                       and projected_fatigue_after_trip <= 90.0),
        "stamina_cost": work.stamina_cost if work else 0.0,
        "basis": opt.reason,
    }


OPTIONS = (EveningOption("A: разобрать мебель, топить дольше", HEAVY, "больше топлива, но поздно лечь"),
           EveningOption("B: лечь раньше на том, что есть", None, "сохранить силы, рискнуть остыть"),
           EveningOption("C: утеплить комнату и лечь раньше", SEAL, "тепло держится дольше без новых дров"))


def options(body: Body, room: Room, beliefs: EveningBeliefs, tomorrow: Tomorrow,
            outside_c: float) -> list[dict]:
    """Three options, each with the player's own expectation of how it ends. None is scored as correct."""
    return [_forecast(o, body, room, beliefs, tomorrow, outside_c) for o in OPTIONS]


def choose(body: Body, room: Room, beliefs: EveningBeliefs, tomorrow: Tomorrow,
           outside_c: float) -> tuple[dict, str, Tomorrow]:
    """Weigh predicted night's disruption and next day's load. No true-night oracle.

    Plans change the *cost* of fatigue, not a lookup table from plan to A/B/C.
    Decisions are research heuristics, not a proven human policy.
    """
    opts = options(body, room, beliefs, tomorrow, outside_c)
    eligible = [o for o in opts if o["available"]]
    if not eligible:
        return next(o for o in opts if o["option"].startswith("B:")), "работа недоступна", tomorrow

    def opportunity_cost(o: dict) -> float:
        # Waking cold is disruptive, even if later intervention averts a bad morning.
        # Mild cooling is not the same as interrupted sleep: use *predicted wakes*.
        cold = o["wake_hours_expected"] * 12.0 + (5.0 if o["expects_to_wake_cold"] else 0.0)
        # Fatigue is more expensive before a demanding day; short tasks tolerate it.
        future = max(0.0, o["fatigue_after_trip_expected"] - 80.0) * 1.7
        unready = max(0.0, o["morning_fatigue_expected"] - tomorrow.max_morning_fatigue) * 1.0
        strength = o["morning_fatigue_expected"] * (0.12 + tomorrow.hours_out * 0.07)
        # Time and finite materials have an opportunity cost even when the night stays warm.
        materials = 2.5 if o["option"].startswith("A:") else (1.5 if o["option"].startswith("C:") else 0.0)
        return cold + future + unready + strength + 1.5 * o["work_hours_expected"] + materials

    pick = min(eligible, key=lambda o: (opportunity_cost(o), o["work_hours_expected"]))
    after = tomorrow
    if tomorrow.droppable and not pick["ready_for_tomorrow_expected"]:
        after = replace(tomorrow, name=f"{SHORT_WALK.name} вместо «{tomorrow.name}»",
                        hours_out=SHORT_WALK.hours_out, load=SHORT_WALK.load,
                        max_morning_fatigue=SHORT_WALK.max_morning_fatigue, droppable=False)
    reason = (f"сравнил ожидаемый холод, работу и запас сил на «{tomorrow.name}»; "
              f"выбрал минимальную цену {opportunity_cost(pick):.1f}"
              + ("; отложил дальний план" if after is not tomorrow else ""))
    return pick, reason, after
