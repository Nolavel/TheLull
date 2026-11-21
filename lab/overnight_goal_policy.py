"""D1.9 — observable goal formation and tomorrow's actual action.

No world future, hidden loot, simulated next-night oracle or automatic
learning from assigned priorities. These are a FIXED, falsifiable policy
hypothesis, not general autonomous cognition.
"""
from __future__ import annotations

from .goal_priority_study import FUEL, PROTECT, WORK, GOALS
from .clothing_followthrough import WORK_START_STAMINA, WORK_MINUTES
from .body import Body
from .evening import Room
from .agent import Agent
from .world import World

RECOVER="остаться дома и восстановиться"
FORAGE="искать реальные запасы топлива"
FINISH="выполнить незавершённую работу"
ACTIONS=(RECOVER, FORAGE, FINISH)


def pressure(body: Body, room: Room, world: World, *,
             pending_work: bool, deadline_minute: float) -> dict:
    """Current measured priorities, not a consequence script for 'cold wake'.

    Thresholds are predeclared research hypotheses; the caller observes the
    SAME function before AND after the real night. No wake flag is an input.
    """
    cues={
        "core_c":round(body.core_c,5),
        "stamina":round(body.stamina,5),
        "fatigue":round(body.fatigue,5),
        "fuel":round(room.fuel,5),
        "pending_work":pending_work,
        "deadline_remaining_min":round(deadline_minute-body.elapsed_minutes,5),
        "terminal":body.terminal,
    }
    if body.terminal:
        return {"goal":None,"reason":"terminal body, no further intent", "cues":cues}
    if body.core_c<35.8 or body.stamina<45 or body.fatigue>75:
        return {"goal":PROTECT,
                "reason":"observed core/stamina/fatigue threatens next action",
                "cues":cues}
    if pending_work and deadline_minute-body.elapsed_minutes<=WORK_MINUTES+90:
        return {"goal":WORK,
                "reason":"visible outstanding task and deadline approaching",
                "cues":cues}
    if room.fuel < world.fuel_per_night:
        return {"goal":FUEL,
                "reason":"visible stove fuel below believed night demand",
                "cues":cues}
    if pending_work:
        return {"goal":WORK,
                "reason":"body able and a finite job is still unfinished",
                "cues":cues}
    return {"goal":PROTECT,
            "reason":"task complete; no immediate fuel deficit; conserve ability",
            "cues":cues}


def choose_morning(goal: str, body: Body, room: Room, agent: Agent,
                   world: World, *, pending_work: bool,
                   deadline_minute: float) -> dict:
    """Goal-specific ranking of the same feasible actions; no future oracle.

    This is deliberately small: one outstanding work item, finite fuel,
    shelter recovery or existing run_day exploration. Work and recovery stay
    physically separate from the canonical outdoor route controller.
    """
    if goal not in GOALS:
        raise ValueError("unknown goal")
    ranked_targets=agent.rank_targets()
    best=ranked_targets[0] if ranked_targets else None
    available={
        RECOVER:not body.terminal,
        FORAGE:bool(not body.terminal and best is not None),
        FINISH:bool(not body.terminal and pending_work and
                    body.stamina>=WORK_START_STAMINA and
                    deadline_minute-body.elapsed_minutes>=WORK_MINUTES),
    }
    candidates=[
        {
            "option":RECOVER,"available":available[RECOVER],
            "predicted_fuel_change":0.0,
            "predicted_stamina_change":min(100.0-body.stamina,20.0),
            "predicted_work_completed":False,
            "predicted_minutes":0,
            "basis":"остаться дома до вечера, тело продолжит физически меняться",
        },
        {
            "option":FORAGE,"available":available[FORAGE],
            "predicted_fuel_change":round(
                min(4.0,max(0.0,best["loot"])),3) if best else 0,
            "predicted_stamina_change":-18.0,
            "predicted_work_completed":False,
            "predicted_minutes":round(best["minutes"]*2+30,3) if best else None,
            "basis":"только известные оценки Agent, не истинные запасы",
        },
        {
            "option":FINISH,"available":available[FINISH],
            "predicted_fuel_change":0.0,
            "predicted_stamina_change":-20.0,
            "predicted_work_completed":True,
            "predicted_minutes":WORK_MINUTES,
            "basis":"60 мин, 20 stamina; остаётся одна реальная задача",
        },
    ]
    feasible=[x for x in candidates if x["available"]]
    if not feasible:
        return {"goal":goal,"choice":None,"alternatives":candidates,
                "reason":"body terminal or nothing executable","cues":[]}
    # Lexicographic preference: goals change the relative value of
    # completed job, finite fuel, and remaining strength.
    def key(a):
        option=a["option"]
        if goal==PROTECT:
            return (a["predicted_stamina_change"],
                    -max(0,-a["predicted_stamina_change"]),
                    -max(0,a["predicted_minutes"] or 0))
        if goal==FUEL:
            return (a["predicted_fuel_change"],
                    a["predicted_stamina_change"])
        return (int(a["predicted_work_completed"]),
                a["predicted_stamina_change"])
    winner=max(feasible,key=key)
    return {
        "goal":goal,"choice":winner["option"],
        "alternatives":candidates,
        "cues":[f"core={body.core_c:.2f}C; stamina={body.stamina:.2f}; fatigue={body.fatigue:.2f}",
                f"fuel={room.fuel:.3f}, pending_work={pending_work}",
                f"deadline_remaining={deadline_minute-body.elapsed_minutes:.1f}min",
                f"known_target={best['node'] if best else 'none'}"],
        "reason":f"ranked by goal={goal}, perceived consequences={key(winner)}",
    }
