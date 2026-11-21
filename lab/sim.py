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
from .body import (DEATH_C, HYPOTHERMIC_C, TRAVEL_FATIGUE_PER_H, Body, step_core, step_fatigue)
from .world import DayWeather, World

DEPART_AFTER_DAWN_MIN = 60  # the player does not leave at first light
# Deprecated, kept only so lab/loop_bridge.py keeps importing while Codex migrates. Minutes are now
# absolute inside the 24-hour day, so departure is world.dawn_min + DEPART_AFTER_DAWN_MIN, not this value.
# The day now bills fatigue and cold to the shared Body, so the bridge's own fatigue heuristic can go.
DEPART_MIN = DEPART_AFTER_DAWN_MIN
INDOOR_EXPOSURE = 0.15  # an unheated building still blocks most of the wind
WAIT_CHUNK_MIN = 15  # the player re-decides this often while waiting out a storm
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
    search_minutes: float = 0.0
    recheck_searches: int = 0  # spent a 30-min chunk when expected loot was zero
    empty_searches: int = 0  # actual searched observations, not an oracle
    plan_changes: int = 0
    caught_in_storm: bool = False
    after_dark: bool = False
    crisis: bool = False
    min_core_c: float = 37.0  # degrees, the same scale the night uses
    waited_out_storm: bool = False
    storm_observed: bool = False  # the player saw for itself whether a storm came
    storm_start: int | None = None  # weather truth, recorded for experiment checks
    storm_end: int | None = None
    cold_night: bool = False
    next_intention: str = ""
    run_end_reason: str | None = None  # set on the last day when the run cannot go on
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
    """Absolute minutes inside the 24-hour day."""
    total = int(minute) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _expected_chunks(agent: Agent, node: str) -> int:
    loot = min(agent.beliefs.loot.get(node, 0), CARRY_CAPACITY)
    return max(1, round(loot / LOOT_PER_CHUNK))


def _predicted_trip(agent: Agent, node: str) -> float:
    out_cost, _ = agent.path("home", node)
    return 2 * out_cost + _expected_chunks(agent, node) * SEARCH_CHUNK_MIN


