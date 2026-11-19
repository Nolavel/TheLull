"""Day-by-day simulation of one virtual player in one world.

Same seed, world and profile give the same story: results are comparable across commits.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .agent import CARRY_CAPACITY, SEARCH_CHUNK_MIN, Agent
from .world import World

DEPART_MIN = 60
INDOOR_LOSS_PER_MIN = 0.3


@dataclass
class DayRecord:
    day: int
    fuel_morning: int
    went_out: bool = False
    target: str | None = None
    predicted_return: float | None = None
    actual_return: float | None = None
    margin: float = 0.0
    signal_trust: float = 0.0
    carried: int = 0
    plan_changes: int = 0
    caught_in_storm: bool = False
    after_dark: bool = False
    crisis: bool = False
    min_warmth: float = 100.0
    cold_night: bool = False
    events: list[str] = field(default_factory=list)

    @property
    def return_error(self) -> float | None:
        if self.predicted_return is None or self.actual_return is None:
            return None
        return self.actual_return - self.predicted_return


def clock(minute: float) -> str:
    total = 8 * 60 + int(minute)  # day starts at 08:00
    return f"{total // 60:02d}:{total % 60:02d}"


def run_day(world: World, agent: Agent, rng: random.Random, day: int, fuel: int) -> tuple[DayRecord, int]:
    weather = world.roll_weather(rng)
    rec = DayRecord(day=day, fuel_morning=fuel, margin=agent.margin, signal_trust=agent.beliefs.signal_trust())

    if fuel >= world.fuel_per_night + 1:
        rec.events.append("топлива хватает — остался дома")
        return _night(world, rec, fuel)

    target = agent.choose_target()
    if target is None:
        unexplored = [n for n in world.nodes if agent._knows_node(n) and n not in agent.visited and n != "home"]
        if unexplored:
            target = min(unexplored, key=lambda n: agent.path("home", n)[0])
            rec.events.append(f"известных запасов нет — идёт разведать {target}")
        else:
            rec.events.append("не знает, куда идти — остался дома")
            return _night(world, rec, fuel)

    now = float(DEPART_MIN)
    out_cost, _ = agent.path("home", target)
    rec.went_out, rec.target = True, target
    # The plan: walk there, search until the bag is full (expects ~1.5 per chunk), walk back.
    expected_loot = min(agent.beliefs.loot.get(target, 0), CARRY_CAPACITY)
    chunks = max(1, round(expected_loot / 1.5)) if world.nodes[target]["kind"] == "building" else 0
    rec.predicted_return = now + 2 * out_cost + chunks * SEARCH_CHUNK_MIN
    rec.events.append(f"{clock(now)} вышел к {target}, рассчитывает вернуться к {clock(rec.predicted_return)}")

    node, goal, warmth, carried = "home", target, 100.0, 0
    noticed = False
    returning = False

    def check_signal() -> None:
        nonlocal noticed, returning, goal
        if noticed or weather.signal_at is None or now < weather.signal_at:
            return
        noticed = True
        trust = agent.beliefs.signal_trust()
        if trust >= 0.5 and not returning:
            returning, goal = True, "home"
            rec.plan_changes += 1
            rec.events.append(f"{clock(now)} заметил признаки непогоды и поверил им ({trust:.0%}) — поворачивает домой")
        else:
            rec.events.append(f"{clock(now)} заметил признаки непогоды, но не придал значения ({trust:.0%})")

    while True:
        if node == goal:
            if goal == "home":
                break
            agent.visited.add(node)
            while not returning:
                cost_home = agent.path(node, "home", storm=weather.is_storm(now))[0]
                left = agent.beliefs.loot.get(node, 0)
                if carried >= CARRY_CAPACITY or left <= 0:
                    break
                if now + SEARCH_CHUNK_MIN + cost_home + agent.margin > world.day_length:
                    rec.events.append(f"{clock(now)} пора возвращаться: до темноты впритык (запас {agent.margin:.0f} мин)")
                    break
                now += SEARCH_CHUNK_MIN
                warmth -= INDOOR_LOSS_PER_MIN * SEARCH_CHUNK_MIN
                got = min(world.loot.get(node, 0), rng.randint(1, 2), CARRY_CAPACITY - carried)
                world.loot[node] = world.loot.get(node, 0) - got
                carried += got
                agent.beliefs.loot[node] = world.loot[node]
                if got == 0:
                    rec.events.append(f"{clock(now)} {node} пуст — ожидание не оправдалось")
                check_signal()
            returning, goal = True, "home"
            continue

        storm_now = weather.is_storm(now)
        _, route = agent.path(node, goal, storm=storm_now)
        if len(route) < 2:
            rec.crisis = True
            rec.events.append(f"{clock(now)} не знает дороги к {goal}")
            break
        nxt = route[1]
        edge = world.edge(node, nxt)

        if storm_now and edge.exposure > 0.5 and node != "home" and agent.beliefs.knows_storms_pass:
            wait = weather.storm_end - now
            now = float(weather.storm_end)
            warmth -= INDOOR_LOSS_PER_MIN * wait
            rec.plan_changes += 1
            rec.events.append(f"пережидает бурю в {node} {wait:.0f} мин, вместо открытой улицы")
            continue

        minutes = world.travel_minutes(edge, now, weather)
        if storm_now:
            rec.caught_in_storm = True
        predicted = agent.observe_edge(node, nxt, storm_now, minutes)
        if minutes > predicted * 1.5:
            what = " в буре" if storm_now else (" в темноте" if now >= world.day_length else "")
            rec.events.append(f"{clock(now)} {node}→{nxt}{what}: {minutes:.0f} мин вместо ожидаемых {predicted:.0f}")
        warmth -= world.warmth_loss_per_min(edge.exposure, now, weather) * minutes
        now += minutes
        rec.min_warmth = min(rec.min_warmth, warmth)
        node = nxt
        for found in agent.discover(node, world):
            rec.events.append(f"{clock(now)} в {node} увидел путь к {found}")
        check_signal()
        if warmth <= 0:
            rec.crisis = True
            rec.events.append(f"{clock(now)} замёрз в пути — с трудом добрался домой без добычи")
            carried, now = 0, now + 30
            break

    if rec.caught_in_storm:
        agent.beliefs.knows_storms_pass = True
    if noticed:
        agent.observe_signal(weather.storm_start is not None)

    rec.actual_return, rec.carried = now, carried
    rec.after_dark = now > world.day_length
    fuel += carried
    rec.events.append(f"{clock(now)} дома, принёс {carried}" + (" — уже стемнело" if rec.after_dark else ""))

    scare = rec.after_dark or rec.crisis or rec.caught_in_storm or rec.min_warmth < 25
    note = agent.update_margin(scare=scare, on_time=not scare)
    if note:
        rec.events.append(note)
    return _night(world, rec, fuel)


def _night(world: World, rec: DayRecord, fuel: int) -> tuple[DayRecord, int]:
    fuel -= world.fuel_per_night
    if fuel < 0:
        rec.cold_night = True
        rec.events.append("ночь без огня")
        fuel = 0
    return rec, fuel


def run(world_name: str, variant: str, profile: str, days: int, seed: int) -> list[DayRecord]:
    rng = random.Random(seed)
    world = World.load(world_name, variant)
    agent = Agent(profile, world)
    fuel = world.start_fuel
    records = []
    for d in range(1, days + 1):
        rec, fuel = run_day(world, agent, rng, d, fuel)
        records.append(rec)
    return records
