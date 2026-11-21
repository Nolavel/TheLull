"""D1.7: distinguish repeatable route costs from a one-off witnessed storm.

Predeclared training *sequences* on the same edge. All policies see identical
physical wet trips. A new observed-weather cue is presented at next departure;
the weather FUTURE is never passed to choice. Compare:
  ema          = old ordinary beliefs, no signed risk bonus
  last_error   = D1.6 unconditioned last surprise
  contextual   = signed, matching-weather repeated evidence
  causal_wait  = same contextual evidence, plus optional wait when a storm has
                 repeatedly been worse than a calm route (local knowledge only).
A wait burns real minutes in a cold shelter but does not burn fuel.
This is NOT an autonomous multi-day physical survival sequence; each observed
trip restarts at the same baseline body/room to isolate belief learning.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from statistics import mean

from .agent import Agent, edge_key
from .body import Body
from .clothing_adaptation_study import choose_clothing, make_world, restore_outcome
from .clothing_followthrough import followup_work
from .clothing_payoff_study import DISTANCE_MULTIPLIERS, VARIANTS, evaluate
from .coupled_microloop import DRY, EXPLORE, Equipment, _advance
from .evening import Room
from .world import DayWeather

ROUTE_ID="home→house_a→home"
WAIT="переждать ветер перед выходом"
POLICIES=("ema","last_error","contextual","causal_wait")
PATTERNS={
    "always_calm":(("calm","calm","calm"),"calm"),
    "late_storm_spike":(("calm","calm","storm"),"calm"),
    "storm_then_clears":(("storm","calm","calm"),"calm"),
    "storm_repeats":(("calm","storm","storm"),"storm"),
    "storm_only":(("storm","storm","storm"),"storm"),
}
PROFILES=("local","novice")
DISTANCES=(1,8,24,40)
WAIT_MINUTES=90


def weather_for(world, condition: str, seed: int, *, heldout=False) -> DayWeather:
    """Observable present weather; unseen storm duration/arrival can vary.

    Training storms vary from 60–120 minutes by seed (usual model range).
    Heldout calm sometimes turns stormy AFTER departure and present storm
    sometimes ends earlier; the agent sees only wind at its current position.
    Same weather and seed always apply to all policies in one paired case.
    """
    if condition not in ("calm","storm"):
        raise ValueError("unknown weather condition")
    dawn=world.dawn_min
    if not heldout:
        if condition=="storm":
            start=dawn-(seed*7)%30
            return DayWeather(start,start+60+(seed*11)%61,None)
        return DayWeather(None,None,None)
    if condition=="calm":
        start=dawn+60+(seed*7)%120
        return (DayWeather(start,start+60+(seed*13)%61,None)
                if seed%3==0 else DayWeather(None,None,None))
    start=dawn-(seed*7)%30
    return DayWeather(start,start+60+(seed*17)%61,None)


def observed_legs_cue(world, weather: DayWeather, trip: dict) -> str:
    """Only sample experienced wind when a leg begins, not storm schedule."""
    seen=[]
    absolute=world.dawn_min+trip["departure_minute"]
    for leg in trip["legs"]:
        seen.append("storm" if weather.is_storm(absolute) else "calm")
        absolute+=leg["minutes_billed"]
    return seen[0] if seen and all(x==seen[0] for x in seen) else "mixed"


def actor_forecast(actor: Agent, weather_cue: str) -> dict:
    """Frozen before departure, all parameters from the actor's own beliefs."""
    route=actor.beliefs.edge_minutes[edge_key("home","house_a")]
    minutes=2*route["storm" if weather_cue=="storm" else "calm"]
    return {
        "minutes":minutes,
        "stamina":minutes/60*actor.beliefs.wet_walk_stamina_per_h_est,
        "core":minutes/60*actor.beliefs.wet_walk_core_loss_per_h_est,
    }


