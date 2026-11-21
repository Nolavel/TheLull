"""D1.8: do consequences form and revise a GOAL, not just action utility?

The same warm/cold shelter, Body, furniture, pending work and deadline are
replayed with three competing *experimenter-assigned initial priorities*.
A planner compares all physically feasible options on fallible personal
forecasts; the same action executor bills time, stamina, heat, fuel and
furniture. Then the actor OBSERVES the result and independently derives the
next goal from the changed physical state. Compare adaptive next intention to
a frozen-priority control using the EXACT same post-action Body/Room.

This is a two-action shelter microloop, NOT two survived days, route loot, or
evidence of human fun. Gathering fuel means chopping a finite furnishing; a
walk in the current route lab does not actually collect fuel.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product

from .agent import Agent
from .body import Body
from .clothing_followthrough import WORK_CONSUMPTION, WORK_MINUTES, WORK_START_STAMINA, followup_work
from .coupled_microloop import Equipment, _advance
from .evening import HEAVY, Room
from .world import World

PROTECT="сохранить силы и тепло"
FUEL="запастись топливом"
WORK="закончить работу"
GOALS=(PROTECT,FUEL,WORK)
REST="отдохнуть"
HEAT="согреться у печи"
CHOP="разобрать мебель на топливо"
DO_WORK="закончить физическую работу"
ACTIONS=(REST,HEAT,CHOP,DO_WORK)
DURATIONS={REST:45,HEAT:30,CHOP:round(HEAVY.hours*60),DO_WORK:WORK_MINUTES}


@dataclass
class Session:
    body: Body
    room: Room
    gear: Equipment
    pending_work: bool = True
    deadline_minute: float = 180.0


def available(session: Session, action: str) -> bool:
    b,r=session.body,session.room
    if b.terminal:
        return False
    return {
        REST:True,
        HEAT:r.fuel>0 and not r.fire_lit,
        CHOP:r.furniture>0 and r.has_axe and b.stamina>=HEAVY.stamina_cost,
        DO_WORK:session.pending_work and b.stamina>=WORK_START_STAMINA,
    }[action]


def prediction(actor: Agent, session: Session, action: str) -> dict:
    """Only actor-visible Body/Room and fallible Beliefs, NO future physics."""
    b,r=session.body,session.room
    m=DURATIONS[action]
    hours=m/60
    # Approximate even for a novice. The physical recovery rate is
    # intentionally NOT called in this forecast.
    recovered=min(100.0,b.stamina+20.0*hours)
    stamina=(max(0,recovered-HEAVY.stamina_cost) if action==CHOP
             else max(0,recovered-WORK_CONSUMPTION) if action==DO_WORK
             else recovered)
    # Actual work does not regenerate idle stamina. A deliberately
    # imperfect actor predicts only the action's known stamina cost.
    if action in (CHOP,DO_WORK):
        stamina=max(0,b.stamina-(HEAVY.stamina_cost if action==CHOP
                                 else WORK_CONSUMPTION))
    lit=r.fire_lit or action==HEAT
    burned=min(r.fuel,hours) if lit else 0.0
    core=(min(37.0,b.core_c+0.5*hours*actor.beliefs.stove_effect_est/4.0)
          if lit else b.core_c-actor.beliefs.shelter_core_cooling_est*hours)
    fuel=r.fuel-burned+(HEAVY.fuel if action==CHOP else 0.0)
    return {
        "option":action,"available":available(session,action),
        "predicted_minutes":m,"predicted_core":round(core,4),
        "predicted_stamina":round(stamina,4),
        "predicted_fuel":round(max(0,fuel),4),
        "predicted_work_done":bool(action==DO_WORK and session.pending_work),
        "predicted_by_deadline":bool(action==DO_WORK and
                                      b.elapsed_minutes+m<=session.deadline_minute),
        "known_furniture_used":1 if action==CHOP else 0,
        "belief_basis":"shelter cooling/burn and visible Body/Room; no future read",
    }


def order(goal: str, pred: dict) -> tuple:
    """Lexicographic declared GOAL preference, not tuning against CI outcomes.

    Body terminal is never an acceptable plan. Thermal safety is an actor
    prediction, not a secretly simulated optimal outcome.
    """
    warmth_ok=int(pred["predicted_core"]>=35.5)
    stamina=pred["predicted_stamina"]
    fuel=pred["predicted_fuel"]
    minutes=pred["predicted_minutes"]
    if goal==PROTECT:
        return (warmth_ok,stamina,round(pred["predicted_core"],4),fuel,-minutes)
    if goal==FUEL:
        return (fuel,warmth_ok,stamina,-minutes)
    if goal==WORK:
        return (int(pred["predicted_by_deadline"]),
                int(pred["predicted_work_done"]),
                warmth_ok,-minutes,stamina)
    raise ValueError("unknown goal")


def plan(actor: Agent, session: Session, goal: str) -> dict:
    options=[prediction(actor,session,a) for a in ACTIONS]
    feasible=[x for x in options if x["available"]]
    if not feasible:
        return {"goal":goal,"choice":None,"alternatives":options,
                "cues":["terminal body: no valid action"],
                "reason":"no available actions", "predicted_ranking":[]}
    ranked=sorted(feasible,key=lambda a:order(goal,a),reverse=True)
    winner=ranked[0]
    b,r=session.body,session.room
    return {
        "goal":goal,"choice":winner["option"],"alternatives":options,
        "cues":[f"core={b.core_c:.2f}°C stamina={b.stamina:.1f}",
                f"fuel={r.fuel:.2f}, furniture={r.furniture}, stove={r.fire_lit}",
                f"work pending={session.pending_work} deadline remaining="
                f"{session.deadline_minute-b.elapsed_minutes:.1f}min"],
        "predicted_ranking":[{"option":p["option"],
                              "goal_order":order(goal,p)} for p in ranked],
        "reason":(f"priority={goal}; selected {winner['option']} "
                  f"by forecast-based ranking {order(goal,winner)}, "
                  "NOT a hardcoded action assigned to a goal"),
    }


def execute(session: Session, action: str, world: World) -> dict:
    """One real physical action; no reward if unfinished due to terminal."""
    if action not in ACTIONS or not available(session,action):
        raise ValueError("action unavailable")
    b,r,gear=session.body,session.room,session.gear
    prior={"minutes":b.elapsed_minutes,"stamina":b.stamina,"core":b.core_c,
           "fuel":r.fuel,"furniture":r.furniture,
           "work_pending":session.pending_work}
    if action==DO_WORK:
        report=followup_work(b,r,world,rest_if_tired=False,gear=gear)
        completed=report["completed"]
        if completed:
            session.pending_work=False
        used=report["total_minutes"]
    elif action==HEAT:
        r.fire_lit=True
        used=_advance(b,r,world,gear,DURATIONS[action],at_home=True)
        completed=used>=DURATIONS[action]-1e-6 and not b.terminal
    elif action==REST:
        used=_advance(b,r,world,gear,DURATIONS[action],at_home=True)
        completed=used>=DURATIONS[action]-1e-6 and not b.terminal
    else:
        pre_stamina=b.stamina
        pre_fatigue=b.fatigue
        used=_advance(b,r,world,gear,DURATIONS[action],at_home=True)
        ratio=min(1.0,used/DURATIONS[action])
        b.stamina=max(0.0,pre_stamina-HEAVY.stamina_cost*ratio)
        b.fatigue=min(100.0,max(b.fatigue,pre_fatigue+HEAVY.fatigue_per_h*used/60))
        completed=used>=DURATIONS[action]-1e-6 and not b.terminal
        if completed:
            r.furniture-=1
            r.fuel+=HEAVY.fuel
    return {
        "action":action,"completed":completed,
        "elapsed_minutes":round(used,5),
        "before":prior,
        "after":{"minutes":round(b.elapsed_minutes,5),
                 "stamina":round(b.stamina,5),"core":round(b.core_c,5),
                 "fuel":round(r.fuel,5),"furniture":r.furniture,
                 "work_pending":session.pending_work,
                 "terminal":b.terminal},
        "observed_consequences":{
            "core_delta":round(b.core_c-prior["core"],5),
            "stamina_delta":round(b.stamina-prior["stamina"],5),
            "fuel_delta":round(r.fuel-prior["fuel"],5),
            "minutes_spent":round(used,5),
            "work_now_finished":prior["work_pending"] and not session.pending_work,
        }
    }


def update_goal(session: Session, anchor: str) -> dict:
    """Derive emerging priority ONLY from observed state after an action."""
    b,r=session.body,session.room
    if b.terminal:
        return {"next_goal":None,"because":"body at terminal boundary"}
    if b.core_c < 35.5:
        return {"next_goal":PROTECT,
                "because":f"measured core={b.core_c:.2f} below 35.5°C"}
    if session.pending_work and b.stamina < WORK_START_STAMINA:
        return {"next_goal":PROTECT,
                "because":f"observed stamina={b.stamina:.1f}; next work requires 60"}
    if session.pending_work and (
        session.deadline_minute-b.elapsed_minutes <=WORK_MINUTES+15
    ):
        return {"next_goal":WORK,
                "because":"pending work and observed deadline approaching"}
    if r.fuel < 2 and r.furniture>0 and b.stamina >= HEAVY.stamina_cost:
        return {"next_goal":FUEL,
                "because":f"observed stove fuel={r.fuel:.2f}, furniture available"}
    if session.pending_work:
        return {"next_goal":WORK,
                "because":"body capable, work still pending"}
    if r.fuel<3 and r.furniture>0:
        return {"next_goal":FUEL,
                "because":"work complete; replenish visibly low fuel"}
    return {"next_goal":PROTECT,
            "because":"work complete and fuel covered; recover for another task"}


def case(variant: str, initial_core: float, initial_stamina: float,
         fuel: float, wetness: float, deadline: int, anchor: str)->dict:
    world=World.load("district_v0",variant)
    # Same weather-independent indoor physics for all three goals; 3 variants
    # change actual air temperature. No future weather schedule read at all.
    session=Session(Body(core_c=initial_core,stamina=initial_stamina,
                         fatigue=15.0),
                    Room(fuel=fuel,furniture=2,has_axe=True),
                    Equipment(wetness=wetness),
                    deadline_minute=deadline)
    actor=Agent("local",world)
    first=plan(actor,session,anchor)
    before_goal=anchor
    # Crucial control: an externally imposed initial goal may already be
    # inconsistent with current pressure. Do NOT call that a goal learned
    # from consequences. Freeze the initial STATE-INFERRED goal here.
    pressure_before=update_goal(session,anchor)
    predicted_first=next(
        (x for x in first["alternatives"] if x["option"]==first["choice"]),None
    )
    outcome=execute(session,first["choice"],world) if first["choice"] else None
    belief_update=""
    if outcome and outcome["elapsed_minutes"]>0:
        # Only real observed body cooling; no "recovery" from positive heat
        # mistaken for shelter cooling.
        belief_update=actor.beliefs.observe_shelter_cooling(
            outcome["before"]["core"],outcome["after"]["core"],
            outcome["elapsed_minutes"]/60.0
        )
    inferred=update_goal(session,anchor)
    goal=inferred["next_goal"]
    adapted=plan(actor,session,goal) if goal else None
    frozen=plan(actor,session,before_goal) if not session.body.terminal else None
    frozen_pressure=(
        plan(actor,session,pressure_before["next_goal"])
        if pressure_before["next_goal"] and not session.body.terminal else None
    )
    forecast_error=None
    if outcome and predicted_first:
        real=outcome["after"]
        forecast_error={
            "core":round(real["core"]-predicted_first["predicted_core"],5),
            "stamina":round(real["stamina"]-predicted_first["predicted_stamina"],5),
            "fuel":round(real["fuel"]-predicted_first["predicted_fuel"],5),
            "minutes":round(outcome["elapsed_minutes"]-
                            predicted_first["predicted_minutes"],5),
            "work_completion_correct": (
                predicted_first["predicted_work_done"] ==
                (not real["work_pending"])
            ),
        }
    snapshot=copy.deepcopy(session)
    # The next action is genuinely executed on the exact post-action state,
    # separately for the adaptive and frozen-control policies.
    second_results={}
    for name,dec in (
        ("adapted",adapted),("frozen",frozen),
        ("pre_action_pressure_frozen",frozen_pressure),
    ):
        other=copy.deepcopy(snapshot)
        second_results[name]=(
            execute(other,dec["choice"],world) if dec and dec["choice"] else None
        )
    return {
        "inputs":{"variant":variant,"core":initial_core,
                  "stamina":initial_stamina,"fuel":fuel,
                  "wetness":wetness,"deadline":deadline,"anchor":anchor},
        "first_intention":first,
        "first_actual":outcome,
        "goal_update":{
            "before":before_goal,"after":goal,
            "reason":inferred["because"],
            "changed":goal!=before_goal and goal is not None,
            "pressure_inferred_before_action":pressure_before,
            "pressure_truly_changed_after_action": (
                pressure_before["next_goal"]!=goal
            ),
        },
        "decision_chain":{
            "assigned_goal":before_goal,
            "initial_state_inferred_goal":pressure_before["next_goal"],
            "cues":first["cues"],
            "alternatives":first["alternatives"],
            "choice":first["choice"],
            "forecast_committed_before_action":predicted_first,
            "observed_consequences":outcome["observed_consequences"] if outcome else None,
            "forecast_error":forecast_error,
            "belief_update_from_observed_cooling":belief_update,
            "next_goal":goal,
            "why_goal_changed":inferred["because"],
            "next_action":adapted["choice"] if adapted else None,
        },
        "next_intentions":{
            "adapted":adapted,"frozen_control":frozen,
            "pre_action_pressure_frozen":frozen_pressure,
        },
        "next_actual_physical_continuations":second_results,
        "state_after_first":{
            "core":session.body.core_c,"stamina":session.body.stamina,
            "fuel":session.room.fuel,"furniture":session.room.furniture,
            "work_pending":session.pending_work,
            "elapsed_minutes":session.body.elapsed_minutes,
        }
    }


def study()->dict:
    # 3 worlds × 2 core × 2 stamina × 2 fuel × 2 wetness × 2 deadlines =
    # 96 distinct initial physical conditions; 3 priorities on EACH = 288.
    variants=("A_safe","B_readable","C_unreadable")
    initial_states=list(product(
        variants,(35.4,36.8),(55.0,85.0),(1.0,3.0),(0.0,1.0),(120,240)
    ))
    cases=[]
    checks=Counter()
    counts=Counter()
    goal_matrix=defaultdict(Counter)
    effects=defaultdict(Counter)
    examples=[]
    for variant,core,stamina,fuel,wetness,deadline in initial_states:
        same=[]
        for goal in GOALS:
            row=case(variant,core,stamina,fuel,wetness,deadline,goal)
            first=row["first_intention"]
            outcome=row["first_actual"]
            follow=row["goal_update"]
            if first["choice"] not in [o["option"] for o in first["alternatives"]
                                      if o["available"]]:
                checks["chosen_unavailable"]+=1
            if outcome:
                bef=outcome["before"]
                aft=outcome["after"]
                if abs((aft["minutes"]-bef["minutes"])-
                       outcome["elapsed_minutes"])>1e-4:
                    checks["unbilled_time"]+=1
                if (aft["fuel"]>bef["fuel"]+1e-5
                    and not (outcome["action"]==CHOP and outcome["completed"])):
                    checks["created_fuel"]+=1
                if (aft["furniture"]<bef["furniture"] and
                    not(outcome["action"]==CHOP and outcome["completed"])):
                    checks["unearned_furniture"]+=1
                if outcome["action"]==CHOP and outcome["completed"] and (
                    abs(aft["fuel"]-bef["fuel"]-HEAVY.fuel)>1e-4 or
                    aft["furniture"]!=bef["furniture"]-1):
                    checks["chop_not_accounted"]+=1
                if outcome["action"]==DO_WORK and outcome["completed"] and (
                    aft["work_pending"] or aft["stamina"]>bef["stamina"]-WORK_CONSUMPTION+1e-5):
                    checks["free_work"]+=1
                if aft["terminal"]:
                    counts["first_action_terminal"]+=1
            if follow["pressure_truly_changed_after_action"]:
                counts["new_pressure_after_actual_action"]+=1
                if len(examples)<12 and (
                    row["next_intentions"]["pre_action_pressure_frozen"]
                    and row["next_intentions"]["adapted"]
                    and row["next_intentions"]["pre_action_pressure_frozen"]["choice"]
                    !=row["next_intentions"]["adapted"]["choice"]
                ):
                    counts["genuine_pressure_changed_next_action"]+=0
            if follow["changed"]:
                counts["goal_revisions"]+=1
                counts[f"revision:{follow['before']}->{follow['after']}"]+=1
            same.append(first["choice"])
            goal_matrix[goal][first["choice"]]+=1
            nexts=row["next_intentions"]
            if nexts["adapted"] and nexts["pre_action_pressure_frozen"]:
                if (nexts["adapted"]["choice"] !=
                    nexts["pre_action_pressure_frozen"]["choice"]):
                    counts["consequence_changed_goal_and_next_action"]+=1
                    if not follow["pressure_truly_changed_after_action"]:
                        checks["action_changed_without_new_pressure"]+=1
            if nexts["adapted"] and nexts["frozen_control"]:
                if nexts["adapted"]["choice"]!=nexts["frozen_control"]["choice"]:
                    counts["goal_caused_next_action_change"]+=1
                    if len(examples)<12:
                        examples.append(row)
                for name,d in nexts.items():
                    if d and d["choice"] not in [
                        a["option"] for a in d["alternatives"] if a["available"]
                    ]:
                        checks["second_action_unavailable"]+=1
                for name,after in row["next_actual_physical_continuations"].items():
                    if after and after["after"]["fuel"]<0:
                        checks["negative_fuel"]+=1
                    if after and after["after"]["terminal"]:
                        effects[name]["terminal"]+=1
                    if after and after["completed"]:
                        effects[name]["completed"]+=1
                    if after and after["after"]["work_pending"] is False:
                        effects[name]["work_done"]+=1
                    if after and after["after"]["fuel"]>=2:
                        effects[name]["fuel_at_least_2"]+=1
                    if after and after["after"]["stamina"]>=WORK_START_STAMINA:
                        effects[name]["ready_for_work"]+=1
            cases.append(row)
        if len(set(same))>1:
            counts["same_state_distinct_first_actions"]+=1
    return {
        "design":{"distinct_initial_states":len(initial_states),
                  "priorities":GOALS,"total_cases":len(cases),
                  "two_real_actions_max":True,
                  "same_world_body_resources_for_goal_comparisons":True,
                  "goal_revised_only_after_actual_consequences":True,
                  "human_participants":0},
        "counts":dict(counts),
        "first_choice_by_goal":{k:dict(v) for k,v in goal_matrix.items()},
        "second_action_effects_on_matched_states":{
            k:dict(v) for k,v in effects.items()},
        "examples":examples,
        "checks":{k:checks[k] for k in (
            "chosen_unavailable","unbilled_time","created_fuel",
            "unearned_furniture","chop_not_accounted","free_work",
            "second_action_unavailable","negative_fuel",
            "action_changed_without_new_pressure")},
        "limits":[
            "Three initial goals are experimentally assigned; report distinguishes disagreement with state-inferred pressure BEFORE any action from a genuinely new pressure AFTER the consequence.",
            "Goal after first action is derived from observed thermal, stamina, fuel and task deadline pressures. The priority heuristic is a hypothesis, not a learning optimizer.",
            "Same post-action Body and Room are copied only for frozen-vs-adaptive counterfactual, not given to actor as hypothetical future observations.",
            "Fuel comes from finite furniture and requires 90 minutes, axe, stamina; a walking trip in D1.7 has no fuel pickup.",
            "No active outdoor weather effect indoors; world air temperature variants change actual thermal pressure.",
            "Two physical actions, not a full day/night or open world and no human enjoyment claims.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--json",required=True)
    a=p.parse_args()
    data=study()
    with open(a.json,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps({
        "design":data["design"],"counts":data["counts"],
        "first_choice_by_goal":data["first_choice_by_goal"],
        "second_action_effects_on_matched_states":data["second_action_effects_on_matched_states"],
        "checks":data["checks"],
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
