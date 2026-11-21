"""A stamina-dependent SECOND action after a trip, sharing the same Body clock.

No artificial stamina death or forced drying. A tired person may defer a
physically demanding shelter task or recover first; rest costs real time.
This is a prototype action, not a gameplay movement controller.
"""
from __future__ import annotations

from .body import Body
from .coupled_microloop import Equipment, _advance
from .evening import Room
from .world import World

WORK_START_STAMINA = 60.0   # tentative task readiness, not universal mobility gate
WORK_CONSUMPTION = 20.0
WORK_MINUTES = 60
REST_QUANTUM_MINUTES = 15
REST_LIMIT_MINUTES = 180


def followup_work(body: Body, room: Room, world: World, *,
                  rest_if_tired: bool = True,
                  gear: Equipment | None = None) -> dict:
    """Process one difficult home task or defer it without fake progress.

    The caller's body/room/elapsed_minutes continue from the actual trip.
    Nothing is generated; in particular, no fuel or loot is awarded.
    """
    before = body.elapsed_minutes
    before_stamina = body.stamina
    rest_minutes = 0.0
    gear = gear if gear is not None else Equipment()
    # Never turn an observed wet garment dry by entering the shelter.
    if body.terminal:
        return {"choice": "unavailable_terminal", "completed": False,
                "rest_minutes": 0.0, "work_minutes": 0.0,
                "total_minutes": 0.0, "stamina_before": before_stamina,
                "stamina_after": body.stamina, "reason": "critical state"}

    if body.stamina < WORK_START_STAMINA and not rest_if_tired:
        return {"choice": "defer", "completed": False,
                "rest_minutes": 0.0, "work_minutes": 0.0,
                "total_minutes": 0.0, "stamina_before": before_stamina,
                "stamina_after": body.stamina, "reason": "not enough stamina for next task"}

    while (body.stamina < WORK_START_STAMINA - 1e-9
           and rest_minutes < REST_LIMIT_MINUTES and not body.terminal):
        billed = _advance(body, room, world, gear, REST_QUANTUM_MINUTES,
                          at_home=True)
        rest_minutes += billed
        if billed < REST_QUANTUM_MINUTES - 1e-7:
            break

    if body.terminal or body.stamina < WORK_START_STAMINA - 1e-9:
        return {"choice": "recover_but_unavailable", "completed": False,
                "rest_minutes": round(rest_minutes, 6), "work_minutes": 0.0,
                "total_minutes": round(body.elapsed_minutes - before, 6),
                "stamina_before": before_stamina, "stamina_after": body.stamina,
                "reason": "recovery time or thermal condition insufficient"}

    # Work occupies an actual hour in the same physical shelter.
    # _advance's generic awake controller restores idle breath. A strenuous
    # ACTION cannot silently gain that idle stamina while working; apply its
    # explicit cost to the pre-work value, proportionally even if terminal
    # interrupts the hour. Keep the same thermal / time controller.
    stamina_before_work = body.stamina
    fatigue_before_work = body.fatigue
    work = _advance(body, room, world, gear, WORK_MINUTES, at_home=True)
    complete = work >= WORK_MINUTES - 1e-6 and not body.terminal
    proportion = min(1.0, work / WORK_MINUTES)
    body.stamina = max(0.0, stamina_before_work - WORK_CONSUMPTION * proportion)
    body.fatigue = min(100.0, max(body.fatigue,
                                  fatigue_before_work + 7.0 * (work / 60.0)))
    return {"choice": "rest_then_work" if rest_minutes else "work_now",
            "completed": complete,
            "rest_minutes": round(rest_minutes, 6),
            "work_minutes": round(work, 6),
            "total_minutes": round(body.elapsed_minutes - before, 6),
            "stamina_before": round(before_stamina, 6),
            "stamina_after": round(body.stamina, 6),
            "reason": ("paid stamina for real task" if complete
                       else "task cut short by terminal condition")}
