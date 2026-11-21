"""D1.6: prediction -> observation -> signed error -> a genuinely new choice.

Three matched policies on each completed wet training trip:
  prior: no feedback,
  ema: same original D1.5 travel/stamina/core belief updates,
  error: identical EMA + predeclared, asymmetric forecast-error caution.

Decision inputs are identical at second choice; no future weather, oracle or
dry counterfactual is disclosed to any agent. A separate unseen-weather
second trip is used ONLY by the researcher to assess the resulting decisions.
The second trip starts from a controlled equal body/room, NOT a full 2-day run.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict
from statistics import mean

from .agent import Agent, edge_key
from .body import Body
from .clothing_adaptation_study import (
    choose_clothing, make_world, restore_outcome
)
from .clothing_followthrough import followup_work
from .clothing_payoff_study import DISTANCE_MULTIPLIERS, VARIANTS, evaluate
from .coupled_microloop import DRY, EXPLORE, Equipment
from .evening import Room

ROUTE_ID = "home→house_a→home"
POLICIES = ("prior", "ema", "error")
HELDOUT_SEED_OFFSET = 10000
PROFILES = ("local", "novice")


def preview(agent: Agent, world, *, assume_storm: bool, use_error: bool = False):
    """Only information in the actor, with a controlled starting condition."""
    return choose_clothing(
        agent, Body(), Room(fuel=world.start_fuel),
        Equipment(wetness=1.0), assume_storm=assume_storm,
        consider_prediction_error=use_error,
    )


def evaluate_case(seed: int, variant: str, multiplier: int,
                  profile: str) -> dict:
    world = make_world(variant, multiplier)
    weather = world.roll_weather(random.Random(f"{seed}:weather:1"))
    # At time of the second decision, the last experienced weather is
    # a fallible assumption, held identical in every policy.
    assume_storm = weather.is_storm(world.dawn_min)
    actor = Agent(profile,world)
    prior = preview(actor,world,assume_storm=assume_storm)

    # PRE-commit a forecast before the training trip. Never overwrite it with
    # the newer EMA estimate before computing the signed error.
    key = edge_key("home","house_a")
    predicted_minutes = 2.0 * actor.beliefs.edge_minutes[key][
        "storm" if assume_storm else "calm"
    ]
    predicted_stamina_demand = (
        predicted_minutes / 60.0 * actor.beliefs.wet_walk_stamina_per_h_est
    )
    predicted_core_loss = (
        predicted_minutes / 60.0 * actor.beliefs.wet_walk_core_loss_per_h_est
    )
    prediction = {
        "travel_minutes": predicted_minutes,
        "stamina_demand": predicted_stamina_demand,
        "core_loss": predicted_core_loss,
        "weather_assumption": "storm" if assume_storm else "calm",
        "measured_before_training": True,
    }

    # Experimental training instruction, not evidence that this was the
    # actor's autonomous first choice.
    physical_training = evaluate(seed,variant,multiplier)
    actual = physical_training["arms"]["wet_now"]
    if not actual["completed_return"]:
        return {
            "case":{"seed":seed,"variant":variant,"multiplier":multiplier,
                    "profile":profile},
            "training_controlled_wet":True,
            "eligible":False,
            "reason":"training trip did not complete, no fictitious full-route observation",
            "prior_choice":prior.choice,
            "prediction":prediction,
            "observed_partial":{"minutes":actual["travel_minutes"],
                                "terminal":actual["terminal_at_minute"]},
            "decisions":None,"observed_error":None,"heldout":None,
        }

    seen = {
        "travel_minutes":actual["travel_minutes"],
        "stamina_demand":actual["walking_stamina_demand"],
        "core_loss":max(0.0,
                        actual["core_at_departure"]-actual["core_after_route"]),
        "first_leg_minutes":actual["legs"][0]["minutes_billed"],
    }
    signed_error = {
        "travel_minutes":seen["travel_minutes"]-prediction["travel_minutes"],
        "stamina_demand":seen["stamina_demand"]-prediction["stamina_demand"],
        "core_loss":seen["core_loss"]-prediction["core_loss"],
    }

    # Pure single-axis counterfactual: PRIOR has no learning; EMA and ERROR
    # receive precisely the same actual wet trip, including the same weather.
    ema_agent = copy.deepcopy(actor)
    previous_edge = ema_agent.observe_edge(
        "home","house_a",assume_storm,seen["first_leg_minutes"]
    )
    wet_memory = ema_agent.beliefs.observe_wet_walk(
        hours=seen["travel_minutes"]/60.0,
        stamina_demand=seen["stamina_demand"],
        core_before=actual["core_at_departure"],
        core_after=actual["core_after_route"],
    )
    error_agent = copy.deepcopy(ema_agent)
    error_memory = error_agent.beliefs.observe_trip_prediction(
        ROUTE_ID,
        predicted_minutes=prediction["travel_minutes"],
        actual_minutes=seen["travel_minutes"],
        predicted_stamina_demand=prediction["stamina_demand"],
        actual_stamina_demand=seen["stamina_demand"],
        predicted_core_loss=prediction["core_loss"],
        actual_core_loss=seen["core_loss"],
    )
    decision_objects = {
        "prior": prior,
        "ema": preview(ema_agent,world,assume_storm=assume_storm),
        "error": preview(error_agent,world,assume_storm=assume_storm,
                         use_error=True),
    }
    choices = {policy:d.choice for policy,d in decision_objects.items()}

    # Evaluate decisions under a held-out weather draw. Construct the
    # counterfactual outputs only AFTER all actors have chosen. Neither
    # weather nor successful dry actions are included in their beliefs.
    next_seed = seed + HELDOUT_SEED_OFFSET
    heldout_physics = evaluate(next_seed,variant,multiplier)
    results = {}
    for policy,choice in choices.items():
        physical = heldout_physics["arms"][
            "prepared_all" if choice == DRY else "wet_now"
        ]
        followup = None
        if physical["completed_return"]:
            body,room = restore_outcome(physical,world)
            work = followup_work(
                body,room,world,rest_if_tired=True,
                gear=Equipment(wetness=physical["wetness_after_preparation"]),
            )
            followup = {
                "ready_without_rest": work["rest_minutes"] == 0,
                "completed": work["completed"],
                "rest_minutes": work["rest_minutes"],
                "total_work_and_rest_minutes": work["total_minutes"],
                "end_stamina":body.stamina,
                "end_core":body.core_c,
            }
        results[policy] = {
            "choice":choice,
            "completed_return":physical["completed_return"],
            "trip_elapsed_minutes":physical["elapsed_minutes"],
            "fuel_burned":physical["fuel_burned"],
            "stamina_at_return":physical["stamina_after_route"],
            "core_at_return":physical["core_after_route"],
            "followup":followup,
        }

    # For changed decisions only, identify which *previously observed*
    # residual channels materially contributed to the provisional risk score.
    channel_tests = {}
    if choices["error"] != choices["ema"]:
        for channel in ("minutes","stamina","core"):
            ablation = copy.deepcopy(error_agent)
            ablation.beliefs.trip_prediction_errors[ROUTE_ID][channel] = 0.0
            channel_tests[channel] = preview(
                ablation,world,assume_storm=assume_storm,use_error=True
            ).choice
    return {
        "case":{"seed":seed,"variant":variant,"multiplier":multiplier,
                "profile":profile},
        "training_controlled_wet":True,"eligible":True,
        "prediction":prediction,
        "observation":seen,"signed_error":signed_error,
        "decision_chain":{
            "intention":prior.intention,
            "cues":prior.cues,
            "alternatives":prior.alternatives,
            "actor_initial_choice":prior.choice,
            "executed_action":EXPLORE,
            "executed_action_source":"researcher-controlled training, not actor",
            "prediction_before":prediction,
            "observed_after":seen,
            "signed_error":signed_error,
            "belief_update":error_memory,
            "next_intention":decision_objects["error"].choice,
            "next_reason":decision_objects["error"].reason,
            "control_ema_choice":decision_objects["ema"].choice,
        },
        "belief_update":{
            "edge_prior_minutes":previous_edge,
            "edge_after_minutes":ema_agent.beliefs.edge_minutes[key][
                "storm" if assume_storm else "calm"
            ],
            "wet_walk":wet_memory,"prediction_error":error_memory,
        },
        "decisions":{p:asdict(d) for p,d in decision_objects.items()},
        "choice_changed_due_ema":choices["ema"] != choices["prior"],
        "choice_changed_due_error":choices["error"] != choices["ema"],
        "strict_error_channel_ablation":channel_tests,
        "heldout":{"seed":next_seed,
                   "storm":heldout_physics["weather"],
                   "policies":results,
                   "researcher_only":{
                       arm:{
                           "completed_return":heldout_physics["arms"][arm][
                               "completed_return"
                           ],
                           "elapsed_minutes":heldout_physics["arms"][arm][
                               "elapsed_minutes"
                           ],
                       } for arm in ("wet_now","prepared_all")
                   }},
    }


def study(seeds: int = 30) -> dict:
    if not 1 <= seeds <= 100:
        raise ValueError("seeds 1..100")
    counts = Counter()
    checks = Counter()
    errors_by_group = defaultdict(list)
    policy_stats = defaultdict(Counter)
    transitions = []
    examples = {}
    for variant in VARIANTS:
        for profile in PROFILES:
            for multiplier in DISTANCE_MULTIPLIERS:
                for seed in range(1,seeds+1):
                    item = evaluate_case(seed,variant,multiplier,profile)
                    case = item["case"]
                    key=f"{variant}/{profile}/×{multiplier}"
                    counts["cases"]+=1
                    if seed==1:
                        examples[key]=item
                    if not item["eligible"]:
                        counts["incomplete_training"]+=1
                        if item["decisions"] is not None:
                            checks["learned_unfinished_trip"]+=1
                        continue
                    counts["observed_full_training"]+=1
                    original=item["prediction"]
                    observation=item["observation"]
                    signed=item["signed_error"]
                    if any(abs(signed[c] - (
                        observation[c]-original[c])) > 1e-6
                           for c in ("travel_minutes","stamina_demand","core_loss")):
                        checks["incorrect_signed_error"]+=1
                    if item["choice_changed_due_ema"]:
                        counts["ema_changed_choice"]+=1
                    if item["choice_changed_due_error"]:
                        counts["error_changed_choice"]+=1
                        counts[key+":error_changed_choice"]+=1
                        if len(transitions)<20:
                            transitions.append({
                                "case":case,
                                "prediction":original,
                                "observation":observation,
                                "error":signed,
                                "choices":{p:d["choice"] for p,d in item["decisions"].items()},
                                "ablation":item["strict_error_channel_ablation"],
                            })
                    errors_by_group[variant].append(signed)
                    decisions=item["decisions"]
                    chain=item["decision_chain"]
                    if (chain["observed_after"]!=observation or
                        chain["prediction_before"]!=original or
                        chain["next_intention"]!=decisions["error"]["choice"] or
                        not chain["belief_update"] or
                        chain["executed_action"]!=EXPLORE or
                        len(chain["alternatives"])!=2):
                        checks["broken_intent_chain"]+=1
                    if any(len(decisions[p]["alternatives"]) != 2 for p in POLICIES):
                        checks["lost_options"]+=1
                    if (decisions["ema"]["choice"] not in (
                        EXPLORE,DRY) or decisions["error"]["choice"] not in (EXPLORE,DRY)):
                        checks["invalid_choice"]+=1
                    heldout=item["heldout"]
                    if heldout["seed"]!=seed+HELDOUT_SEED_OFFSET:
                        checks["wrong_holdout_seed"]+=1
                    # Causal comparison of policies must share physical
                    # weather/results for each option, not independent RNG.
                    for p in POLICIES:
                        choice=decisions[p]["choice"]
                        output=heldout["policies"][p]
                        alt=heldout["researcher_only"][
                            "prepared_all" if choice==DRY else "wet_now"
                        ]
                        if output["choice"]!=choice or (
                            output["completed_return"]!=alt["completed_return"] or
                            output["trip_elapsed_minutes"]!=alt["elapsed_minutes"]
                        ):
                            checks["heldout_not_matched"]+=1
                        stats=policy_stats[p]
                        stats["trials"]+=1
                        if choice==DRY: stats["chose_dry"]+=1
                        if output["completed_return"]: stats["returns"]+=1
                        if output["followup"] and output["followup"]["completed"]:
                            stats["next_work_completed"]+=1
                        if output["followup"] and output["followup"]["rest_minutes"]>0:
                            stats["needed_rest"]+=1
                        stats["fuel_burned_total_milli"]+=round(output["fuel_burned"]*1000)
                        stats["elapsed_total_milli"]+=round(output["trip_elapsed_minutes"]*1000)
                    if item["choice_changed_due_error"]:
                        old=heldout["policies"]["ema"]
                        new=heldout["policies"]["error"]
                        if new["completed_return"] and not old["completed_return"]:
                            counts["error_switch_rescued_return"]+=1
                        if old["completed_return"] and not new["completed_return"]:
                            counts["error_switch_lost_return"]+=1
                        if new["trip_elapsed_minutes"] < old["trip_elapsed_minutes"]:
                            counts["error_switch_saved_clock"]+=1
                        if new["fuel_burned"] > old["fuel_burned"]:
                            counts["error_switch_spent_more_fuel"]+=1
    policy_summary={}
    for p in POLICIES:
        c=policy_stats[p]
        n=max(1,c["trials"])
        policy_summary[p]={
            "trials":c["trials"],"chose_dry":c["chose_dry"],
            "returns":c["returns"],
            "next_work_completed":c["next_work_completed"],
            "needed_rest":c["needed_rest"],
            "mean_fuel_burned":round(c["fuel_burned_total_milli"]/(1000*n),5),
            "mean_trip_elapsed_h":round(c["elapsed_total_milli"]/(60000*n),5),
        }
    def mean_abs(name,rows):
        return round(mean(abs(row[name]) for row in rows),5) if rows else None
    return {
        "design":{
            "seeds":seeds,"worlds":VARIANTS,"profiles":PROFILES,
            "distance_multipliers":DISTANCE_MULTIPLIERS,
            "cases":counts["cases"],
            "policy_arms":POLICIES,
            "heldout_seed_offset":HELDOUT_SEED_OFFSET,
            "human_participants":0,
            "training_policy":"researcher-controlled wet path, only complete returns teach",
            "controls":"prior vs legacy EMA vs EMA + signed prediction-error caution",
        },
        "counts":dict(counts),
        "policy_outcomes_heldout":policy_summary,
        "forecast_absolute_errors_by_world":{
            variant:{
                "n":len(errors_by_group[variant]),
                "travel_minute_mae":mean_abs("travel_minutes",errors_by_group[variant]),
                "stamina_mae":mean_abs("stamina_demand",errors_by_group[variant]),
                "core_loss_mae":mean_abs("core_loss",errors_by_group[variant]),
            } for variant in VARIANTS
        },
        "strict_transitions":transitions,
        "examples":examples,
        "checks":{name:checks[name] for name in (
            "learned_unfinished_trip","incorrect_signed_error",
            "lost_options","invalid_choice","wrong_holdout_seed",
            "heldout_not_matched","broken_intent_chain"
        )},
        "limits":[
            "The prior/EMA/error control choices share the same standardized starting Body/Room and weather assumption.",
            "The heldout second trip is a physical counterfactual with a fresh fixed initial state, NOT a two-day persistent playthrough.",
            "A training wet trip is assigned by study design; no first decision is claimed to be autonomous.",
            "No real dry outcome is disclosed to the actor; the researcher's heldout outcomes are never read by choice logic.",
            "All utility weights and error buffer coefficients are hypotheses, not tuned for success.",
            "Positive surprises are weighted as caution; negative signed errors are retained, not used as a forced incentive to take risks.",
            "Stamina's value is attached to one follow-up heavy-work task, not yet general locomotion.",
            "No humans, no game fun measurement, and no evidence of broad human intent.",
        ],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--seeds",type=int,default=30)
    parser.add_argument("--json",required=True)
    args=parser.parse_args()
    result=study(args.seeds)
    with open(args.json,"w",encoding="utf-8") as file:
        json.dump(result,file,ensure_ascii=False,indent=2)
    print(json.dumps({
        "design":result["design"],"counts":result["counts"],
        "policy_outcomes_heldout":result["policy_outcomes_heldout"],
        "forecast_absolute_errors_by_world":result["forecast_absolute_errors_by_world"],
        "checks":result["checks"],
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