def observe_complete(actor: Agent, world, weather, trip: dict,
                     prediction: dict, *, mode: str) -> dict:
    """Never pretend a terminal partial trip is a full route observation."""
    if not trip["completed_return"]:
        return {"accepted":False,"reason":"incomplete trip","prediction":prediction}
    cue=observed_legs_cue(world,weather,trip)
    actual={
        "minutes":trip["travel_minutes"],
        "stamina":trip["walking_stamina_demand"],
        "core":max(0,trip["core_at_departure"]-trip["core_after_route"]),
    }
    error={name:actual[name]-prediction[name] for name in actual}
    # One common edge observation for all policies; storm state comes from
    # actual wind at the departure, *not* hidden storm duration in weather.
    first_storm=weather.is_storm(world.dawn_min+trip["departure_minute"])
    actor.observe_edge("home","house_a",first_storm,
                       trip["legs"][0]["minutes_billed"])
    if mode != "contextual" or cue=="calm":
        # Contextual learner will not poison its normal-weather estimate with
        # a storm's higher core cooling. Storm costs stay separately stored.
        actor.beliefs.observe_wet_walk(
            hours=trip["travel_minutes"]/60,
            stamina_demand=actual["stamina"],
            core_before=trip["core_at_departure"],
            core_after=trip["core_after_route"],
        )
    if mode=="last_error":
        actor.beliefs.observe_trip_prediction(
            ROUTE_ID,
            predicted_minutes=prediction["minutes"],actual_minutes=actual["minutes"],
            predicted_stamina_demand=prediction["stamina"],
            actual_stamina_demand=actual["stamina"],
            predicted_core_loss=prediction["core"],
            actual_core_loss=actual["core"],
        )
    if mode=="contextual":
        actor.beliefs.observe_contextual_trip(
            ROUTE_ID,weather_cue=cue,
            predicted_minutes=prediction["minutes"],actual_minutes=actual["minutes"],
            predicted_stamina=prediction["stamina"],actual_stamina=actual["stamina"],
            predicted_core=prediction["core"],actual_core=actual["core"],
        )
    return {"accepted":True,"observed_weather":cue,"predicted":prediction,
            "actual":actual,"signed_error":error,
            "route_belief_calm":actor.beliefs.edge_minutes[
                edge_key("home","house_a")]["calm"]}


def choose_next(actor: Agent, world, *, cue: str, mode: str) -> dict:
    if mode=="ema":
        decision=choose_clothing(actor,Body(),Room(fuel=world.start_fuel),
                                 Equipment(wetness=1),assume_storm=(cue=="storm"))
        assessment=None
    elif mode=="last_error":
        decision=choose_clothing(actor,Body(),Room(fuel=world.start_fuel),
                                 Equipment(wetness=1),assume_storm=(cue=="storm"),
                                 consider_prediction_error=True)
        assessment=None
    else:
        assessment=actor.beliefs.contextual_assessment(
            ROUTE_ID,current_cue=cue
        )
        decision=choose_clothing(actor,Body(),Room(fuel=world.start_fuel),
                                 Equipment(wetness=1),assume_storm=(cue=="storm"),
                                 contextual_adjustment=assessment["bonus"])
    d=asdict(decision)
    possible_wait=(cue=="storm" and actor.beliefs.knows_storms_pass)
    direct=actor.beliefs.edge_minutes[edge_key("home","house_a")]
    predicted_saved_minutes=2*(direct["storm"]-direct["calm"])
    # The third alternative does not exist for actors who do not believe
    # storms pass. Prediction is subjective; no true end time is consulted.
    d["alternatives"].append({
        "option":WAIT,"available":possible_wait,
        "predicted_delay_min":actor.expected_storm_left(0) if possible_wait else None,
        "predicted_route_time_saving_min":predicted_saved_minutes if possible_wait else None,
        "basis":"сохранить дрова, заплатить временем и холодом комнаты",
    })
    d["wait_gate"]={
        "visible_storm":cue=="storm",
        "storm_finiteness_known":actor.beliefs.knows_storms_pass,
        "storm_specific_excess_evidence":bool(
            assessment and assessment["attribution"]=="storm_specific_excess"),
        "predicted_savings_exceed_wait":bool(
            possible_wait and predicted_saved_minutes >
            actor.expected_storm_left(0)*1.1),
        "predicted_savings_minutes":round(predicted_saved_minutes,5),
    }
    if (mode=="causal_wait" and possible_wait and assessment is not None
        and assessment["attribution"]=="storm_specific_excess"
        and predicted_saved_minutes > actor.expected_storm_left(0)*1.1):
        d["choice"]=WAIT
        d["reason"]+="; повторная неожиданность относится к ветреной погоде, можно переждать"
    d["context_assessment"]=assessment
    d["current_observed_cue"]=cue
    return d


