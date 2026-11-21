"""One experimental dawn-to-dawn greybox: finite stove fuel couples wet clothes and water.

A distinct research scenario, NOT a second authoritative survival_loop. It reuses
the canonical Body, Room, step_core/step_body, World weather/edges, Agent.beliefs
and evening_run.play. Only two research factors are varied (wet, water needed).
No human enjoyment is inferred; actions and reasons are observable probes.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from typing import Callable

from .agent import Agent
from .body import (Body, CLOTHING_INSULATION_C, COOLING_COEF, IDLE_FATIGUE_PER_H,
                   TRAVEL_FATIGUE_PER_H, step_core, step_fatigue)
from .evening import Room, step_body
from .evening_run import play
from .sim import Decision, clock
from .world import DAY_MINUTES, World

TICK_H = 0.25
DRY_H = 1.5
WATER_H = 1.0
SEARCH_H = 1.0
WET_INSULATION_LOSS_C = 5.0
# A dry garment is the reference protection, not a survival objective.
# Difference in cold exposure from *the same* environmental conditions.
DRY_CORE_ADVANTAGE_C_PER_H = WET_INSULATION_LOSS_C * COOLING_COEF
BELIEVED_DRY_ADVANTAGE_C_PER_H = 0.30  # tentative actor estimate, NOT true physics

# The planned preparation itself differs; movement and destination do not.
EXPLORE = "искать дрова сейчас"
DRY = "высушить одежду перед выходом"
WATER = "подготовить воду перед выходом"
REST = "остаться в убежище"
POLICIES = ("agent", "explore_first", "dry_first", "water_first")
CONDITIONS = ((False, False), (True, False), (False, True), (True, True))


@dataclass
class Equipment:
    wetness: float = 0.0                  # 0 dry .. 1 soaked, persistent all day
    raw_water: int = 0                   # physical finite inventory
    safe_water: int = 0
    drying_hours: float = 0.0
    water_heat_hours: float = 0.0

    @property
    def clothing_c(self) -> float:
        return CLOTHING_INSULATION_C - WET_INSULATION_LOSS_C * self.wetness


def _tick(body: Body, room: Room, world: World, gear: Equipment,
          minutes: float, *, at_home: bool, exposure: float = 0.0,
          weather=None, work: str = "") -> float:
    """Tick one physical clock. Stove burns whether the actor is at home or not."""
    if body.terminal or minutes < 0:
        return 0.0
    expected = minutes / 60
    if at_home:
        fire_before = room.fire_hours_total
        room.step(expected)
        actual = step_body(body, room, world.air_temp_c, expected, asleep=False,
                           fatigue_per_h=IDLE_FATIGUE_PER_H,
                           clothing_c=gear.clothing_c)
        fire_elapsed = room.fire_hours_total - fire_before
        if work == DRY and fire_elapsed > 0:
            gear.drying_hours += fire_elapsed
            gear.wetness = max(0.0, gear.wetness - fire_elapsed / DRY_H)
        elif work == WATER and fire_elapsed > 0:
            gear.water_heat_hours += fire_elapsed
            if gear.water_heat_hours >= WATER_H - 1e-8 and gear.raw_water > 0:
                gear.raw_water -= 1
                gear.safe_water += 1
                gear.water_heat_hours -= WATER_H
        return actual * 60
    felt = world.felt_outdoors_c(exposure, world.dawn_min + body.elapsed_minutes, weather)
    step_core(body, felt, expected, clothing_c=gear.clothing_c)
    actual = body.last_step_hours
    step_fatigue(body, actual, asleep=False, per_hour=TRAVEL_FATIGUE_PER_H)
    room.step(actual)
    return actual * 60


def _advance(body: Body, room: Room, world: World, gear: Equipment,
             minutes: float, *, at_home: bool, exposure: float = 0.0,
             weather=None, work: str = "") -> float:
    accounted = 0.0
    while accounted < minutes - 1e-8 and not body.terminal:
        step = min(TICK_H * 60, minutes - accounted)
        billed = _tick(body, room, world, gear, step, at_home=at_home,
                       exposure=exposure, weather=weather, work=work)
        accounted += billed
        if billed < step - 1e-7:
            break
    return accounted


def _options(stage: str, gear: Equipment, room: Room) -> list[dict]:
    tasks = [
        (EXPLORE, True, 1.0, 0.0, "добыча конечна, улица охлаждает"),
        (DRY, gear.wetness > 1e-8 and (room.fuel > 0 or room.fire_lit),
         DRY_H, min(room.fuel, DRY_H),
         "добровольная подготовка: сухая одежда уменьшает будущую потерю тепла; "
         "действие тратит время и дрова"),
        (WATER, gear.raw_water > 0 and (room.fuel > 0 or room.fire_lit),
         WATER_H, min(room.fuel, WATER_H), "кипячение даст подготовленную воду; нужна печь"),
        (REST, True, 0.5, 0.0, "без новой добычи или подготовки"),
    ]
    if stage == "return":
        tasks = [x for x in tasks if x[0] != EXPLORE]
    return [
        {"option": label, "available": bool(ok),
         "expected_duration_h": hours, "expected_fuel_spent": fuel,
         "basis": basis} for label,ok,hours,fuel,basis in tasks
    ]


def _choose(policy: str, stage: str, body: Body, room: Room,
            gear: Equipment, agent: Agent) -> tuple[str, str]:
    available = {o["option"] for o in _options(stage, gear, room) if o["available"]}
    if stage == "morning" and policy != "agent":
        preference = {
            "explore_first": (EXPLORE, DRY, WATER, REST),
            "dry_first": (DRY, EXPLORE, WATER, REST),
            "water_first": (WATER, EXPLORE, DRY, REST),
        }[policy]
        chosen = next(x for x in preference if x in available)
        return chosen, "предварительно зарегистрированная стратегия, не человеческий выбор"
    if policy == "agent":
        # Drying is an optional investment, NEVER an emergency ordered merely
        # because wetness > 0. Benefits are avoided outdoor core loss while
        # using the same dry reference clothing; costs are fuel and time.
        # These are rough beliefs for a planned 2-hour walk, not an oracle.
        estimated_trip_h = 2.0 if stage == "morning" else 1.5
        saved_core = gear.wetness * BELIEVED_DRY_ADVANTAGE_C_PER_H * estimated_trip_h
        scarce_fuel = 0.8 if room.fuel <= 2.0 else 0.25
        drying_cost = DRY_H * scarce_fuel + 0.3  # hours unavailable for exploring
        cold_urgency = max(0.0, 36.0 - body.core_c)
        scores = {
            EXPLORE: 1.5 + (1.0 if room.fuel < 2.5 else 0.0),
            DRY: saved_core + 0.5 * cold_urgency - drying_cost,
            WATER: 1.0 if gear.raw_water > 0 else -1.0,
            REST: 0.4 + cold_urgency,
        }
        selected = max(available, key=lambda label: (scores[label], label))
        return selected, (
            f"оценка ценности сухой одежды: до {saved_core:.2f}°C меньших "
            f"потерь на будущей вылазке; цена сушки {drying_cost:.2f}; "
            f"выбрано {selected} при ограниченных дровах"
        )
    # Scripted comparator after return: prepare an outstanding need once.
    for label in (DRY, WATER, REST):
        if label in available:
            return label, "контрольный порядок при возвращении"
    return REST, "нет доступной подготовки"


def _intention(gear: Equipment, room: Room, body: Body) -> str:
    """An anticipated objective, not a compulsory clothing or water quest."""
    if body.core_c < 35.5:
        return "снизить риск охлаждения и восстановиться"
    if room.fuel < 2:
        return "найти топливо для следующего дня"
    return "разведать место и выбрать, как подготовиться к следующему выходу"


def run(seed: int, variant: str = "B_readable", profile: str = "local",
        *, wet: bool = False, need_water: bool = False, policy: str = "agent",
        provider: Callable[[Decision], str] | None = None) -> dict:
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    if provider is not None and policy != "agent":
        raise ValueError("human decisions allowed only for agent mode")
    world = World.load("district_v0", variant)
    weather = world.roll_weather(random.Random(f"{seed}:weather:1"))
    agent = Agent(profile, world)
    body = Body()
    room = Room(fuel=world.start_fuel, furniture=0)
    gear = Equipment(wetness=1.0 if wet else 0.0, raw_water=1 if need_water else 0)
    initial_stock = sum(world.loot.values())
    carried = 0
    deposited = 0
    searched = False
    log = []

    def decision(stage: str) -> str:
        cues = [
            f"тело: {body.core_c:.2f} °C",
            f"ощущается в убежище: {room.felt_c(world.air_temp_c):.2f} °C",
            f"мокрота одежды: {gear.wetness:.2f}",
            f"топливо: {room.fuel:.3f}",
            f"вода сырая/подготовленная: {gear.raw_water}/{gear.safe_water}",
            f"время: {clock(world.dawn_min + body.elapsed_minutes)}",
        ]
        alternatives = _options(stage, gear, room)
        chosen, reason = _choose(policy, stage, body, room, gear, agent)
        entry = Decision(time=clock(world.dawn_min + body.elapsed_minutes),
                         point="убежище:"+stage, intention=_intention(gear, room, body),
                         cues=cues, alternatives=alternatives,
                         choice=chosen, reason=reason)
        if provider is not None:
            request = provider(entry)
            allowed = {o["option"] for o in alternatives if o["available"]}
            if request not in allowed:
                raise ValueError(f"unavailable human action: {request}")
            entry.choice = request
            entry.reason = "выбор человека (причина запрашивается отдельно)"
            chosen = request
        log.append(entry)
        return chosen

    def apply(chosen: str) -> None:
        if body.terminal:
            return
        before_min = body.elapsed_minutes
        before_core = body.core_c
        before_burn = room.burned_fuel_total
        before_wet = gear.wetness
        before_raw = gear.raw_water
        if chosen in (DRY, WATER):
            if room.fuel > 0 and not room.fire_lit:
                room.fire_lit = True  # ignition availability is held constant in this 2x2
            _advance(body, room, world, gear,
                     (DRY_H if chosen == DRY else WATER_H) * 60,
                     at_home=True, work=chosen)
        elif chosen == REST:
            _advance(body, room, world, gear, 30, at_home=True)
        log[-1].outcome = (
            f"прошло {(body.elapsed_minutes-before_min):.2f} мин; "
            f"core {before_core:.2f}→{body.core_c:.2f}; "
            f"дров сгорело {room.burned_fuel_total-before_burn:.3f}; "
            f"мокрота {before_wet:.2f}→{gear.wetness:.2f}; "
            f"сырая вода {before_raw}→{gear.raw_water}"
        )
        if chosen == DRY and before_wet > gear.wetness:
            log[-1].belief_update = "увидел, что огонь действительно сушит одежду"
        elif chosen == WATER and gear.safe_water > 0:
            log[-1].belief_update = "увидел, что вода подготовлена"

    first = decision("morning")
    if first != EXPLORE:
        apply(first)

    if not body.terminal and body.elapsed_minutes < (world.day_length-world.dawn_min):
        # A single known house: one real edge + search, physically paid for;
        # no teleport and no "loot appears in the shelter" on early stop.
        travelled = world.edge("home","house_a")
        outbound = world.travel_minutes(travelled, world.dawn_min + body.elapsed_minutes, weather)
        actual = _advance(body, room, world, gear, outbound,
                          at_home=False, exposure=travelled.exposure, weather=weather)
        if not body.terminal and actual >= outbound - 1e-6:
            searched_minutes = _advance(body, room, world, gear, SEARCH_H*60,
                     at_home=False, exposure=0.35, weather=weather)
            if not body.terminal and searched_minutes >= SEARCH_H*60-1e-6:
                searched = True
                available = world.loot.get("house_a", 0)
                carried = min(available, random.Random(f"{seed}:loot").randint(1,2))
                world.loot["house_a"] -= carried
                agent.beliefs.loot["house_a"] = max(
                    0.0, agent.beliefs.loot.get("house_a",0) - carried
                )
                return_trip = world.travel_minutes(
                    travelled, world.dawn_min + body.elapsed_minutes, weather
                )
                home_minutes = _advance(body, room, world, gear, return_trip,
                                 at_home=False, exposure=travelled.exposure,
                                 weather=weather)
                if not body.terminal and home_minutes >= return_trip - 1e-6:
                    deposited = carried
                    room.fuel += carried

    if not body.terminal and deposited == carried and searched:
        second = decision("return")
        apply(second)

    # No activity is silently free: daylight remaining still cools the same body
    # and burns any fire left alight.
    remaining = max(0.0, world.day_length - world.dawn_min - body.elapsed_minutes)
    if remaining > 1e-7 and not body.terminal:
        _advance(body, room, world, gear, remaining, at_home=True)
    core_at_dusk = body.core_c
    water_at_dusk, wet_at_dusk = gear.safe_water, gear.wetness
    fuel_at_dusk = room.fuel
    night = None
    if not body.terminal:
        # Use the existing night controller; wet clothes affect that SAME body.
        night = play("B: лечь раньше на том, что есть", world.air_temp_c,
                     room, body, agent.beliefs, hours_of_night=world.night_hours,
                     clothing_c=gear.clothing_c)

    for event in log:
        if not event.outcome:
            event.outcome = "вылазка предпринята; добыча только после возвращения"
    next_intent = _intention(gear, room, body)
    return {
        "case": {"seed":seed,"variant":variant,"profile":profile,
                 "wet":wet,"need_water":need_water,"policy":policy},
        "participant_source": "human" if provider else "simulated_agent",
        "weather": asdict(weather),
        "decisions": [asdict(x) for x in log],
        "initial_fuel": world.start_fuel,
        "loot_before": initial_stock,
        "loot_after": sum(world.loot.values()),
        "found": carried, "delivered": deposited, "searched": searched,
        "wet_at_dusk": round(wet_at_dusk,4),
        "water_at_dusk": water_at_dusk,
        "raw_water_left": gear.raw_water,
        "wet_final": round(gear.wetness,4),
        "clothing_insulation_final_c": round(gear.clothing_c,4),
        "dry_reference_insulation_c": CLOTHING_INSULATION_C,
        "max_avoided_core_loss_next_2h_c": round(
            (1.0-gear.wetness)*DRY_CORE_ADVANTAGE_C_PER_H*2.0, 5
        ),
        "safe_water_final": gear.safe_water,
        "fuel_at_dusk": round(fuel_at_dusk,4),
        "fuel_final": round(room.fuel,4),
        "fuel_burned": round(room.burned_fuel_total,5),
        "core_at_dusk": round(core_at_dusk,4),
        "core_final": round(body.core_c,4),
        "elapsed_minutes": round(body.elapsed_minutes,6),
        "completed_dawn": not body.terminal and abs(body.elapsed_minutes-DAY_MINUTES)<1e-5,
        "terminal_at_minute": body.terminal_at_minute,
        "end_reason": body.terminal_reason,
        "night": night,
        "next_intention_rule_based": next_intent,
        "limits": [
            "One day+night bounded greybox; NOT the authoritative multi-day survival loop.",
            "No water deprivation penalty; safe water is an optional preparation goal.",
            "Wetness is initial condition, no weather-driven soaking or layered clothing yet.",
            "Spark/ignition availability held constant, no matches inventory in this experiment.",
            "Exploration is one 60-min search of a known house, not a human-controlled map.",
            "Dry clothing is a physical protection advantage, not an obligatory goal.",
            "Next intention is a heuristic label; there is no measured human fun.",
        ],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seed",type=int,default=1)
    ap.add_argument("--variant",choices=("A_safe","B_readable","C_unreadable"),default="B_readable")
    ap.add_argument("--profile",choices=("novice","local"),default="local")
    ap.add_argument("--wet",action="store_true")
    ap.add_argument("--need-water",action="store_true")
    ap.add_argument("--policy",choices=POLICIES,default="agent")
    ap.add_argument("--json")
    args=ap.parse_args()
    result=run(args.seed,args.variant,args.profile,wet=args.wet,
               need_water=args.need_water,policy=args.policy)
    if args.json:
        with open(args.json,"w",encoding="utf-8") as f:
            json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ("night","decisions")},
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
