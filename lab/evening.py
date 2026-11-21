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
from dataclasses import dataclass, replace

from .agent import Beliefs
from .body import (BASAL_HEAT_C, CLOTHING_INSULATION_C, COMFORT_C, COOLING_COEF,
                   DEATH_C, HYPOTHERMIC_C, IDLE_FATIGUE_PER_H, RECOVERY_PER_H,
                   REWARM_COEF, START_CORE_C, WAKE_COLD_C, Body, step_core, step_fatigue)

# The default district is light 08:00-18:00 and dark the other 14h.
# Integrated calls pass world.daylight_hours / world.night_hours explicitly.
HOURS_OF_NIGHT = 14.0
STEP_H = 0.25
DAYLIGHT_H = 10.0

PASSIVE_OFFSET_C = 3.0
MAX_HEATED_OFFSET_C = 12.0
HEATING_RATE_C_PER_H = 6.0
COOLING_RATE_C_PER_H = 3.0
FUEL_BURN_PER_H = 1.0
HEAT_SOURCE_OFFSET_C = 10.0

# One person = one memory, no independent stove-only Beliefs object.
EveningBeliefs = Beliefs

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
PACK = Work("подготовить снаряжение и маршрут", 0.75, 0, 18.0, 3.0)
SEAL_COOLING_FACTOR = 0.5




@dataclass
class Room:
    heated_offset_c: float = 0.0
    fuel: int = 3
    fire_lit: bool = False
    cooling_rate: float = COOLING_RATE_C_PER_H
    furniture: int = 2  # pieces left that could still be broken up for fuel
    has_axe: bool = True  # chopping is not available without the tool
    sealed: bool = False  # insulation is a persistent one-time repair
    # Cumulative resource meters are diagnostic observations, not extra fuel.
    burned_fuel_total: float = 0.0
    fire_hours_total: float = 0.0

    def felt_c(self, outside_c: float) -> float:
        # Indoors the wind-chill term is gone entirely (Hoarbound §4). What is left: the structure's passive
        # warmth, the warmth the room has accumulated, and the stove itself while it burns.
        source = HEAT_SOURCE_OFFSET_C if self.fire_lit and self.fuel > 0 else 0.0
        return outside_c + PASSIVE_OFFSET_C + self.heated_offset_c + source

    def step(self, hours: float) -> None:
        # Paired step_body may rewind the final fraction when the single
        # Body reaches its stopping boundary inside this time interval.
        self._pre_step = (self.fuel, self.heated_offset_c, self.fire_lit,
                          self.burned_fuel_total, self.fire_hours_total)
        if self.fire_lit and self.fuel > 0:
            burned_h = min(hours, self.fuel / FUEL_BURN_PER_H)
            spent = FUEL_BURN_PER_H * burned_h
            self.fuel = max(0.0, self.fuel - spent)
            self.burned_fuel_total += spent
            self.fire_hours_total += burned_h
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
              fatigue_per_h: float = 0.0,
              *, clothing_c: float = CLOTHING_INSULATION_C) -> float:
    """Advance body and room on one clock; refund unspent fuel at terminal crossing.

    Call after room.step(hours). The room snapshot allows a partial final tick;
    no fictitious rest, fire burn or extra minutes are billed after the stop.
    """
    previous = getattr(room, "_pre_step", None)
    if body.terminal:
        if previous is not None:
            (room.fuel, room.heated_offset_c, room.fire_lit,
             room.burned_fuel_total, room.fire_hours_total) = previous
        return 0.0
    used = hours
    if previous is not None and body.hours_until_terminal(room.felt_c(outside_c), hours, clothing_c) < hours - 1e-9:
        # The heat of a room can change during the step. Solve the first
        # crossing using the same end-of-step felt-temperature approximation.
        lo, hi = 0.0, hours
        for _ in range(35):
            mid = (lo + hi) / 2.0
            shadow = replace(room, fuel=previous[0],
                             heated_offset_c=previous[1], fire_lit=previous[2],
                             burned_fuel_total=previous[3], fire_hours_total=previous[4])
            shadow.step(mid)
            if body.hours_until_terminal(shadow.felt_c(outside_c), mid, clothing_c) < mid - 1e-12:
                hi = mid
            else:
                lo = mid
        used = hi
        (room.fuel, room.heated_offset_c, room.fire_lit,
         room.burned_fuel_total, room.fire_hours_total) = previous
        room.step(used)
    step_core(body, room.felt_c(outside_c), used, clothing_c=clothing_c)
    billed = body.last_step_hours
    if billed < used - 1e-8 and previous is not None:
        # Numerical boundary: refund the last microscopic partial interval.
        (room.fuel, room.heated_offset_c, room.fire_lit,
         room.burned_fuel_total, room.fire_hours_total) = previous
        room.step(billed)
    step_fatigue(body, billed, asleep=asleep, per_hour=fatigue_per_h)
    return billed


