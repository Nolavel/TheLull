"""D1.5 — actual post-trip stamina actions and fallible route-learning.

Does a person who walks a route remember its cost and adjust voluntary
clothing preparation? We compare the SAME decision inputs before/after a
single *observed wet* expedition. We NEVER give the agent counterfactual
results (dry controls are researcher-only).

D1.4 is intentionally preserved unchanged as the old baseline.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import asdict
from statistics import mean

from .agent import Agent
from .body import Body
from .clothing_followthrough import WORK_START_STAMINA, followup_work
from .clothing_payoff_study import (
    DISTANCE_MULTIPLIERS, VARIANTS, evaluate
)
from .coupled_microloop import DRY, EXPLORE, Equipment
from .evening import Room
from .sim import Decision
from .world import Edge, World

DRY_TIME_H = 1.5
DRY_FUEL = 1.5
BASE_DRY_WALK_STAMINA_PER_H_EST = 12.0
# Actor priors are fallible; these are NOT the actual Body physics.
BELIEVED_DRY_HEAT_ADVANTAGE_C_PER_H = 0.30
BELIEVED_PACE_SAVING_FRACTION = 0.04


def make_world(variant: str, multiplier: int) -> World:
    if multiplier not in DISTANCE_MULTIPLIERS:
        raise ValueError("unregistered distance")
    world = World.load("district_v0", variant)
    orig = world.edge("home", "house_a")
    world.edges = [
        Edge(e.a, e.b, orig.length_m * multiplier, e.exposure)
        if {e.a, e.b} == {"home", "house_a"} else e
        for e in world.edges
    ]
    return world


def choose_clothing(agent: Agent, body: Body, room: Room, gear: Equipment,
                    *, assume_storm: bool = False) -> Decision:
    """A decision from subjective route beliefs, not the real route or weather."""
    estimated_one_way, route = agent.path("home", "house_a", storm=assume_storm)
    if not route:
        raise ValueError("unknown target — no legitimate expedition option")
    hours = 2 * estimated_one_way / 60.0
    wet_stamina_h = agent.beliefs.wet_walk_stamina_per_h_est
    predicted_wet_stamina = max(0.0, body.stamina - wet_stamina_h * hours)
    anticipated_avoided_core = hours * min(
        BELIEVED_DRY_HEAT_ADVANTAGE_C_PER_H,
        agent.beliefs.wet_walk_core_loss_per_h_est * 0.5
    ) * gear.wetness
    anticipated_saved_stamina = hours * max(
        0.0, wet_stamina_h - BASE_DRY_WALK_STAMINA_PER_H_EST
    ) * gear.wetness
    anticipated_saved_minutes = (2*estimated_one_way
                                 * BELIEVED_PACE_SAVING_FRACTION*gear.wetness)
    # This second task has an OBSERVABLE stamina requirement. Conserving
    # breath may avoid paid rest; it does not create a mobility death gate.
    avoid_rest = (
        predicted_wet_stamina < WORK_START_STAMINA <=
        predicted_wet_stamina + anticipated_saved_stamina
    )
    expected_benefit = (
        anticipated_avoided_core * 0.8
        + anticipated_saved_stamina * 0.09
        + anticipated_saved_minutes * 0.02
        + (0.55 if avoid_rest else 0.0)
    )
    # Time+fuel have competing uses. Not scaled to guarantee a win.
    fuel_scarcity = 0.4 if room.fuel <= 2 else 0.3
    expected_cost = DRY_TIME_H*0.80 + DRY_FUEL*fuel_scarcity
    available_dry = gear.wetness > 0 and room.fuel >= DRY_FUEL and not body.terminal
    available_trip = not body.terminal
    selected = DRY if available_dry and expected_benefit > expected_cost else EXPLORE
    alternatives = [
        {"option": EXPLORE, "available": available_trip,
         "predicted_route_h": round(hours,4), "expected_fuel": 0.0,
         "expected_next_task_stamina": round(predicted_wet_stamina,3),
         "basis": "выход немедленно, без траты дров и часов"},
        {"option": DRY, "available": available_dry,
         "predicted_route_h": round(hours*(1-BELIEVED_PACE_SAVING_FRACTION),4),
         "expected_fuel": DRY_FUEL,
         "expected_next_task_stamina": round(min(
             100.0, predicted_wet_stamina + anticipated_saved_stamina),3),
         "basis": "предполагаемая защита тела/стамины/темпа, 90 минут и дрова"},
    ]
    return Decision(
        time="утро",point="решение о подготовке к известному маршруту",
        intention="вернуться с маршрута и выполнить тяжёлую работу в убежище",
        cues=[
            f"знакомая дорога по памяти: {route}",
            f"оценка пути туда-обратно: {hours:.2f} ч",
            f"предполагаемая буря: {assume_storm} (только допущение)",
            f"тело: {body.core_c:.2f}°C, stamina: {body.stamina:.1f}",
            f"одежда мокрота: {gear.wetness:.2f}, топливо: {room.fuel:.2f}",
            f"прошлых наблюдений мокрой ходьбы: {agent.beliefs.wet_walk_samples}",
            f"предстоящая работа требует {WORK_START_STAMINA:.0f} stamina",
        ],
        alternatives=alternatives,
        choice=selected,
        reason=(f"ожидаемая общая выгода {expected_benefit:.2f}, "
                f"цена подготовки {expected_cost:.2f}; "
                f"стамина/ч из опыта {wet_stamina_h:.2f}; "
                f"ожидаемый выигрыш тепла {anticipated_avoided_core:.2f}°C, "
                f"стамины {anticipated_saved_stamina:.2f}, "
                f"ходьбы {anticipated_saved_minutes:.2f} мин; "
                f"отдых перед работой вероятно сэкономлен: {avoid_rest}"),
    )


def restore_outcome(row: dict, world: World) -> tuple[Body, Room]:
    """Continue the SAME observed Body state after the expedition in the lab."""
    body = Body(core_c=row["core_after_route"],
                stamina=row["stamina_after_route"],
                fatigue=row["fatigue_after_route"],
                elapsed_minutes=row["elapsed_minutes"])
    room = Room(
        fuel=row["fuel_remaining"],
        fire_lit=row["room_fire_lit_after_route"],
        heated_offset_c=row["room_heat_offset_after_route_c"],
        burned_fuel_total=row["fuel_burned"],
        fire_hours_total=row["room_fire_hours_total"],
        furniture=0,
    )
    return body,room


def analyse_case(seed: int, variant: str, multiplier: int,
                 profile: str = "novice") -> dict:
    world = make_world(variant, multiplier)
    agent = Agent(profile,world)
    gear = Equipment(wetness=1.0)
    room = Room(fuel=world.start_fuel)
    start_body = Body()
    first = choose_clothing(agent,start_body,room,gear)
    researcher = evaluate(seed,variant,multiplier)
    # Observe only what happened on the deliberately wet *training* outing.
    actual = researcher["arms"]["wet_now"]
    observation = {"observed":False,"learning":"","path_update":None}
    if actual["completed_return"]:
        weather = world.roll_weather(random.Random(f"{seed}:weather:1"))
        experienced_storm = weather.is_storm(world.dawn_min)
        before_edge = agent.path("home","house_a",storm=experienced_storm)[0]
        # The traveler completed this leg and knows the elapsed minutes.
        observed_leg = actual["legs"][0]["minutes_billed"]
        prediction = agent.observe_edge("home","house_a",experienced_storm,
                                        observed_leg)
        observation = {
            "observed":True,
            "learning":agent.beliefs.observe_wet_walk(
                hours=actual["travel_minutes"]/60,
                stamina_demand=actual["walking_stamina_demand"],
                core_before=actual["core_at_departure"],
                core_after=actual["core_after_route"],
            ),
            "predicted_edge_minutes":round(prediction,5),
            "observed_edge_minutes":round(observed_leg,5),
            "edge_belief_now_min":round(
                agent.path("home","house_a",storm=experienced_storm)[0],5),
            "experienced_storm":experienced_storm,
            "basis": "first real traversed leg, not dry counterfactual",
        }
        # Same hypothetical initial state for a PURE belief-update contrast;
        # separate from the physical same-body post-trip action below.
        after = choose_clothing(agent,Body(),Room(fuel=world.start_fuel),
                                Equipment(wetness=1.0),
                                assume_storm=experienced_storm)
    else:
        after = None

    # A real second action in the same physical Body/clock after each
    # physically successful trip. Neither clothing arm gets free recovery.
    followups = {}
    for arm in ("wet_now","prepared_all","prepared_no_stamina"):
        row = researcher["arms"][arm]
        if not row["completed_return"]:
            followups[arm] = {"possible":False,"reason":"did not return"}
            continue
        body,work_room = restore_outcome(row,world)
        before = {"core_c":body.core_c,"stamina":body.stamina,
                  "elapsed_minutes":body.elapsed_minutes}
        # Availability and voluntary deferral are exposed separately.
        can_do_now = body.stamina >= WORK_START_STAMINA
        deferred_body,deferred_room = restore_outcome(row,world)
        clothes = Equipment(wetness=row["wetness_after_preparation"])
        defer = followup_work(deferred_body,deferred_room,world,
                              rest_if_tired=False, gear=clothes)
        action = followup_work(body,work_room,world,
                               rest_if_tired=True,
                               gear=Equipment(wetness=row["wetness_after_preparation"]))
        followups[arm] = {
            "possible":True,"can_work_without_rest":can_do_now,
            "state_before":before,"defer_option":defer,
            "rest_or_work":action,
            "state_after":{"core_c":round(body.core_c,5),
                           "stamina":round(body.stamina,5),
                           "elapsed_minutes":round(body.elapsed_minutes,5)},
            "fuel_before":row["fuel_remaining"],
            "fuel_after":round(work_room.fuel,5),
            "burned_fuel_after":round(work_room.burned_fuel_total,5),
            "wetness_at_followup":row["wetness_after_preparation"],
        }
    return {
        "case":{"seed":seed,"variant":variant,"multiplier":multiplier,
                "profile":profile},
        "exogenous_weather":researcher["weather"],
        "first_intention":asdict(first),
        "observed_wet_walk":observation,
        "same_initial_state_belief_only_redecision":asdict(after) if after else None,
        "post_trip_second_action":followups,
        "researcher_only_wet_vs_prepared":{
            arm:{"completed_return":researcher["arms"][arm]["completed_return"],
                 "elapsed_minutes":researcher["arms"][arm]["elapsed_minutes"]}
            for arm in ("wet_now","prepared_all")},
    }


def study(seeds: int = 30) -> dict:
    if not 1<=seeds<=100:
        raise ValueError("seeds must be 1..100")
    items=[]
    checks=Counter()
    counts=Counter()
    examples={}
    for variant in VARIANTS:
        for profile in ("local","novice"):
            for multiplier in DISTANCE_MULTIPLIERS:
                for seed in range(1,seeds+1):
                    row=analyse_case(seed,variant,multiplier,profile)
                    items.append(row)
                    key=f"{variant}/{profile}/x{multiplier}"
                    if seed==1:
                        examples[key]=row
                    initial=row["first_intention"]
                    future=row["same_initial_state_belief_only_redecision"]
                    if future:
                        counts["learned_from_real_return"]+=1
                        if future["choice"]!=initial["choice"]:
                            counts["belief_only_choice_changed"]+=1
                            counts[key+":choice_changed"]+=1
                        if row["observed_wet_walk"]["observed_edge_minutes"]<=0:
                            checks["unobserved_edge"]+=1
                        if len(future["alternatives"])!=2:
                            checks["missing_alternative"]+=1
                    if row["observed_wet_walk"]["observed"] and future is None:
                        checks["lost_observation"]+=1
                    for arm,work in row["post_trip_second_action"].items():
                        if not work["possible"]:
                            continue
                        counts[f"{arm}_work_attempted"]+=1
                        if work["can_work_without_rest"]:
                            counts[f"{arm}_work_ready"]+=1
                        if work["rest_or_work"]["completed"]:
                            counts[f"{arm}_work_completed"]+=1
                        if work["rest_or_work"]["rest_minutes"]>0:
                            counts[f"{arm}_work_needed_rest"]+=1
                        if (abs(work["state_after"]["elapsed_minutes"]
                            -work["state_before"]["elapsed_minutes"]
                            -work["rest_or_work"]["total_minutes"]) > .001):
                            checks["free_time"]+=1
                        if work["state_after"]["stamina"] < -1e-7:
                            checks["negative_stamina"]+=1
                        if (work["fuel_before"] < work["fuel_after"] - .001
                            or work["burned_fuel_after"] < -1e-7):
                            checks["free_fuel"]+=1
                    prep=row["post_trip_second_action"]["prepared_all"]
                    nostam=row["post_trip_second_action"]["prepared_no_stamina"]
                    if prep["possible"] and nostam["possible"]:
                        if prep["rest_or_work"]["rest_minutes"] < nostam["rest_or_work"]["rest_minutes"]-1e-5:
                            counts["dry_stamina_saved_recovery_time"]+=1
                        if (prep["can_work_without_rest"]
                            and not nostam["can_work_without_rest"]):
                            counts["dry_stamina_unlocked_immediate_task"]+=1
    return {
        "design":{"seeds":seeds,"worlds":VARIANTS,
                  "distance_multipliers":DISTANCE_MULTIPLIERS,
                  "profiles":("local","novice"),"cases":len(items),
                  "same_initial_belief_comparison":True,
                  "continuation_of_same_body_after_trip":True,
                  "simulated_agent_only":True},
        "counts":dict(counts),
        "checks":{k:checks[k] for k in (
            "unobserved_edge","missing_alternative","lost_observation",
            "free_time","negative_stamina","free_fuel"
        )},
        "examples":examples,
        "limits":[
            "Second decision compares SAME original Body/Room with updated beliefs; it is not a simulated next dawn.",
            "The physically continued after-trip task restores observed room heat/fire/fuel and actual garment wetness, but is a separate action-choice probe, not a 2-day playthrough.",
            "One training trip is deliberately wet; subsequent preparation remains voluntary, with no dry counterfactual disclosed to Agent.",
            "The heavy work stamina readiness threshold is a prototype task constraint, not a global mobility exhaustion penalty.",
            "The route is artificially lengthened 1/8/24/40x only for laboratory sensitivity.",
            "True future storm is never passed to the chooser. Last observed storm can be used as an explicit, uncertain belief.",
            "No claims about human enjoyment or autonomous fun.",
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",type=int,default=30)
    p.add_argument("--json",required=True)
    a=p.parse_args()
    report=study(a.seeds)
    with open(a.json,"w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({"design":report["design"],"counts":report["counts"],
                      "checks":report["checks"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