def run_day(world: World, agent: Agent, weather: DayWeather, lrng: random.Random, day: int, fuel: int,
            signals_visible: bool = True, body: Body | None = None,
            *, charge_legacy_night: bool = True) -> tuple[DayRecord, int]:
    body = body if body is not None else Body()
    rec = DayRecord(day=day, fuel_morning=fuel, margin=agent.margin, signal_trust=agent.beliefs.signal_trust(),
                    storm_start=weather.storm_start, storm_end=weather.storm_end, min_core_c=body.core_c)
    # Packing pays for a shorter morning setup; the clock stays absolute.
    depart = world.dawn_min + max(0, DEPART_AFTER_DAWN_MIN - (15 if body.packed else 0))

    if fuel >= world.fuel_per_night + 1:
        rec.decisions.append(Decision(
            clock(0), "выход", "топлива на ночь уже достаточно",
            ["в доме есть топливо на ночь"],
            [{"option": "выйти за запасами", "basis": "не нужно сейчас"}],
            "остаться дома", "выход сейчас не даст выгоды"))
        rec.events.append("топлива хватает — остался дома")
        return _finish_day(world, rec, fuel, charge_legacy_night)

    ranking = agent.rank_targets()
    if ranking:
        target = ranking[0]["node"]
        target_dec = Decision(
            clock(depart), "цель", "принести запасы, пока светло",
            ["оценки запасов: " + ", ".join(
                f"{r['node']}≈{r['loot']:.0f}" + (" (не проверено до конца)" if r["recheck"] else "")
                for r in ranking)],
            [{"option": r["node"], "predicted_min": round(_predicted_trip(agent, r["node"])),
              "score": round(r["score"], 3), "recheck": r["recheck"]} for r in ranking],
            target, ("повторная проверка: прежняя оценка ноль, но пустота не наблюдалась"
                     if ranking[0]["recheck"] else "больше ожидаемого груза за меньшее время"))
    else:
        unexplored = [n for n in world.nodes
                      if agent._knows_node(n) and n not in agent.visited and n != "home"
                      and agent.path("home", n)[1]]
        if not unexplored:
            rec.decisions.append(Decision(
                clock(depart), "цель", "нет известной цели",
                ["известных запасов нет", "неизученных мест нет"], [], "остаться дома", "некуда идти"))
            rec.events.append("не знает, куда идти — остался дома")
            return _finish_day(world, rec, fuel, charge_legacy_night)
        target = min(unexplored, key=lambda n: agent.path("home", n)[0])
        target_dec = Decision(
            clock(depart), "разведка", "узнать, что есть рядом",
            ["известных запасов нет"],
            [{"option": n, "predicted_min": round(agent.path("home", n)[0] * 2)} for n in unexplored],
            target, "ближайший неизученный путь")
    rec.decisions.append(target_dec)

    now = float(depart)
    out_cost, _ = agent.path("home", target)
    rec.went_out, rec.target = True, target
    rec.predicted_travel = 2 * out_cost
    rec.predicted_return = now + _predicted_trip(agent, target)
    rec.events.append(f"{clock(now)} вышел к {target}, рассчитывает вернуться к {clock(rec.predicted_return)}")

    node, goal, carried = "home", target, 0  # warmth lives in body.core_c now, carried across days
    noticed = False
    returning = False
    sig = {"dec": None}
    storm_met: dict[str, float | None] = {"at": None}
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
            rechecked_this_visit = False
            while not returning:
                cost_home = agent.path(node, "home", storm=weather.is_storm(now))[0]
                left = agent.beliefs.loot.get(node, 0)
                if carried >= CARRY_CAPACITY:
                    break
                # Zero *prediction* is not proof. At most one uncertain recheck
                # per visit; every attempt incurs travel and a real search chunk.
                if left <= 0 and (not agent.can_recheck(node) or rechecked_this_visit):
                    break
                if now + SEARCH_CHUNK_MIN + cost_home + agent.margin > world.day_length:
                    rec.events.append(f"{clock(now)} пора возвращаться: до темноты впритык (запас {agent.margin:.0f} мин)")
                    break
                if left <= 0:
                    rechecked_this_visit = True
                    rec.recheck_searches += 1
                    rec.events.append(f"{clock(now)} перепроверяет {node}: оценка ноль, но пустота не подтверждена")
                now += SEARCH_CHUNK_MIN
                rec.search_minutes += SEARCH_CHUNK_MIN
                felt = world.felt_outdoors_c(INDOOR_EXPOSURE, now, weather)
                step_core(body, felt, SEARCH_CHUNK_MIN / 60.0)
                step_fatigue(body, SEARCH_CHUNK_MIN / 60.0, asleep=False, per_hour=TRAVEL_FATIGUE_PER_H)
                rec.min_core_c = min(rec.min_core_c, body.core_c)
                got = min(world.loot.get(node, 0), lrng.randint(1, 2), CARRY_CAPACITY - carried)
                world.loot[node] = world.loot.get(node, 0) - got
                carried += got
                update = agent.learn_loot(node, got)
                target_dec.belief_update += update + "; "
                if got == 0:
                    rec.empty_searches += 1
                    rec.events.append(f"{clock(now)} в {node} поиск ничего не дал — отметил пустым")
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
            est = agent.beliefs.storm_duration_est
            knows = agent.beliefs.knows_storms_pass
            storm_dec = Decision(
                clock(now), "буря", "дойти до следующего места",
                [f"ветер {weather.wind(now):.1f}, открытая улица {node}→{nxt}",
                 f"укрытие здесь: {world.nodes[node]['kind']}"],
                [{"option": f"переждать в {node}",
                  "basis": (f"думает, что бури длятся около {est:.0f} мин" if est is not None
                            else ("знает, что бури проходят, но не знает сколько длятся" if knows
                                  else "не знает, сколько длится буря"))},
                 {"option": "идти дальше", "basis": "маршрут короче, но улица открыта"}],
                "переждать" if knows else "идти",
                "рассчитывает, что буря скоро кончится" if knows
                else "не знает, когда кончится буря — идёт дальше")
            rec.decisions.append(storm_dec)
            if knows:
                # The player does not know storm_end: it waits in chunks and keeps re-deciding.
                waited, gave_up = 0.0, False
                while weather.is_storm(now):
                    home_cost = agent.path(node, "home", storm=True)[0]
                    if agent.expected_storm_left(waited) <= 0:
                        gave_up = True
                        rec.events.append(f"{clock(now)} буря длится дольше, чем он ожидал — выходит в неё")
                        break
                    if body.is_hypothermic() or now + WAIT_CHUNK_MIN + home_cost + agent.margin > world.day_length:
                        gave_up = True
                        rec.events.append(f"{clock(now)} ждать больше нельзя: "
                                          + ("мёрзнет" if body.is_hypothermic() else "темнеет") + " — выходит в бурю")
                        break
                    now += WAIT_CHUNK_MIN
                    waited += WAIT_CHUNK_MIN
                    felt = world.felt_outdoors_c(INDOOR_EXPOSURE if world.nodes[node]["kind"] != "waypoint"
                                                 else 0.5, now, weather)
                    step_core(body, felt, WAIT_CHUNK_MIN / 60.0)
                    step_fatigue(body, WAIT_CHUNK_MIN / 60.0, asleep=False)
                    rec.min_core_c = min(rec.min_core_c, body.core_c)
                rec.plan_changes += 1
                rec.waited_out_storm = not gave_up
                storm_dec.outcome = (f"ждал {waited:.0f} мин, буря прошла" if not gave_up
                                     else f"ждал {waited:.0f} мин и всё равно пошёл в бурю")
                rec.events.append(f"{clock(now)} переждал в {node} {waited:.0f} мин"
                                  if not gave_up else f"{clock(now)} выходит из {node} в бурю")
                if not gave_up:
                    storm_dec.belief_update = agent.observe_storm_duration(waited)
                    rec.storm_observed = True
                    continue

        minutes = world.travel_minutes(edge, now, weather)
        if storm_now:
            if not rec.caught_in_storm:
                storm_met["at"] = now  # first contact: all it can judge the length from
            rec.caught_in_storm = True
            if storm_dec is not None and not storm_dec.outcome:
                storm_dec.outcome = f"шёл открытой улицей {minutes:.0f} мин"
        predicted = agent.observe_edge(node, nxt, storm_now, minutes)
        rec.actual_travel += minutes
        if minutes > predicted * 1.5:
            what = " в буре" if storm_now else (" в темноте" if not world.is_daylight(now) else "")
            rec.events.append(f"{clock(now)} {node}→{nxt}{what}: {minutes:.0f} мин вместо ожидаемых {predicted:.0f}")
        step_core(body, world.felt_outdoors_c(edge.exposure, now, weather), minutes / 60.0)
        step_fatigue(body, minutes / 60.0, asleep=False, per_hour=TRAVEL_FATIGUE_PER_H)
        now += minutes
        rec.min_core_c = min(rec.min_core_c, body.core_c)
        node = nxt
        for found in agent.discover(node, world):
            rec.events.append(f"{clock(now)} в {node} увидел путь к {found}")
        check_signal()
        if body.core_c <= HYPOTHERMIC_C - 2.0:
            rec.crisis = True
            rec.events.append(f"{clock(now)} замерзает в пути ({body.core_c:.1f}°) — бросает добычу и идёт домой")
            carried, now = 0, now + 30
            break

    # What the player may learn about the sign: only what it could witness.
    # Daylight at home counts (a storm is visible and audible from a window); after dark, asleep, it does not.
    if weather.storm_start is not None and weather.storm_start < world.day_length:
        rec.storm_observed = True
    if rec.caught_in_storm:
        rec.storm_observed = True
        # Walking through a storm teaches that they end, and roughly how long — but only the part it lived
        # through, measured from first contact. An early estimate is honestly too short.
        if weather.storm_end is not None and weather.storm_end < world.day_length and storm_met["at"] is not None:
            rec.events.append(agent.observe_storm_duration(weather.storm_end - storm_met["at"]))
        else:
            agent.beliefs.knows_storms_pass = True
    if noticed and sig["dec"] is not None:
        if rec.storm_observed or weather.storm_start is None:
            before = agent.beliefs.signal_trust()
            agent.observe_signal(weather.storm_start is not None and rec.storm_observed)
            sig["dec"].outcome = "буря пришла" if rec.storm_observed else "буря не пришла"
            sig["dec"].belief_update = f"доверие к приметам {before:.0%}→{agent.beliefs.signal_trust():.0%}"
        else:
            sig["dec"].outcome = "буря началась после темноты — он этого не видел"
            sig["dec"].belief_update = "ничего не узнал: исход прогноза остался неизвестным"

    rec.actual_return, rec.carried = now, carried
    rec.after_dark = now > world.day_length
    fuel += carried
    target_dec.outcome = (f"дома в {clock(now)} с {carried}, ожидал к {clock(rec.predicted_return)}"
                          + (", уже темно" if rec.after_dark else ""))
    rec.events.append(f"{clock(now)} дома, принёс {carried}" + (" — уже стемнело" if rec.after_dark else ""))

    scare = rec.after_dark or rec.crisis or rec.caught_in_storm or rec.min_core_c < HYPOTHERMIC_C
    note = agent.update_margin(scare=scare, on_time=not scare)
    if note:
        rec.events.append(note)
        target_dec.belief_update += note
    return _finish_day(world, rec, fuel, charge_legacy_night)


