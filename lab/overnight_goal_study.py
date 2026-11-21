"""D1.9 — paired actual dawn → trip/job → shelter → night → next dawn.

The ONLY experimental intervention is whether the actor updates the active
goal from observed post-night conditions or retains the originally assigned
goal. Both policies start with identical weather, body, rooms, loot, memories,
equipment and goal. The real canonical survival loop owns the clock, stove,
night wakes, weariness and terminal boundary. Never score a fictitious dawn.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import product
from statistics import mean

from .goal_priority_study import PROTECT, FUEL, WORK, GOALS
from .survival_loop import run
from .overnight_goal_policy import RECOVER, FORAGE, FINISH

VARIANTS=("A_safe","B_readable","C_unreadable")
PROFILES=("local","novice")
POLICIES=("adaptive","frozen")
START_FUELS=(1,2,4)


def audit_history(story: dict) -> dict:
    errs=Counter()
    counts=Counter()
    history=story["history"]
    for index,day in enumerate(history):
        cont=day["goal_continuity"]
        if cont is None:
            errs["missing_intent_trace"]+=1
            continue
        if cont["morning_decision"] is not None:
            choice=cont["morning_decision"]["choice"]
            if choice is not None and choice not in [
                x["option"] for x in cont["morning_decision"]["alternatives"]
                if x["available"]
            ]:
                errs["unavailable_choice"]+=1
            if choice==RECOVER and day["day_trip"]["went_out"]:
                errs["recovery_choice_became_trip"]+=1
            if choice==FINISH and not cont["work_action"] and (
                day["departure_minute"] is not None
            ):
                errs["chosen_work_not_executed"]+=1
            if choice==FORAGE and not day["day_trip"]["went_out"]:
                if day["terminal_at_minute"] is not None:
                    counts["outdoor_trip_prevented_by_terminal"]+=1
                elif any(
                    x["available"] and x["option"]==FORAGE
                    for x in cont["morning_decision"]["alternatives"]
                ):
                    errs["forage_choice_silently_canceled"]+=1
        if day["completed_dawn"]:
            if abs(day["minutes_accounted"]-1440)>1e-4 or day["next_dawn_minute"] is None:
                errs["false_dawn"]+=1
        else:
            if day["next_dawn_minute"] is not None or day["minutes_accounted"]>=1440+1e-5:
                errs["fictitious_continuation"]+=1
        if day["fuel_next_dawn"] > (
            day["fuel_at_dawn"]+day["fuel_delivered"]
            +4*(day["furniture_at_dawn"]-day["furniture_next_dawn"])+1e-4
        ):
            errs["free_fuel"]+=1
        if any(x<0 for x in day["remaining_loot"].values()):
            errs["negative_loot"]+=1
        if index and history[index-1]["completed_dawn"]:
            prev=history[index-1]
            if (abs(prev["core_next_dawn"]-day["core_at_dawn"])>1e-4
                or abs(prev["fuel_next_dawn"]-day["fuel_at_dawn"])>1e-4
                or prev["furniture_next_dawn"]!=day["furniture_at_dawn"]):
                errs["broken_physical_continuity"]+=1
            anticipated=prev["goal_continuity"]["after_night"]["goal"]
            if story["goal_policy"]=="adaptive" and cont["goal_at_this_dawn"]!=anticipated:
                errs["goal_not_carried_over"]+=1
            if story["goal_policy"]=="frozen" and (
                cont["goal_at_this_dawn"]!=story["assigned_initial_goal"]
            ):
                errs["frozen_goal_changed"]+=1
            previous_cont=prev["goal_continuity"]
            preview=(
                previous_cont["next_dawn_adaptive_preview"]
                if story["goal_policy"]=="adaptive"
                else previous_cont["next_dawn_frozen_preview"]
            )
            current=cont["morning_decision"]
            if preview and current and (
                preview["choice"]!=current["choice"] or
                preview["goal"]!=current["goal"]
            ):
                errs["next_dawn_choice_not_carried"]+=1
            if (story["goal_policy"]=="adaptive"
                and previous_cont["physical_night_changed_pressure"]):
                counts["physical_night_pressure_carried_into_real_next_day"]+=1
                no_night=previous_cont["next_dawn_time_only_control_preview"]
                if (preview and current and no_night and
                    current["choice"]!=no_night["choice"]):
                    counts["actual_next_day_action_changed_due_physical_night"]+=1
                    if current["choice"]==FORAGE:
                        counts["next_day_changed_to_forage"]+=1
                    if current["choice"]==RECOVER:
                        counts["next_day_changed_to_recover"]+=1
                    if current["choice"]==FINISH:
                        counts["next_day_changed_to_work"]+=1
            if day["gear_wetness_at_next_dawn"]!=prev["gear_wetness_at_next_dawn"]:
                errs["gear_reset"]+=1
            counts["real_second_dawns"]+=1
        if day["day_trip"]["went_out"]:
            counts["actual_outings"]+=1
            if day["fuel_delivered"]==0:
                counts["outings_returned_empty_or_terminal"]+=1
        if cont["work_action"]:
            event=cont["work_action"]
            if event["completed"] and day["pending_work_at_next_dawn"]:
                errs["phantom_unfinished_work"]+=1
            if event["completed"] and event["total_minutes"]<60-1e-5:
                errs["free_work"]+=1
        b=cont["before_night"]
        a=cont["after_night"]
        if b is not None and a is not None and day["completed_dawn"]:
            counts["paired_before_after_night"]+=1
            time_only=cont["time_only_control_pressure"]
            if cont["changed_pressure_during_night"]:
                counts["pre_to_post_night_pressure_changed"]+=1
                preview=cont["next_dawn_adaptive_preview"]
                control=cont["next_dawn_pre_night_pressure_preview"]
                if preview and control and preview["choice"]!=control["choice"]:
                    counts["pre_to_post_night_action_changed"]+=1
            if cont["physical_night_changed_pressure"]:
                counts["physical_night_changed_pressure"]+=1
                preview=cont["next_dawn_adaptive_preview"]
                control=cont["next_dawn_time_only_control_preview"]
                if preview and control and preview["choice"]!=control["choice"]:
                    counts["physical_night_changed_action_vs_time_only"]+=1
            if (time_only is not None and
                time_only["goal"]!=cont["before_night"]["goal"]):
                counts["clock_advance_changed_pressure"]+=1
                if not cont["physical_night_changed_pressure"]:
                    counts["clock_only_pressure_revision"]+=1
            if (cont["next_dawn_adaptive_preview"] and
                cont["next_dawn_frozen_preview"] and
                cont["next_dawn_adaptive_preview"]["choice"]!=
                cont["next_dawn_frozen_preview"]["choice"]):
                counts["adaptive_vs_initial_goal_on_same_postnight_state"]+=1
            if day["night"]["woke_cold"]:
                counts["nights_with_cold_wake"]+=1
    if story["days_completed"] != sum(d["completed_dawn"] for d in history):
        errs["credited_incomplete_day"]+=1
    if abs(story["elapsed_minutes"]-
           sum(d["minutes_accounted"] for d in history))>0.001:
        errs["lost_simulation_time"]+=1
    if story["terminal_at_minute"] is not None and (
        abs(story["terminal_at_minute"]-story["elapsed_minutes"])>0.001
    ):
        errs["terminal_after_time"]+=1
    return {"checks":dict(errs),"counts":dict(counts)}


def study(seeds: int = 12,days: int = 3)->dict:
    if not 1<=seeds<=30 or not 2<=days<=5:
        raise ValueError("seeds 1..30, days 2..5")
    violations=Counter()
    global_counts=Counter()
    policy_stats=defaultdict(Counter)
    transitions=[]
    cases=[]
    per_variant=defaultdict(Counter)
    for variant,profile,goal,initial_fuel,seed in product(
        VARIANTS,PROFILES,GOALS,START_FUELS,range(1,seeds+1)
    ):
        arms={
            mode:run(seed,days,variant=variant,profile=profile,
                     initial_furniture=2,heating_policy="dusk",
                     goal_policy=mode,initial_goal=goal,
                     initial_fuel=initial_fuel)
            for mode in POLICIES
        }
        r0=arms["adaptive"]["history"][0]
        r1=arms["frozen"]["history"][0]
        # The FIRST full physical episode must be bit-for-bit equivalent
        # except explicit labels about the experimental policy.
        for key in ("world_weather","fuel_next_dawn","core_next_dawn",
                    "furniture_next_dawn","pending_work_at_next_dawn",
                    "minutes_accounted","remaining_loot","day_trip","night"):
            if r0[key]!=r1[key]:
                violations["nonidentical_initial_physics"]+=1
        for i in range(min(len(arms["adaptive"]["history"]),
                           len(arms["frozen"]["history"]))):
            if (arms["adaptive"]["history"][i]["world_weather"]!=
                arms["frozen"]["history"][i]["world_weather"]):
                violations["unpaired_weather"]+=1
        key=f"{variant}/{profile}/{goal}/fuel{initial_fuel}/seed{seed}"
        sample={"case":key}
        for mode,story in arms.items():
            assessment=audit_history(story)
            violations.update(assessment["checks"])
            global_counts.update({f"{mode}:{k}":v
                                  for k,v in assessment["counts"].items()})
            stats=policy_stats[mode]
            stats["trials"]+=1
            stats["days_completed"]+=story["days_completed"]
            stats["elapsed_minutes"]+=story["elapsed_minutes"]
            stats["work_completed"]+=int(story["pending_work_at_end"] is False)
            stats["fuel_end_milli"]+=round(
                story["history"][-1]["fuel_next_dawn"]*1000
            )
            stats["terminal"]+=int(story["terminal_at_minute"] is not None)
            stats["trips"]+=sum(int(d["day_trip"]["went_out"]) for d in story["history"])
            stats["morning_recoveries"]+=sum(
                int(d["goal_continuity"]["morning_decision"]["choice"]
                    =="остаться дома и восстановиться")
                for d in story["history"]
                if d["goal_continuity"]["morning_decision"] is not None
            )
            per_variant[f"{variant}/{mode}"]["days"]+=story["days_completed"]
            sample[mode]={
                "days_completed":story["days_completed"],
                "elapsed_minutes":story["elapsed_minutes"],
                "last_goal":story["history"][-1]["goal_continuity"]["after_night"]["goal"],
                "work_done":story["pending_work_at_end"] is False,
                "end_reason":story["end_reason"],
            }
        for day in arms["adaptive"]["history"]:
            cont=day["goal_continuity"]
            if (day["completed_dawn"] and cont["physical_night_changed_pressure"]
                and len(transitions)<30):
                transitions.append({
                    "case":key,"day":day["day"],
                    "initial_goal":cont["goal_at_this_dawn"],
                    "before_night":cont["before_night"],
                    "after_night":cont["after_night"],
                    "time_only_control":cont["time_only_control_pressure"],
                    "night_actual":{
                        "wakes":day["night"]["woke_cold"],
                        "fuel_burned":cont["night_actual_fuel_spent"],
                        "core_before":cont["before_night"]["cues"]["core_c"],
                        "core_after":cont["after_night"]["cues"]["core_c"],
                    },
                    "adapted_next":cont["next_dawn_adaptive_preview"],
                    "old_pressure_next":cont["next_dawn_pre_night_pressure_preview"],
                    "time_only_next":cont["next_dawn_time_only_control_preview"],
                })
        if len(cases)<24:
            cases.append(sample)
    report={
        "design":{"seeds":seeds,"days":days,
                  "pair_count":seeds*len(VARIANTS)*len(PROFILES)*len(GOALS)*len(START_FUELS),
                  "starting_fuel_levels":START_FUELS,
                  "paired_arms":POLICIES,
                  "initial_goals":GOALS,
                  "weather_paired":True,
                  "real_day_trip_and_night":True,
                  "initial_goal_assigned_by_researcher":True,
                  "human_participants":0},
        "counts":dict(global_counts),
        "by_variant":{k:dict(v) for k,v in per_variant.items()},
        "outcomes":{
            mode:{
                "trials":a["trials"],
                "mean_days_completed":round(a["days_completed"]/a["trials"],4),
                "mean_elapsed_hours":round(a["elapsed_minutes"]/60/a["trials"],4),
                "work_completed":a["work_completed"],
                "mean_fuel_remaining":round(a["fuel_end_milli"]/1000/a["trials"],4),
                "terminal":a["terminal"],
                "trips":a["trips"],
                "morning_recoveries":a["morning_recoveries"],
            } for mode,a in policy_stats.items()
        },
        "night_to_dawn_examples":transitions,
        "case_samples":cases,
        "checks":{k:violations[k] for k in (
            "missing_intent_trace","unavailable_choice","false_dawn",
            "fictitious_continuation","free_fuel","negative_loot",
            "broken_physical_continuity","goal_not_carried_over",
            "frozen_goal_changed","gear_reset","phantom_unfinished_work",
            "free_work","credited_incomplete_day","lost_simulation_time",
            "terminal_after_time","nonidentical_initial_physics",
            "unpaired_weather","recovery_choice_became_trip",
            "chosen_work_not_executed","forage_choice_silently_canceled",
            "next_dawn_choice_not_carried"
        )},
        "limits":[
            "Initial goals experimentally assigned; pressure formation is explicit state rules, not learned independent values.",
            "A genuine dawn only counts if the actual real night completes; terminal partial days are not credited.",
            "Same Body/Room/Agent/world/loot persists across dawns WITHIN each arm; paired arms physically diverge after their first different choice.",
            "Strict physical-night attribution compares observed post-night pressure against the PRE-night core/fatigue/stamina/fuel carried to the SAME post-night clock. Deadline-only changes are counted separately.",
            "Strict same-state goal contrast uses previews after the real night, not researcher-only future outcomes.",
            "Seed weather repeats across fixed starting-fuel controls; these are paired conditions, not independent human sessions.",
            "One persistent DRY Equipment object (no evolving garment wetness in canonical run_day); this does not integrate D1.7 clothing physics.",
            "One finite pending 60-minute job; finished work not respawned.",
            "Automatic dusk ignition and night evening choices remain the same canonical baseline in both arms.",
            "No claim of actual human fun or self-generated long-run goals.",
        ],
    }
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",type=int,default=12)
    p.add_argument("--days",type=int,default=3)
    p.add_argument("--json",required=True)
    args=p.parse_args()
    report=study(args.seeds,args.days)
    with open(args.json,"w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({
        "design":report["design"],
        "counts":report["counts"],
        "outcomes":report["outcomes"],
        "checks":report["checks"]
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