def wait_and_walk(seed: int, variant: str, multiplier: int,
                  weather: DayWeather) -> dict:
    world=make_world(variant,multiplier)
    edge=world.edge("home","house_a")
    body=Body()
    room=Room(fuel=world.start_fuel,fire_lit=False,furniture=0)
    gear=Equipment(wetness=1)
    _advance(body,room,world,gear,WAIT_MINUTES,at_home=True)
    legs=[]
    for _ in range(2):
        if body.terminal:
            break
        absolute=world.dawn_min+body.elapsed_minutes
        travel=gear.travel_minutes(
            world.travel_minutes(edge,absolute,weather),
            wind=weather.wind(absolute),exposure=edge.exposure
        )
        cost={"stamina_demand":0.0,"extra_fatigue":0.0,
              "walked_h":0.0,"minimum_stamina":body.stamina,"wet_pace_delay_min":0.0}
        used=_advance(body,room,world,gear,travel,
                      at_home=False,exposure=edge.exposure,weather=weather,
                      travelling=True,walking_costs=cost)
        legs.append(used>=travel-1e-6 and not body.terminal)
    completed=len(legs)==2 and all(legs)
    return {
        "completed_return":completed,"elapsed_minutes":round(body.elapsed_minutes,5),
        "fuel_burned":round(room.burned_fuel_total,5),
        "stamina_after_route":round(body.stamina,5),
        "core_after_route":round(body.core_c,5),
        "wetness_after_preparation":1.0,
        "fuel_remaining":round(room.fuel,5),
        "room_fire_lit_after_route":room.fire_lit,
        "room_heat_offset_after_route_c":round(room.heated_offset_c,5),
        "room_fire_hours_total":round(room.fire_hours_total,5),
        "fatigue_after_route":round(body.fatigue,5),
        "terminal_at_minute":body.terminal_at_minute,
        "wait_minutes":WAIT_MINUTES,
    }