def _finish_day(world: World, rec: DayRecord, fuel: int, legacy: bool) -> tuple[DayRecord, int]:
    """Integrated loops own night once. Legacy day-only experiments keep their old flat charge."""
    if legacy:
        return _night(world, rec, fuel)
    rec.next_intention = "выйти за топливом" if fuel <= world.fuel_per_night else "выхода не требуется"
    return rec, fuel


def _night(world: World, rec: DayRecord, fuel: int) -> tuple[DayRecord, int]:
    fuel -= world.fuel_per_night
    if fuel < 0:
        rec.cold_night = True
        rec.events.append("ночь без огня")
        fuel = 0
    rec.next_intention = "выйти за топливом" if fuel <= world.fuel_per_night else "выхода не требуется"
    return rec, fuel


def run_end_reason(world: World, body: Body, agent: Agent, fuel: int, cold_nights: int) -> str | None:
    """Why this run cannot go on. A run that never ends makes its own averages meaningless.

    Resources are finite by the author's decision and do not come back, so exhaustion is a legitimate
    ending, not a defect to balance away.
    """
    if body.core_c <= DEATH_C + 0.2:
        return "замёрз"
    if body.fatigue >= 100.0:
        return "силы кончились"
    if fuel <= 0 and not any(v > 0 for v in world.loot.values()):
        return "район исчерпан: топлива нет и брать негде"
    if cold_nights >= 3:
        return "три ночи без огня подряд"
    return None


def run(world_name: str, variant: str, profile: str, days: int, seed: int,
        signals_visible: bool = True, body: Body | None = None) -> list[DayRecord]:
    """Weather depends only on (seed, day), never on what the player did: conditions stay paired.

    `body` may be supplied by a caller that owns continuity across a longer run; otherwise a fresh one
    is made here and still carries across all the days of this run.
    """
    world = World.load(world_name, variant)
    agent = Agent(profile, world)
    body = body if body is not None else Body()
    loot_rng = random.Random(f"{seed}:loot")
    fuel = world.start_fuel
    records: list[DayRecord] = []
    cold_streak = 0
    for d in range(1, days + 1):
        weather = world.roll_weather(random.Random(f"{seed}:weather:{d}"))
        rec, fuel = run_day(world, agent, weather, loot_rng, d, fuel, signals_visible, body)
        cold_streak = cold_streak + 1 if rec.cold_night else 0
        records.append(rec)
        reason = run_end_reason(world, body, agent, fuel, cold_streak)
        if reason:
            rec.run_end_reason = reason
            rec.events.append(f"прогон окончен: {reason}")
            break
    return records
