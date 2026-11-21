"""Trace the complete evening->night->next-dawn chain, not a survival score.

Night observations can seed an opt-in next morning replan. Baselines stay
untouched. Absence of replans is an empirical negative result, not CI failure.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from statistics import mean

from .survival_loop import run

VARIANTS=("A_safe","B_readable","C_unreadable")
PROFILES=("local","novice")


def analyze(seeds:int=20,days:int=5)->dict:
    if not 1<=seeds<=100 or not 2<=days<=30:
        raise ValueError("seeds 1..100; days 2..30")
    flags=Counter()
    failures=Counter()
    examples={}
    rows={}
    for variant in VARIANTS:
        rows[variant]={}
        for mode in ("legacy","night_replan"):
            stories=[]
            choices=Counter()
            goals=Counter()
            for profile in PROFILES:
                for seed in range(1,seeds+1):
                    story=run(seed,days,variant=variant,profile=profile,
                              heating_policy="agent",
                              carry_night_intent=(mode=="night_replan"))
                    stories.append(story)
                    record=story["history"]
                    for i,d in enumerate(record):
                        flags["days_started"]+=1
                        if d["evening_decision"] is not None:
                            flags["evening_decisions"]+=1
                            ev=d["evening_decision"]
                            choices[ev["choice"][:1]]+=1
                            if not ev["outcome"] or not ev["reason"] or not ev["alternatives"]:
                                failures["incomplete_evening_decision"]+=1
                        if d["night_formed_next_intention"] is not None:
                            flags["night_intentions"]+=1
                            goals[d["night_formed_next_intention"]["intention"]]+=1
                        if i==0 and d["arriving_intention"] is not None:
                            failures["invented_inherited_first_intention"]+=1
                        if i>0:
                            flags["linked_dawns"]+=1
                            previous=record[i-1]["night_formed_next_intention"]
                            if d["arriving_intention"]!=previous:
                                failures["lost_night_context"]+=1
                            if previous and previous["wants_recovery"]:
                                flags[mode+":recovery_intent_arrived"]+=1
                                if d["evening"]["intention"].startswith("короткая вылазка"):
                                    flags[mode+":reduced_evening_plan"]+=1
                                if d["day_trip"]["decisions"] and any(
                                    x["choice"]=="остаться и восстановиться"
                                    for x in d["day_trip"]["decisions"]
                                ):
                                    flags[mode+":stayed_home"]+=1
                        if not d["end_reason"] and d["completed_dawn"]:
                            flags["completed_dawns"]+=1
                        if d["completed_dawn"] and abs(d["minutes_accounted"]-1440)>1e-4:
                            failures["wrong_full_day_clock"]+=1
                        if d["terminal_at_minute"] is not None and (
                            abs(d["terminal_at_minute"]-story["elapsed_minutes"])>1e-4
                        ):
                            failures["wrong_terminal_clock"]+=1
                    if seed==1 and profile=="local":
                        examples[f"{variant}/{mode}"]=[
                            {"day":d["day"],"source":d["arriving_intention"],
                             "day_intention":d["day_trip"]["next_intention"],
                             "evening":d["evening_decision"],
                             "night_to_next":d["night_formed_next_intention"],
                             "wakes":d["night"].get("woke_cold",0),
                             "next_dawn":d["completed_dawn"]}
                            for d in record
                        ]
            rows[variant][mode]={
                "runs":len(stories),
                "mean_actual_elapsed_h":round(mean(s["elapsed_minutes"]/60 for s in stories),3),
                "mean_started_days":round(mean(s["days_started"] for s in stories),3),
                "evening_choices":dict(choices),
                "night_formed_goals":dict(goals),
                "ending_causes":dict(Counter(s["end_reason"] or "horizon" for s in stories)),
            }
    return {
        "design":{"seeds_per_variant_profile":seeds,"days":days,
                  "modes":("legacy","night_replan"),"policies":"agent",
                  "cases":len(VARIANTS)*len(PROFILES)*seeds*2,
                  "no_human_participants":True},
        "results":rows,"observations":dict(flags),
        "checks":{k:failures[k] for k in (
            "incomplete_evening_decision","invented_inherited_first_intention",
            "lost_night_context","wrong_full_day_clock","wrong_terminal_clock"
        )},
        "example_chains":examples,
        "limits":[
            "An explicit opt-in experiment, NOT proof of autonomous human-like intent.",
            "Day travel still prioritizes loot; the optional replan can stay home if cold and fuel permits.",
            "No future loot/weather oracle; only last night's recorded condition feeds next dawn.",
            "Terminal partial days have no invented next dawn; no next intention after stop.",
            "If no real wake and replans happen, preserve that negative result.",
            "Nothing here measures player enjoyment.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",type=int,default=20)
    p.add_argument("--days",type=int,default=5)
    p.add_argument("--json",required=True)
    a=p.parse_args()
    result=analyze(a.seeds,a.days)
    with open(a.json,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({"design":result["design"],"results":result["results"],
                      "observations":result["observations"],
                      "checks":result["checks"]},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