def sleep_refusal(room: Room, body: Body, outside_c: float) -> str | None:
    """Named reason, as Hoarbound's SleepController does. Not a save gate: the lab never blocks progress."""
    if room.felt_c(outside_c) < 5.0:
        return "слишком холодно, чтобы ложиться"
    if body.core_c < WAKE_COLD_C + 0.25:
        return "сначала нужно согреться"
    if body.fatigue < 15.0:
        return "ещё не устал настолько, чтобы заснуть"
    return None


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


def morning_prep_hours(tomorrow: Tomorrow) -> float:
    """Time spent packing and checking a route after sunrise unless done tonight."""
    return 0.25 + 0.12 * tomorrow.hours_out + 0.12 * tomorrow.load


@dataclass
class EveningOption:
    label: str
    work: Work | None
    reason: str


def _forecast(opt: EveningOption, body: Body, room: Room, beliefs: EveningBeliefs,
              tomorrow: Tomorrow, outside_c: float, daylight_hours: float = DAYLIGHT_H,
              night_hours: float = HOURS_OF_NIGHT) -> dict:
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
        and (work is not PACK or not body.packed)
    ))
    work_h = beliefs.expected_work_hours(work) if work else 0.0
    added_fuel = work.fuel if work else 0
    fuel_after = room.fuel + added_fuel
    fire_h = beliefs.hours_of_fire(fuel_after)
    # The next-day cost is explicit. There is no table mapping an intended
    # journey to an A/B/C action.
    travel_effort = tomorrow.hours_out * (3.0 + 0.9 * tomorrow.load + 0.75)
    prep_h = 0.0 if body.packed or work is PACK else morning_prep_hours(tomorrow)
    day_effort = travel_effort + prep_h * 1.5
    daylight_overrun = max(0.0, tomorrow.hours_out + prep_h - daylight_hours)

    if not available:
        return {
            "option": opt.label, "available": False,
            "work_hours_expected": round(work_h, 2),
            "fuel_after": fuel_after, "fire_hours_expected": round(fire_h, 1),
            "night_hours": round(night_hours - work_h, 1),
            "cold_hours_expected": None, "wake_hours_expected": None,
            "core_at_morning_if_uninterrupted": None,
            "expects_to_wake_cold": None, "morning_fatigue_expected": None,
            "day_effort_expected": round(day_effort, 1),
            "morning_prep_hours_expected": round(prep_h, 2),
            "daylight_overrun_expected": round(daylight_overrun, 2),
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
                       fatigue=body.fatigue, recovery_per_h=beliefs.recovery_est,
                       packed=body.packed)

    # Local import: evening_run already depends on this module; the runtime
    # call is safe and avoids maintaining an inconsistent second night model.
    from .evening_run import play
    predicted = play(opt.label, outside_c, shadow_room, shadow_body, beliefs,
                     hours_of_night=night_hours)
    morning_fatigue = predicted["morning_fatigue"]
    prep_h = 0.0 if shadow_body.packed else morning_prep_hours(tomorrow)
    day_effort = travel_effort + prep_h * 1.5
    daylight_overrun = max(0.0, tomorrow.hours_out + prep_h - daylight_hours)
    projected_fatigue_after_trip = morning_fatigue + day_effort
    morning_fit = (morning_fatigue <= tomorrow.max_morning_fatigue
                   and projected_fatigue_after_trip <= 90.0
                   and predicted["morning_core_c"] >= HYPOTHERMIC_C)
    return {
        "option": opt.label,
        "available": True,
        "work_hours_expected": round(work_h, 2),
        "fuel_after": fuel_after,
        "fire_hours_expected": round(fire_h, 1),
        "night_hours": round(night_hours - work_h, 1),
        "cold_hours_expected": predicted["hours_below_hypothermic"],
        "wake_hours_expected": predicted["awake_at_night_h"],
        "core_at_morning_if_uninterrupted": predicted["morning_core_c"],
        "expects_to_wake_cold": predicted["woke_cold"] > 0,
        "morning_fatigue_expected": morning_fatigue,
        "day_effort_expected": round(day_effort, 1),
        "morning_prep_hours_expected": round(prep_h, 2),
        "daylight_overrun_expected": round(daylight_overrun, 2),
        "fatigue_after_trip_expected": round(projected_fatigue_after_trip, 1),
        "ready_for_tomorrow_expected": morning_fit and daylight_overrun <= 1e-9,
        "stamina_cost": work.stamina_cost if work else 0.0,
        "basis": opt.reason,
    }


