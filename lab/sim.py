"""Day-by-day simulation of one virtual player in one world.

Reproducible from (world, variant, profile, seed). At every decision point the player writes a Decision:
what it intended, what it perceived, which alternatives it actually weighed, what it chose and why,
then the outcome and the belief update. The simulator truth (true loot, true weather) reaches the agent
only through what it experiences.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .agent import CARRY_CAPACITY, SEARCH_CHUNK_MIN, Agent
from .world import DayWeather, World

DEPART_MIN = 60
INDOOR_LOSS_PER_MIN = 0.3
LOOT_PER_CHUNK = 1.5  # what the player expects from one search chunk


@dataclass
class Decision:
    time: str
    point: str  # выход | цель | разведка | сигнал | буря
    intention: str
    cues: list[str]
    alternatives: list[dict]
    choice: str
    reason: str
    outcome: str = ""
    belief_update: str = ""


@dataclass
class DayRecord:
    day: int
    fuel_morning: int
    went_out: bool = False
    target: str | None = None
    predicted_return: float | None = None
    actual_return: float | None = None
    predicted_travel: float | None = None  # walking only, planned route there and back
    actual_travel: float = 0.0  # walking only, what was actually walked
    margin: float = 0.0
    signal_trust: float = 0.0
    carried: int = 0
    plan_changes: int = 0
    caught_in_storm: bool = False
    after_dark: bool = False
    crisis: bool = False
    min_warmth: float = 100.0
    storm_start: int | None = None  # weather truth, recorded for experiment checks
    storm_end: int | None = None
    cold_night: bool = False
    next_intention: str = ""
    decisions: list[Decision] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    @property
    def return_error(self) -> float | None:
        """Includes search and waiting, so it is not a navigation error. Kept for continuity."""
        if self.predicted_return is None or self.actual_return is None:
            return None
        return self.actual_return - self.predicted_return

    @property
    def travel_error(self) -> float | None:
        if self.predicted_travel is None:
            return None
        return self.actual_travel - self.predicted_travel


def clock(minute: float) -> str:
    total = 8 * 60 + int(minute)  # day starts at 08:00
    return f"{total // 60:02d}:{total % 60:02d}"


def _expected_chunks(agent: Agent, node: str) -> int:
    loot = min(agent.beliefs.loot.get(node, 0), CARRY_CAPACITY)
    return max(1, round(loot / LOOT_PER_CHUNK))


def _predicted_trip(agent: Agent, node: str) -> float:
    out_cost, _ = agent.path("home", node)
    return 2 * out_cost + _expected_chunks(agent, node) * SEARCH_CHUNK_MIN


def run_day(world: World, agent: Agent, weather: DayWeather, lrng: random.Random, day: int, fuel: int,
            signals_visible: bool = True) -> tuple[DayRecord, int]:
    rec = DayRecord(day=day, fuel_morning=fuel, margin=agent.margin, signal_trust=agent.beliefs.signal_trust(),
                    storm_start=weather.storm_start, storm_end=weather.storm_end)

    if fuel >= world.fuel_per_night + 1:
        rec.decisions.append(Decision(
            clock(0), "выход", "топлива на ночь уже достаточно",
            ["в доме есть топливо на ночь"],
            [{"option": "выйти за запасами", "basis": "не нужно сейчас"}],
            "остаться дома", "выход сейчас не даст выгоды"))
        rec.events.append("топлива хватает — остался дома")
        return _night(world, rec, fuel)

    ranking = agent.rank_targets()
    if ranking:
        target = ranking[0]["node"]
        target_dec = Decision(
            clock(DEPART_MIN), "цель", "принести запасы, пока светло",
            ["известные запасы: " + ", ".join(f"{r['node']}≈{r['loot']:.0f}" for r in ranking)],
            [{"option": r["node"], "predicted_min": round(_predicted_trip(agent, r["node"])),
              "score": round(r["score"], 3)} for r in ranking],
            target, "больше ожидаемого груза за меньшее время")
    else:
        unexplored = [n for n in world.nodes
                      if agent._knows_node(n) and n not in agent.visited and n != "home"
                      and agent.path("home", n)[1]]
        if not unexplored:
            rec.decisions.append(Decision(
                clock(DEPART_MIN), "цель", "нет известной цели",
                ["известных запасов нет", "неизученных мест нет"], [], "остаться дома", "некуда идти"))
            rec.events.append("не знает, куда идти — остался дома")
            return _night(world, rec, fuel)
        target = min(unexplored, key=lambda n: agent.path("home", n)[0])
        target_dec = Decision(
            clock(DEPART_MIN), "разведка", "узнать, что есть рядом",
            ["известных запасов нет"],
            [{"option": n, "predicted_min": round(agent.path("home", n)[0] * 2)} for n in unexplored],
            target, "ближайший неизученный путь")
    rec.decisions.append(target_dec)

    now = float(DEPART_MIN)
    out_cost, _ = agent.path("home", target)
    rec.went_out, rec.target = True, target
    rec.predicted_travel = 2 * out_cost
    rec.predicted_return = now + _predicted_trip(agent, target)
    rec.events.append(f"{clock(now)} вышел к {target}, рассчитывает вернуться к {clock(rec.predicted_return)}")

    node, goal, warmth, carried = "home", target, 100.0, 0
    noticed = False
    returning = False
    sig = {"dec": None}
    storm_dec = None

    def check_signal() -> None:
        nonlocal noticed, returning, goal
        if not signals_visible or noticed or weather.signal_at is None or now < weather.signal_at:
            return
        noticed = True
        trust = agent.beliefs.signal_trust()
        turn = trust >= 0.5 and not returning
        d = Decision(
            clock(now), "сигнал", "вернуться до непогоды или продолжить",
            ["признаки ухудшения погоды (не всегда верные)"],
            [{"option": "вернуться домой", "basis": f"доверие к приметам {trust:.0%}"},
             {"option": "продолжить", "basis": "дом пока не близко"}],
            "вернуться" if turn else "продолжить",
            "поверил приметам — поворачивает" if turn else f"доверие {trust:.0%} — не поверил")
        rec.decisions.append(d)
        sig["dec"] = d
        if turn:
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
                got = min(world.loot.get(node, 0), lrng.randint(1, 2), CARRY_CAPACITY - carried)
                world.loot[node] = world.loot.get(node, 0) - got
                carried += got
                update = agent.learn_loot(node, got)
                target_dec.belief_update += update + "; "
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

        if storm_now and edge.exposure > 0.5 and node != "home" and storm_dec is None:
            knows = agent.beliefs.knows_storms_pass
            storm_dec = Decision(
                clock(now), "буря", "дойти до следующего места",
                [f"ветер {weather.wind(now):.1f}, открытая улица {node}→{nxt}"],
                [{"option": f"переждать в {node}",
                  "basis": "знает, что буря проходит" if knows else "не знает, как долго она продлится"},
                 {"option": "идти дальше", "basis": "маршрут короче"}],
                "переждать" if knows else "идти",
                "знает, что буря проходит — лучше переждать в укрытии" if knows
                else "не знает, что буря скоро кончится — идёт дальше")
            rec.decisions.append(storm_dec)
            if knows:
                wait = weather.storm_end - now
                now = float(weather.storm_end)
                warmth -= INDOOR_LOSS_PER_MIN * wait
                rec.plan_changes += 1
                storm_dec.outcome = f"ждал {wait:.0f} мин, буря прошла"
                rec.events.append(f"пережидает бурю в {node} {wait:.0f} мин, вместо открытой улицы")
                continue

        minutes = world.travel_minutes(edge, now, weather)
        if storm_now:
            rec.caught_in_storm = True
            if storm_dec is not None and not storm_dec.outcome:
                storm_dec.outcome = f"шёл открытой улицей {minutes:.0f} мин"
        predicted = agent.observe_edge(node, nxt, storm_now, minutes)
        rec.actual_travel += minutes
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
    if noticed and sig["dec"] is not None:
        before = agent.beliefs.signal_trust()
        agent.observe_signal(weather.storm_start is not None)
        sig["dec"].outcome = "буря пришла" if weather.storm_start is not None else "буря не пришла"
        sig["dec"].belief_update = f"доверие к приметам {before:.0%}→{agent.beliefs.signal_trust():.0%}"

    rec.actual_return, rec.carried = now, carried
    rec.after_dark = now > world.day_length
    fuel += carried
    target_dec.outcome = (f"дома в {clock(now)} с {carried}, ожидал к {clock(rec.predicted_return)}"
                          + (", уже темно" if rec.after_dark else ""))
    rec.events.append(f"{clock(now)} дома, принёс {carried}" + (" — уже стемнело" if rec.after_dark else ""))

    scare = rec.after_dark or rec.crisis or rec.caught_in_storm or rec.min_warmth < 25
    note = agent.update_margin(scare=scare, on_time=not scare)
    if note:
        rec.events.append(note)
        target_dec.belief_update += note
    return _night(world, rec, fuel)


def _night(world: World, rec: DayRecord, fuel: int) -> tuple[DayRecord, int]:
    fuel -= world.fuel_per_night
    if fuel < 0:
        rec.cold_night = True
        rec.events.append("ночь без огня")
        fuel = 0
    rec.next_intention = "выйти за топливом" if fuel <= world.fuel_per_night else "выхода не требуется"
    return rec, fuel


def run(world_name: str, variant: str, profile: str, days: int, seed: int,
        signals_visible: bool = True) -> list[DayRecord]:
    """Weather depends only on (seed, day), never on what the player did: conditions stay paired."""
    world = World.load(world_name, variant)
    agent = Agent(profile, world)
    loot_rng = random.Random(f"{seed}:loot")
    fuel = world.start_fuel
    records = []
    for d in range(1, days + 1):
        weather = world.roll_weather(random.Random(f"{seed}:weather:{d}"))
        rec, fuel = run_day(world, agent, weather, loot_rng, d, fuel, signals_visible)
        records.append(rec)
    return records