def run_case(seed: int,variant: str,profile: str,multiplier: int,
             pattern: str) -> dict:
    states,next_cue=PATTERNS[pattern]
    world=make_world(variant,multiplier)
    actors={
        "ema":Agent(profile,world),"last_error":Agent(profile,world),
        "contextual":Agent(profile,world),"causal_wait":Agent(profile,world),
    }
    # Both contextual actors get exactly the same observations and never
    # see researcher counterfactual dry outcomes.
    traces=[]
    for step,state in enumerate(states):
        # The *same* sequence has different witnessed storm onset/duration
        # across episodes. Repetition means evidence from multiple events,
        # not replaying an identical storm three times.
        episode_seed=seed+step*101
        weather=weather_for(world,state,episode_seed)
        # Controlled training; the underlying physics seed is paired
        # and constant across all learning strategies.
        physics=evaluate(episode_seed,variant,multiplier,
                         weather_override=weather)
        wet=physics["arms"]["wet_now"]
        history={"episode":step+1,"weather_condition_assigned":state,
                 "actor_action":"wet_now (researcher-assigned)",
                 "returned":wet["completed_return"],"observations":{}}
        for mode,actor in actors.items():
            forecast=actor_forecast(actor,state)
            history["observations"][mode]=observe_complete(
                actor,world,weather,wet,forecast,
                mode=("contextual" if mode in ("contextual","causal_wait") else mode)
            )
        traces.append(history)

    decisions={mode:choose_next(actor,world,cue=next_cue,mode=mode)
               for mode,actor in actors.items()}
    # The real heldout storm start/end is NOT passed to any policy.
    heldout_seed=seed+10000
    upcoming=weather_for(world,next_cue,heldout_seed,heldout=True)
    heldout=evaluate(heldout_seed,variant,multiplier,weather_override=upcoming)
    # Evaluate every alternative independently for AUDIT ONLY, after the
    # policies commit. Agents never read these outcomes or weather schedule.
    counterfactual={
        EXPLORE:heldout["arms"]["wet_now"],
        DRY:heldout["arms"]["prepared_all"],
        WAIT:wait_and_walk(heldout_seed,variant,multiplier,upcoming),
    }
    outcomes={}
    scored_alternatives={}
    for option,physical in counterfactual.items():
        work=None
        if physical["completed_return"]:
            b,r=restore_outcome(physical,world)
            work=followup_work(
                b,r,world,rest_if_tired=True,
                gear=Equipment(wetness=physical["wetness_after_preparation"])
            )
        scored_alternatives[option]={
            "return":physical["completed_return"],
            "work":bool(work and work["completed"]),
            "rest_min":work["rest_minutes"] if work else None,
            "fuel":physical["fuel_burned"],
            "time_min":physical["elapsed_minutes"],
        }
    for mode,dec in decisions.items():
        option=dec["choice"]
        outcomes[mode]={"choice":option,**scored_alternatives[option]}
    return {"case":{"seed":seed,"variant":variant,"profile":profile,
                    "distance":multiplier,"pattern":pattern},
            "history":traces,"next_current_observed_cue":next_cue,
            "decisions":decisions,"heldout":{"seed":heldout_seed,
                       "condition_at_departure":next_cue,"outcomes":outcomes,
                       "researcher_weather_schedule":{
                           "storm_start":upcoming.storm_start,
                           "storm_end":upcoming.storm_end}},
            "researcher_only_all_alternatives":scored_alternatives,
            }