OPTIONS = (EveningOption("A: разобрать мебель, топить дольше", HEAVY, "больше топлива, но поздно лечь"),
           EveningOption("B: лечь раньше на том, что есть", None, "сохранить силы, рискнуть остыть"),
           EveningOption("C: утеплить комнату и лечь раньше", SEAL, "тепло держится дольше без новых дров"),
           EveningOption("D: подготовить вещи и маршрут к утру", PACK, "готовый рюкзак сохраняет время света завтра"))


def options(body: Body, room: Room, beliefs: EveningBeliefs, tomorrow: Tomorrow,
            outside_c: float, daylight_hours: float = DAYLIGHT_H,
            night_hours: float = HOURS_OF_NIGHT) -> list[dict]:
    """Four options with predictions based on the player's knowledge, not a prescribed choice."""
    return [_forecast(o, body, room, beliefs, tomorrow, outside_c, daylight_hours, night_hours) for o in OPTIONS]


def choose(body: Body, room: Room, beliefs: EveningBeliefs, tomorrow: Tomorrow,
           outside_c: float, daylight_hours: float = DAYLIGHT_H,
           night_hours: float = HOURS_OF_NIGHT) -> tuple[dict, str, Tomorrow]:
    """Weigh predicted night's disruption and next day's load. No true-night oracle.

    Plans change the cost of fatigue and daylight; there is no plan-to-option lookup.
    Decisions are research heuristics, not a proven human policy.
    """
    opts = options(body, room, beliefs, tomorrow, outside_c, daylight_hours, night_hours)
    eligible = [o for o in opts if o["available"]]
    # Packing is available to the player, but a one-day planner does not spend
    # tonight preparing a journey that its own forecast says cannot happen.
    eligible = [o for o in eligible if not (o["option"].startswith("D:")
                and not o["ready_for_tomorrow_expected"])]
    can_keep_plan = any(o["ready_for_tomorrow_expected"] for o in eligible)
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
        # Penalize the lost itinerary only when a viable preparation would preserve it.
        # If the whole night is too cold or exhausting, do not force packing.
        lost_plan = 25.0 if tomorrow.droppable and can_keep_plan and not o["ready_for_tomorrow_expected"] else 0.0
        return cold + future + unready + strength + 1.5 * o["work_hours_expected"] + materials + lost_plan

    pick = min(eligible, key=lambda o: (opportunity_cost(o), o["work_hours_expected"]))
    after = tomorrow
    if tomorrow.droppable and not pick["ready_for_tomorrow_expected"]:
        after = replace(tomorrow, name=f"{SHORT_WALK.name} вместо «{tomorrow.name}»",
                        hours_out=SHORT_WALK.hours_out, load=SHORT_WALK.load,
                        max_morning_fatigue=SHORT_WALK.max_morning_fatigue, droppable=False)
    reason = (f"сравнил ожидаемый холод, работу и запас сил на «{tomorrow.name}»; "
              f"выбрал минимальную цену {opportunity_cost(pick):.1f}"
              + ("; отложил дальний план" if after is not tomorrow else "")
              + ("; подготовка сэкономит утренний свет" if pick["option"].startswith("D:") else ""))
    return pick, reason, after
