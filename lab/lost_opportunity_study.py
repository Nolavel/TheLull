"""D2.0: does a lived night change WHAT tomorrow is for?

An isolated, paired physical experiment using the EXISTING canonical
Room/Body/World/Equipment, evening_run.play, followup_work and _advance.

At dusk an externally assigned job is planned for tomorrow's morning
(60 min, 60 stamina, physical readiness, deadline). A real night happens.
The actor may lose the opportunity, not just see a low fuel meter.
The morning can instead be used to restore strength, prepare a route,
insulate shelter or chop finite furniture. The alternative is PAID,
then the body survives another real day/night.

The two policies share exactly the same night. The only intervention is the
MORNING goal policy at the new dawn. The time-only counterfactual uses
the previous evening's body and room advanced to the SAME clock, WITHOUT
inventing an uneventful physical night or knowing a future outcome.

This is a focused evening -> next morning -> subsequent morning probe,
not an integrated clothing/daytime route playtest. No humans/fun scores.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter, defaultdict
from itertools import product

from .agent import Agent
from .body import Body
from .clothing_followthrough import WORK_MINUTES, WORK_START_STAMINA, followup_work
from .coupled_microloop import Equipment, _advance
from .evening import HEAVY, PACK, SEAL, Room
from .evening_run import play
from .world import DAY_MINUTES, World

MAIN="выполнить назначенную работу"
REST="восстановиться"
PREPARE="подготовить вещи к выходу"
INSULATE="утеплить убежище"
CHOP="получить топливо из мебели"
ACTIONS=(MAIN,REST,PREPARE,INSULATE,CHOP)
COST_MIN={MAIN:WORK_MINUTES,REST:60,
          PREPARE:round(PACK.hours*60),INSULATE:round(SEAL.hours*60),
          CHOP:round(HEAVY.hours*60)}
STAMINA_COST={MAIN:20.0,REST:0.0,
              PREPARE:PACK.stamina_cost,INSULATE:SEAL.stamina_cost,
              CHOP:HEAVY.stamina_cost}
WORK_CORE_MIN=36.0
WORK_FATIGUE_MAX=70.0
MAX_DAWN_DELAY=180.0  # scheduled task expires at 11:00, an announced limit


def work_opportunity(body: Body, deadline: float, pending=True)->dict:
    """A physical work gate: deadlines AND actual readiness, not a wake flag."""
    reasons=[]
    if body.terminal:
        reasons.append("terminal")
    if not pending:
        reasons.append("already completed")
    if body.stamina < WORK_START_STAMINA:
        reasons.append("stamina below task minimum")
    if body.core_c < WORK_CORE_MIN:
        reasons.append("core below outdoor/heavy-work readiness")
    if body.fatigue > WORK_FATIGUE_MAX:
        reasons.append("fatigue above task threshold")
    if body.elapsed_minutes + WORK_MINUTES > deadline+1e-7:
        reasons.append("insufficient scheduled time")
    return {"available":not reasons,"blockers":reasons,
            "observed":{"core_c":round(body.core_c,4),
                        "fatigue":round(body.fatigue,4),
                        "stamina":round(body.stamina,4),
                        "deadline_remaining":round(deadline-body.elapsed_minutes,4)}}


def _can(body,room,action,deadline,pending):
    if body.terminal:
        return False
    if action==MAIN:
        return work_opportunity(body,deadline,pending)["available"]
    if action==REST:
        return True
    if action==PREPARE:
        return not body.packed and body.stamina>=PACK.stamina_cost
    if action==INSULATE:
        return not room.sealed and body.stamina>=SEAL.stamina_cost
    if action==CHOP:
        return bool(room.has_axe and room.furniture>0 and
                    body.stamina>=HEAVY.stamina_cost)
    raise ValueError(action)


def decide(actor,body,room,deadline,pending,*,policy,reported_plan):
    """Two real policies. Neither inspects the physical future or simulates it.

    'continue_job' attempts a recovery period when work is unavailable,
    then may retry; it is NOT an intentionally inert straw man.
    'opportunity' can prioritize salvage shelter/gear or limited fuel
    instead. Reason is grounded in observed constraints, not last-night labels.
    """
    if policy not in ("opportunity","continue_job"):
        raise ValueError("unknown policy")
    gate=work_opportunity(body,deadline,pending)
    low_fuel=room.fuel < 2
    is_cold=body.core_c < WORK_CORE_MIN
    predicted_recovery=round(
        min(100.0-body.stamina,max(0.0,actor.beliefs.recovery_est*2)),2
    )
    # Predictions are intentionally fallible; objective effects of packing,
    # sealing and chopping are known actions, NOT measured future outcomes.
    alts=[]
    for action in ACTIONS:
        alts.append({
            "option":action,
            "available":_can(body,room,action,deadline,pending),
            "minutes":COST_MIN[action],
            "stamina_cost":STAMINA_COST[action],
            "predicted_fuel_gain":HEAVY.fuel if action==CHOP else 0,
            "known_prepares_route":action==PREPARE,
            "known_seals_room":action==INSULATE,
            "estimated_stamina_recovery":predicted_recovery if action==REST else 0,
            "basis":"visible resources, physical task cost and fallible agent beliefs"
        })
    if not pending:
        goal="сохранить готовность после выполненной работы"
    elif gate["available"]:
        goal=MAIN
    elif policy=="continue_job":
        goal="восстановиться ради прежней работы"
    elif body.core_c<35.4 or body.fatigue>WORK_FATIGUE_MAX:
        goal="сначала восстановить способность действовать"
    elif low_fuel and room.furniture>0 and body.stamina>=HEAVY.stamina_cost:
        goal="обеспечить будущую ночь топливом"
    elif room.fuel<=3 and not room.sealed and body.stamina>=SEAL.stamina_cost:
        goal="снизить теплопотери убежища"
    elif not body.packed and body.stamina>=PACK.stamina_cost:
        goal="подготовить следующую попытку"
    else:
        goal="сначала восстановить способность действовать"

    # Goal value is distinct from action: rank only truly available options,
    # with explicit alternative fallbacks, no forced choice of unavailable job.
    preferences={
        MAIN:(MAIN,REST,PREPARE,INSULATE,CHOP),
        "сохранить готовность после выполненной работы":
            (REST,INSULATE,PREPARE,CHOP),
        "восстановиться ради прежней работы":(REST,PREPARE,INSULATE,CHOP),
        "сначала восстановить способность действовать":
            (REST,INSULATE,PREPARE,CHOP),
        "обеспечить будущую ночь топливом":
            (CHOP,INSULATE,REST,PREPARE),
        "снизить теплопотери убежища":
            (INSULATE,REST,PREPARE,CHOP),
        "подготовить следующую попытку":
            (PREPARE,INSULATE,REST,CHOP),
    }
    available={a["option"] for a in alts if a["available"]}
    chosen=next((a for a in preferences[goal] if a in available),None)
    return {
        "assigned_plan":reported_plan,"current_goal":goal,"choice":chosen,
        "cues":{"core":round(body.core_c,4),"stamina":round(body.stamina,4),
                "fatigue":round(body.fatigue,4),"fuel":round(room.fuel,4),
                "furniture":room.furniture,"packed":body.packed,"sealed":room.sealed,
                "deadline_remaining":round(deadline-body.elapsed_minutes,3),
                "job_blockers":gate["blockers"]},
        "alternatives":alts,
        "reason":f"goal={goal}; task feasibility={gate['available']}; "
                 f"observed blockers={gate['blockers']}; "
                 f"chosen feasible option={chosen}",
        "belief_basis":{"recovery_est":actor.beliefs.recovery_est,
                        "burn_rate_est":actor.beliefs.burn_rate_est},
        "policy":policy,
    }


def execute(body,room,world,gear,action,deadline,pending)->dict:
    if action not in ACTIONS or not _can(body,room,action,deadline,pending):
        raise ValueError("attempted unavailable action")
    before={"minute":body.elapsed_minutes,"core":body.core_c,
            "stamina":body.stamina,"fatigue":body.fatigue,
            "fuel":room.fuel,"furniture":room.furniture,
            "packed":body.packed,"sealed":room.sealed,"pending":pending}
    if action==MAIN:
        work=followup_work(body,room,world,rest_if_tired=False,gear=gear)
        actual=work["total_minutes"]
        completed=work["completed"]
        if completed:
            pending=False
    else:
        # Work uses actual _advance physics, not immediate state flips.
        pre_stamina=body.stamina
        pre_fatigue=body.fatigue
        actual=_advance(body,room,world,gear,COST_MIN[action],at_home=True)
        completed=bool(actual>=COST_MIN[action]-1e-6 and not body.terminal)
        if action in (PREPARE,INSULATE,CHOP):
            ratio=min(1.0,actual/COST_MIN[action])
            body.stamina=max(0.0,pre_stamina-STAMINA_COST[action]*ratio)
            per_h={
                PREPARE:PACK.fatigue_per_h,
                INSULATE:SEAL.fatigue_per_h,
                CHOP:HEAVY.fatigue_per_h,
            }[action]
            body.fatigue=min(100.0,max(
                body.fatigue,pre_fatigue+per_h*actual/60.0
            ))
            if completed:
                if action==PREPARE:
                    body.packed=True
                elif action==INSULATE:
                    room.cooling_rate*=0.5
                    room.sealed=True
                elif action==CHOP:
                    room.furniture-=1
                    room.fuel+=HEAVY.fuel
    after={"minute":round(body.elapsed_minutes,6),
           "core":round(body.core_c,5),
           "stamina":round(body.stamina,5),
           "fatigue":round(body.fatigue,5),
           "fuel":round(room.fuel,5),
           "furniture":room.furniture,
           "packed":body.packed,"sealed":room.sealed,"pending":pending}
    return {"choice":action,"completed":completed,
            "actual_minutes":round(actual,6),
            "before":before,"after":after,
            "observed":{"core_delta":round(body.core_c-before["core"],5),
                        "stamina_delta":round(body.stamina-before["stamina"],5),
                        "fuel_delta":round(room.fuel-before["fuel"],5),
                        "time_delta":round(actual,6),
                        "job_completed":not pending,
                        "new_shelter_insulation":not before["sealed"] and room.sealed,
                        "new_route_preparation":not before["packed"] and body.packed,
                        "furniture_used":before["furniture"]-room.furniture}}


def _finish_dawn(body,room,world,gear,dawn_target):
    """Continue the SAME physical world to the next target or terminal."""
    if body.terminal:
        return 0.0
    left=dawn_target-body.elapsed_minutes
    if left< -1e-5:
        raise AssertionError("clock overran target dawn")
    return _advance(body,room,world,gear,max(0.0,left),at_home=True)


def _case(world_name,core,initial_fuel,stamina,fatigue,night_option):
    world=World.load("district_v0",world_name)
    start=Body(core_c=core,stamina=stamina,fatigue=fatigue,
               elapsed_minutes=world.day_length-world.dawn_min)
    shelter=Room(fuel=initial_fuel,furniture=2)
    kit=Equipment()
    actor=Agent("local",world)
    # Fixed publicly announced work slot: 08:00..11:00 next morning.
    deadline=DAY_MINUTES+MAX_DAWN_DELAY
    prior=copy.deepcopy(start)
    prior_room=copy.deepcopy(shelter)
    planned=work_opportunity(prior,deadline,True)
    live_night=play(night_option+": option",world.air_temp_c,shelter,start,
                    actor.beliefs,hours_of_night=world.night_hours)
    dawn_reached=bool(not start.terminal and
                      abs(start.elapsed_minutes-DAY_MINUTES)<1e-4)
    clock_only=copy.deepcopy(prior)
    clock_only.elapsed_minutes=DAY_MINUTES
    time_control=work_opportunity(clock_only,deadline,True)
    actual_gate=work_opportunity(start,deadline,True) if dawn_reached else None
    # A lost opportunity must be viable with identical next-morning clock
    # and pre-night physical Body; a DEAD/SKIPPED dawn is not a morning choice.
    lost=bool(dawn_reached and time_control["available"] and
              not actual_gate["available"])
    gained=bool(dawn_reached and not time_control["available"] and
                actual_gate["available"])
    ret={"input":{"variant":world_name,"core":core,"initial_fuel":initial_fuel,
                   "stamina":stamina,"fatigue":fatigue,
                   "night_option":night_option},
         "deadline_minute":deadline,
         "intention_at_evening":MAIN,
         "evening_job_opportunity":planned,
         "same_time_without_physical_night":time_control,
         "real_night":{"reached_next_dawn":dawn_reached,
                       "hours":live_night["night_elapsed_h"],
                       "cold_wakes":live_night["woke_cold"],
                       "slept_hours":live_night["slept_hours"],
                       "awake_hours":live_night["awake_at_night_h"],
                       "fire_out":live_night["fire_out_at"],
                       "fuel_spent":round(shelter.burned_fuel_total,5),
                       "room_sealed":shelter.sealed,
                       "packed":start.packed,
                       "terminal":start.terminal},
         "actual_morning_job_opportunity":actual_gate,
         "physically_lost_job_opportunity":lost,
         "physically_gained_job_opportunity":gained,
         "policies":{}}
    if not dawn_reached:
        return ret
    # Both post-night policies start from the identical ACTUAL morning.
    for policy in ("opportunity","continue_job"):
        b=copy.deepcopy(start)
        r=copy.deepcopy(shelter)
        g=copy.deepcopy(kit)
        a=copy.deepcopy(actor)
        first=decide(a,b,r,deadline,True,policy=policy,reported_plan=MAIN)
        outcomes=[]
        pending=True
        if first["choice"]:
            outcome=execute(b,r,world,g,first["choice"],deadline,pending)
            pending=outcome["after"]["pending"]
            outcomes.append(outcome)
        # A fallback does not magic away a pending job. Recheck once, after
        # the real resource/time/stamina/temperature consequences of first action.
        # Attempt only if now truly feasible and within scheduled deadline.
        follow_available=work_opportunity(b,deadline,pending)
        if pending and follow_available["available"]:
            follow=execute(b,r,world,g,MAIN,deadline,pending)
            pending=follow["after"]["pending"]
            outcomes.append(follow)
        # Advance all remaining daylight on the shared physical clock.
        reached_dusk=False
        reached_next_next_dawn=False
        if not b.terminal:
            _finish_dawn(b,r,world,g,world.day_length-world.dawn_min+DAY_MINUTES)
            reached_dusk=not b.terminal
        second_night=None
        if reached_dusk:
            second_night=play("B: rest",world.air_temp_c,r,b,a.beliefs,
                              hours_of_night=world.night_hours)
            reached_next_next_dawn=not b.terminal and abs(
                b.elapsed_minutes-2*DAY_MINUTES
            )<1e-4
        ret["policies"][policy]={
            "first_decision":first,
            "actions":outcomes,
            "follow_up_job_feasible":follow_available,
            "work_completed":not pending,
            "work_missed_by_deadline":pending and b.elapsed_minutes>deadline,
            "second_night":{
                "completed_next_dawn":reached_next_next_dawn,
                "cold_wakes":second_night["woke_cold"] if second_night else None,
                "slept_h":second_night["slept_hours"] if second_night else None,
            },
            "final":{
                "minute":round(b.elapsed_minutes,5),
                "core":round(b.core_c,4),"fatigue":round(b.fatigue,4),
                "stamina":round(b.stamina,4),"fuel":round(r.fuel,4),
                "furniture":r.furniture,"sealed":r.sealed,
                "packed":b.packed,"terminal":b.terminal,
                "pending_work":pending
            }
        }
    return ret


def study()->dict:
    # No artificially repeated seeds: each physical dusk case is a distinct
    # environment/resource/body/preparation intervention, not human samples.
    conditions=list(product(
        ("A_safe","B_readable","C_unreadable"),
        (35.7,36.8),
        (0,1,3,6),
        (55.0,85.0),
        (10.0,55.0),
        ("B","C","D"),
    ))
    counters=Counter()
    actions=defaultdict(Counter)
    checks=Counter()
    examples=[]
    all_rows=[]
    for condition in conditions:
        row=_case(*condition)
        counters["constructed_evenings"]+=1
        if row["real_night"]["reached_next_dawn"]:
            counters["real_mornings"]+=1
            if row["physically_lost_job_opportunity"]:
                counters["physically_lost_work_opportunity"]+=1
            if row["physically_gained_job_opportunity"]:
                counters["physically_gained_work_opportunity"]+=1
            if row["same_time_without_physical_night"]["available"] and row[
                "actual_morning_job_opportunity"]["available"]:
                counters["work_remained_possible"]+=1
            for mode,d in row["policies"].items():
                action=d["first_decision"]["choice"]
                actions[mode][action]+=1
                counters[mode+":work_completed"]+=int(d["work_completed"])
                counters[mode+":second_dawn"]+=int(d["second_night"]["completed_next_dawn"])
                counters[mode+":missed_work"]+=int(d["work_missed_by_deadline"])
                counters[mode+":terminal"]+=int(d["final"]["terminal"])
                counters[mode+":prepared"]+=int(d["final"]["packed"])
                counters[mode+":sealed"]+=int(d["final"]["sealed"])
                counters[mode+":furniture_used"]+=2-d["final"]["furniture"]
                if action not in [o["option"] for o in d["first_decision"]["alternatives"]
                                   if o["available"]]:
                    checks["unavailable_choice"]+=1
                for event in d["actions"]:
                    bef,aft=event["before"],event["after"]
                    if abs(aft["minute"]-bef["minute"]-event["actual_minutes"])>1e-4:
                        checks["unbilled_time"]+=1
                    if aft["fuel"]>bef["fuel"]+(
                        HEAVY.fuel if event["choice"]==CHOP and event["completed"] else 0
                    )+1e-4:
                        checks["free_fuel"]+=1
                    if aft["furniture"]<bef["furniture"] and not (
                        event["choice"]==CHOP and event["completed"]
                    ):
                        checks["unpaid_furniture"]+=1
                    if event["choice"]==MAIN and event["completed"] and (
                        not bef["pending"] or aft["pending"] or
                        bef["stamina"]<WORK_START_STAMINA
                    ):
                        checks["fake_work"]+=1
                    if event["choice"]!=MAIN and event["completed"] and (
                        event["choice"]==PREPARE and not aft["packed"] or
                        event["choice"]==INSULATE and not aft["sealed"]
                    ):
                        checks["missing_persistent_benefit"]+=1
                if d["final"]["furniture"]<0 or d["final"]["fuel"]< -1e-8:
                    checks["negative_resource"]+=1
                if d["second_night"]["completed_next_dawn"] and (
                    abs(d["final"]["minute"]-2*DAY_MINUTES)>1e-4
                ):
                    checks["fake_second_dawn"]+=1
            if row["physically_lost_job_opportunity"]:
                a=row["policies"]["opportunity"]
                b=row["policies"]["continue_job"]
                if a["first_decision"]["choice"]!=b["first_decision"]["choice"]:
                    counters["lost_opportunity_changed_real_action"]+=1
                    counters["lost:"+a["first_decision"]["choice"]]+=1
                if len(examples)<22:
                    examples.append(row)
        else:
            counters["nights_without_next_dawn"]+=1
            if row["policies"]:
                checks["terminal_issued_morning_action"]+=1
        all_rows.append(row)
    return {
        "design":{"constructed_evenings":len(conditions),"paired_morning_policies":2,
                  "real_night_baseline":"evening_run.play / existing Body/Room",
                  "second_real_night_in_each_policy":True,
                  "known_job_deadline_minutes_after_dawn":MAX_DAWN_DELAY,
                  "human_participants":0},
        "counts":dict(counters),
        "first_action_by_policy":{k:dict(v) for k,v in actions.items()},
        "examples":examples,
        "all_cases":all_rows,
        "checks":{k:checks[k] for k in (
            "unavailable_choice","unbilled_time","free_fuel",
            "unpaid_furniture","fake_work","missing_persistent_benefit",
            "negative_resource","fake_second_dawn",
            "terminal_issued_morning_action"
        )},
        "limits":[
            "Controlled evening body, resources and preparation options, NOT a complete prior outdoor day; full day/night lab remains D1.9.",
            "No stochastic weather outside, no extra made-up player samples or human fun metrics.",
            "Main task and deadline are researcher-authored and known in advance; reasons are rule-based hypotheses, not learned free goals.",
            "Work is feasible only when core>=36, fatigue<=70, stamina>=60 and a real 60-minute slot remains.",
            "Alternate preparation is concrete: PACK speeds a later trip in the canonical simulator, SEAL halves room cooling, CHOP uses finite furniture and stamina.",
            "Automatic stove ignition and reactive overnight furniture chopping are legacy night physics, NOT chosen morning intent.",
            "Paired policies share identical first night, but can physically diverge after different morning choices; no post-divergence same-state claims.",
        ],
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--json",required=True)
    args=p.parse_args()
    report=study()
    with open(args.json,"w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({
        "design":report["design"],
        "counts":report["counts"],
        "first_action_by_policy":report["first_action_by_policy"],
        "checks":report["checks"],
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