def study(seeds: int=12)->dict:
    if not 1<=seeds<=40:
        raise ValueError("seeds must be 1..40")
    counts=Counter()
    checks=Counter()
    policy_counts=defaultdict(Counter)
    pattern_counts=defaultdict(Counter)
    examples={}
    switched=[]
    for pattern in PATTERNS:
        for variant in VARIANTS:
            for profile in PROFILES:
                for distance in DISTANCES:
                    for seed in range(1,seeds+1):
                        x=run_case(seed,variant,profile,distance,pattern)
                        counts["cases"]+=1
                        if seed==1 and profile=="local" and distance==24:
                            examples[f"{pattern}/{variant}"]=x
                        for episode in x["history"]:
                            if episode["returned"]:
                                counts["completed_training_episode"]+=1
                            else:
                                counts["incomplete_training_episode"]+=1
                            for mode,obs in episode["observations"].items():
                                if obs["accepted"]!=episode["returned"]:
                                    checks["fabricated_full_route"]+=1
                                if obs["accepted"] and any(
                                    abs(obs["signed_error"][name]-(
                                        obs["actual"][name]-obs["predicted"][name]))>1e-6
                                    for name in ("minutes","stamina","core")
                                ):
                                    checks["bad_signed_error"]+=1
                        decisions=x["decisions"]
                        outcomes=x["heldout"]["outcomes"]
                        alternatives=x["researcher_only_all_alternatives"]
                        wet=alternatives[EXPLORE]
                        waited=alternatives[WAIT]
                        if waited["return"] and not wet["return"]:
                            counts["wait_counterfactual_saved_return"]+=1
                        if wet["return"] and not waited["return"]:
                            counts["wait_counterfactual_lost_return"]+=1
                        if waited["work"] and not wet["work"]:
                            counts["wait_counterfactual_unlocked_work"]+=1
                        gate=decisions["causal_wait"]["wait_gate"]
                        for key,value in gate.items():
                            if key != "predicted_savings_minutes" and value:
                                counts["wait_gate:"+key]+=1
                        if any(len(d["alternatives"])!=3 for d in decisions.values()):
                            checks["missing_action"]+=1
                        if any(d["choice"] not in [
                            z["option"] for z in d["alternatives"] if z["available"]
                        ] for d in decisions.values()):
                            checks["unavailable_chosen"]+=1
                        if decisions["contextual"]["context_assessment"] != (
                                decisions["causal_wait"]["context_assessment"]):
                            checks["context_memory_diverged"]+=1
                        for mode in POLICIES:
                            d=decisions[mode]
                            c=policy_counts[mode]
                            c["trials"]+=1
                            if d["choice"]==DRY:c["dry"]+=1
                            if d["choice"]==WAIT:c["wait"]+=1
                            if outcomes[mode]["return"]:c["return"]+=1
                            if outcomes[mode]["work"]:c["work"]+=1
                            chosen=outcomes[mode]
                            # Pareto audit: actual task/return, scarce fuel and
                            # time. Never use this to alter a choice retroactively.
                            dominated=any(
                                (alt["return"]>=chosen["return"]
                                 and alt["work"]>=chosen["work"]
                                 and alt["fuel"]<=chosen["fuel"]+1e-6
                                 and alt["time_min"]<=chosen["time_min"]+1e-6
                                 and (alt["return"]>chosen["return"]
                                      or alt["work"]>chosen["work"]
                                      or alt["fuel"]<chosen["fuel"]-1e-6
                                      or alt["time_min"]<chosen["time_min"]-1e-6))
                                for option,alt in alternatives.items()
                                if option!=d["choice"] and any(
                                    z["option"]==option and z["available"]
                                    for z in d["alternatives"])
                            )
                            if dominated:
                                c["pareto_dominated"]+=1
                            if not chosen["return"] and any(
                                alt["return"] for option,alt in alternatives.items()
                                if option!=d["choice"] and any(
                                    z["option"]==option and z["available"]
                                    for z in d["alternatives"])):
                                c["return_possible_elsewhere"]+=1
                            c["fuel_milli"]+=round(outcomes[mode]["fuel"]*1000)
                            c["time_milli"]+=round(outcomes[mode]["time_min"]*1000)
                            p=pattern_counts[pattern]
                            if mode=="contextual" and d["choice"]==DRY:
                                p["contextual_dry"]+=1
                            if mode=="last_error" and d["choice"]==DRY:
                                p["naive_dry"]+=1
                            if mode=="causal_wait" and d["choice"]==WAIT:
                                p["informed_wait"]+=1
                        if decisions["contextual"]["choice"]!=decisions["last_error"]["choice"]:
                            before=outcomes["last_error"]
                            after=outcomes["contextual"]
                            counts["context_vs_last_choice_changes"]+=1
                            if after["choice"]==EXPLORE:
                                counts["context_deescalated_to_explore"]+=1
                            if after["choice"]==DRY:
                                counts["context_escalated_to_dry"]+=1
                            if after["return"] and not before["return"]:
                                counts["context_rescued_return"]+=1
                            if before["return"] and not after["return"]:
                                counts["context_lost_return"]+=1
                            if after["work"] and not before["work"]:
                                counts["context_unlocked_work"]+=1
                            if before["work"] and not after["work"]:
                                counts["context_lost_work"]+=1
                            counts["context_vs_naive_fuel_delta_milli"]+=round(
                                1000*(after["fuel"]-before["fuel"])
                            )
                            counts["context_vs_naive_time_delta_milli"]+=round(
                                1000*(after["time_min"]-before["time_min"])
                            )
                            pattern_counts[pattern]["context_vs_last_changes"]+=1
                            if len(switched)<24:
                                switched.append({
                                    "case":x["case"],
                                    "legacy":decisions["last_error"]["choice"],
                                    "contextual":decisions["contextual"]["choice"],
                                    "assessment":decisions["contextual"]["context_assessment"],
                                    "history":[ep["observations"]["contextual"]
                                               for ep in x["history"]],
                                })
                        if decisions["causal_wait"]["choice"]==WAIT:
                            counts["explicit_wait_chosen"]+=1
                            if x["next_current_observed_cue"]!="storm":
                                checks["wait_without_wind"]+=1
                        for mode in POLICIES:
                            y=outcomes[mode]
                            if y["fuel"] < -1e-5 or y["time_min"] < 0 or y["time_min"] > 1440:
                                checks["physical_bounds"]+=1
                        forecast_wind=weather_for(
                            make_world(variant,distance),
                            x["heldout"]["condition_at_departure"],
                            x["heldout"]["seed"],heldout=True
                        )
                        if ("storm" if forecast_wind.is_storm(
                                make_world(variant,distance).dawn_min
                             ) else "calm")!=x["heldout"]["condition_at_departure"]:
                            checks["cue_leaks_future"]+=1
    def mean_per_trial(c,key,scale=1.0):
        return round(c[key]/(max(1,c["trials"])*scale),4)
    return {
        "design":{"seeds":seeds,"patterns":PATTERNS,"variants":VARIANTS,
                  "profiles":PROFILES,"distances":DISTANCES,
                  "cases":counts["cases"],"policies":POLICIES,
                  "training_per_case":3,"human_participants":0,
                  "training_is_researcher_assigned":True,
                  "same_start_each_training":True,
                  "no_future_weather_in_decision":True,
                  "structurally_distinct_route_profile_pattern_combinations":
                      len(PATTERNS)*len(VARIANTS)*len(PROFILES)*len(DISTANCES),
                  "seed_variation":"storm start/duration varies, calm training remains deterministic"},
        "counts":dict(counts),
        "policy_outcomes":{
            name:{"trials":c["trials"],"dry":c["dry"],"wait":c["wait"],
                  "returns":c["return"],"work_completed":c["work"],
                  "pareto_dominated":c["pareto_dominated"],
                  "return_possible_elsewhere":c["return_possible_elsewhere"],
                  "mean_fuel":mean_per_trial(c,"fuel_milli",1000),
                  "mean_route_plus_preparation_h":mean_per_trial(
                      c,"time_milli",60000)}
            for name,c in policy_counts.items()
        },
        "by_pattern":{name:dict(c) for name,c in pattern_counts.items()},
        "changed_choices":switched,
        "examples":examples,
        "checks":{k:checks[k] for k in (
            "fabricated_full_route","bad_signed_error","missing_action",
            "unavailable_chosen","context_memory_diverged",
            "wait_without_wind","physical_bounds","cue_leaks_future"
        )},
        "limits":[
            "Training deliberately repeats the same edge with reset bodies; this is NOT 3 survived days.",
            "Wind at each leg start is an observable proxy; within-leg changes are not sampled in the current world stepper.",
            "The weather sequences are experimenter-controlled; storms last 60–120min with seed-varying start, not real random occurrence probabilities.",
            "The calm-only training cases are deterministic repetitions across seeds; case counts are NOT statistical independent player trials.",
            "Attribution is an evidence label, NOT certainty about what caused a loss. No dry counterfactual observed by agent.",
            "The contextual learner leaves storm losses out of its calm global core estimate; this is an explicit tested architectural assumption.",
            "Wait action is available only to an agent believing storms pass; its outcome uses actual time, fuel and room cooling.",
            "The heldout future storm end/start is hidden from the choice, even though current wind is visible.",
            "The posthoc Pareto diagnostic is researcher-only and cannot provide an actor with future knowledge.",
            "Wait was introduced as a real alternative; zero selected waits is an admissible negative result.",
            "No humans, no claim to fun or fully emergent autonomous general-purpose intent.",
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",type=int,default=12)
    p.add_argument("--json",required=True)
    a=p.parse_args()
    result=study(a.seeds)
    with open(a.json,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({"design":result["design"],"counts":result["counts"],
                      "by_pattern":result["by_pattern"],
                      "policy_outcomes":result["policy_outcomes"],
                      "checks":result["checks"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
