"""Virtual player: acts only on its own beliefs and updates them from experience.

Confidence is not a stored number. It shows up in observables: prediction error,
safety margin, plan changes and how often the plan survives contact with the world.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from .world import WALK_SPEED_M_PER_MIN, Edge, World

PROFILES = {
    # Knows only the direct street; underestimates distance; ignores weather signs.
    "novice": {
        "known_edges": [("home", "house_a")],
        "distance_bias": 0.6,
        "knows_wind_matters": False,
        "loot_prior": 6,
        "signal_prior": (1, 3),
        "margin_min": 20,
        "knows_storms_pass": False,
        "storm_duration_est": None,
    },
    # Lives here: knows the streets and the shed, reads the sky, keeps a margin.
    "local": {
        "known_edges": "all",
        "distance_bias": 1.0,
        "knows_wind_matters": True,
        "loot_prior": 4,
        "signal_prior": (3, 1),
        "margin_min": 45,
        "knows_storms_pass": True,
        "storm_duration_est": 90.0,
    },
}

CARRY_CAPACITY = 4
SEARCH_CHUNK_MIN = 30
EMA = 0.5
# Low-valued, uncertain *revisit* only; never a guessed count of real stock.
RECHECK_EXPECTED_LOOT = 0.75


def edge_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


@dataclass
class Beliefs:
    edge_minutes: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)
    loot: dict[str, float] = field(default_factory=dict)
    # This is observation, not a deduction from an exhausted prior.
    confirmed_empty: set[str] = field(default_factory=set)
    signal_hits: float = 1.0
    signal_misses: float = 1.0
    knows_storms_pass: bool = False
    storm_duration_est: float | None = None  # what the player believes, never the world's truth
    # One memory for one person. These were a separate EveningBeliefs object, so a lesson learned at
    # night never reached the next day's trip. The evening cycle reads and updates them here.
    cooling_rate_est: float = 3.0  # how fast the player thinks the room bleeds its warmth, °C/h
    burn_rate_est: float = 1.0  # how fast the player thinks fuel burns, units/h
    recovery_est: float = 6.0  # how much rest the player thinks a warm hour of sleep pays back
    work_hours_est: dict[str, float] = field(default_factory=dict)
    # Thermal beliefs are explicitly tentative; they are updated from the
    # body's lived observations, NEVER copied from the hidden physics knobs.
    shelter_core_cooling_est: float = 1.0  # °C of body core lost per sheltered hour
    stove_effect_est: float = 8.0          # guessed benefit of a lit stove (°C felt)
    # Clothing-trip beliefs learn only from the actor's own finished walks.
    # Wet cost is observed directly; a counterfactual dry advantage remains
    # a fallible prior and is never copied from the world's hidden coefficients.
    wet_walk_stamina_per_h_est: float = 16.0
    wet_walk_core_loss_per_h_est: float = 0.7
    wet_walk_samples: int = 0
    # An explicit prediction error is an actor observation. Not a reward,
    # not a known dry-clothing counterfactual, and not the world's hidden data.
    # key = traversed directed route string, value = most recent *signed* errors.
    trip_prediction_errors: dict[str, dict[str, float]] = field(default_factory=dict)

    def observe_trip_prediction(
        self, route: str, *, predicted_minutes: float, actual_minutes: float,
        predicted_stamina_demand: float, actual_stamina_demand: float,
        predicted_core_loss: float, actual_core_loss: float,
    ) -> str:
        """Compare a stored BEFORE-action estimate with an observed return.

        A failed/unfinished trip is not accepted as if the full route occurred.
        Caller must require a complete observed return. Signed errors preserve
        over-optimistic and over-pessimistic forecasts instead of hiding misses.
        """
        if not route:
            raise ValueError("route must be the observed route")
        fields = (predicted_minutes, actual_minutes,
                  predicted_stamina_demand, actual_stamina_demand,
                  predicted_core_loss, actual_core_loss)
        if not all(math.isfinite(x) for x in fields):
            raise ValueError("forecast/observation must be finite")
        if (predicted_minutes <= 0 or actual_minutes <= 0 or
            predicted_stamina_demand < 0 or actual_stamina_demand < 0 or
            predicted_core_loss < 0 or actual_core_loss < 0):
            raise ValueError("forecast/observation must have physical bounds")
        previous = self.trip_prediction_errors.get(route)
        sample = (int(previous["samples"]) + 1) if previous else 1
        errors = {
            "minutes": actual_minutes - predicted_minutes,
            "stamina": actual_stamina_demand - predicted_stamina_demand,
            "core": actual_core_loss - predicted_core_loss,
        }
        self.trip_prediction_errors[route] = {
            "minutes": errors["minutes"],
            "stamina": errors["stamina"],
            "core": errors["core"],
            "samples": float(sample),
        }
        return (
            f"сверил прогноз с опытом на {route}: "
            f"минуты {predicted_minutes:.1f}→{actual_minutes:.1f} "
            f"(ошибка {errors['minutes']:+.1f}); "
            f"расход stamina {predicted_stamina_demand:.1f}→{actual_stamina_demand:.1f} "
            f"(ошибка {errors['stamina']:+.1f}); "
            f"потери core {predicted_core_loss:.2f}→{actual_core_loss:.2f} "
            f"(ошибка {errors['core']:+.2f})"
        )

    def observe_wet_walk(self, *, hours: float, stamina_demand: float,
                         core_before: float, core_after: float) -> str:
        if hours <= 0:
            return ""
        stamina_h = max(0.0, stamina_demand / hours)
        core_h = max(0.0, (core_before - core_after) / hours)
        old = (self.wet_walk_stamina_per_h_est,
               self.wet_walk_core_loss_per_h_est)
        self.wet_walk_stamina_per_h_est = 0.5 * old[0] + 0.5 * stamina_h
        self.wet_walk_core_loss_per_h_est = 0.5 * old[1] + 0.5 * core_h
        self.wet_walk_samples += 1
        return (f"пережитая мокрая ходьба {hours:.2f} ч: "
                f"stamina/ч {old[0]:.2f}→{self.wet_walk_stamina_per_h_est:.2f}, "
                f"core/ч {old[1]:.2f}→{self.wet_walk_core_loss_per_h_est:.2f}")

    def observe_shelter_cooling(self, before_c: float, after_c: float,
                               elapsed_h: float) -> str:
        """A measurable, completed unheated interval informs later fire choices."""
        if elapsed_h <= 1e-8 or before_c <= after_c:
            return ""
        measured = (before_c - after_c) / elapsed_h
        old = self.shelter_core_cooling_est
        self.shelter_core_cooling_est = max(0.05, 0.5 * old + 0.5 * measured)
        return (f"охлаждение тела в убежище: "
                f"{old:.2f}→{self.shelter_core_cooling_est:.2f} °C/ч")

    def expected_work_hours(self, work) -> float:
        return self.work_hours_est.get(work.name, work.hours)

    def observe_burn_rate(self, measured_per_h: float) -> str:
        if measured_per_h <= 0:
            raise ValueError("observed burn rate must be positive")
        old = self.burn_rate_est
        self.burn_rate_est = 0.5 * old + 0.5 * measured_per_h
        return f"наблюдаемый расход топлива: {old:.2f}→{self.burn_rate_est:.2f} в час"

    def observe_rate_lower_bound(self, minimum_per_h: float) -> str:
        if minimum_per_h <= 0:
            raise ValueError("rate bound must be positive")
        old = self.burn_rate_est
        if old >= minimum_per_h:
            return "погасший огонь не уточнил оценку расхода"
        self.burn_rate_est = 0.5 * (old + minimum_per_h)
        return (f"огонь уже погас: расход не меньше {minimum_per_h:.2f} в час; "
                f"оценка {old:.2f}→{self.burn_rate_est:.2f}")

    def hours_of_fire(self, fuel: float) -> float:
        return fuel / max(0.1, self.burn_rate_est)

    def signal_trust(self) -> float:
        return self.signal_hits / (self.signal_hits + self.signal_misses)


class Agent:
    def __init__(self, profile: str, world: World, *, allow_rechecks: bool = True):
        p = PROFILES[profile]
        # Explicit control arm for paired experiments; the canonical loop opts in.
        self.allow_rechecks = allow_rechecks
        self.profile = profile
        self.margin = float(p["margin_min"])
        self.base_margin = float(p["margin_min"])
        self.beliefs = Beliefs(knows_storms_pass=p["knows_storms_pass"],
                               storm_duration_est=p["storm_duration_est"])
        self.visited: set[str] = set()
        self.beliefs.signal_hits, self.beliefs.signal_misses = map(float, p["signal_prior"])
        known = world.edges if p["known_edges"] == "all" else [world.edge(a, b) for a, b in p["known_edges"]]
        for e in known:
            self._learn_edge_prior(e, p["distance_bias"], p["knows_wind_matters"])
        for node, data in world.nodes.items():
            if data["kind"] == "building" and self._knows_node(node):
                self.beliefs.loot[node] = float(p["loot_prior"])
        self._profile = p

    # --- knowledge -------------------------------------------------------
    def _learn_edge_prior(self, e: Edge, bias: float, knows_wind: bool) -> None:
        calm = e.length_m / WALK_SPEED_M_PER_MIN * bias * (1 + 0.2 * 1.5 * e.exposure)
        windy = calm * (1 + 1.5 * e.exposure) if knows_wind else calm
        self.beliefs.edge_minutes[edge_key(e.a, e.b)] = {"calm": calm, "storm": windy}

    def _knows_node(self, node: str) -> bool:
        return node == "home" or any(node in k for k in self.beliefs.edge_minutes)

    def discover(self, node: str, world: World) -> list[str]:
        """Arriving at a node reveals the streets leading from it."""
        found = []
        for e in world.neighbours(node):
            if edge_key(e.a, e.b) not in self.beliefs.edge_minutes:
                self._learn_edge_prior(e, self._profile["distance_bias"], self._profile["knows_wind_matters"])
                found.append(e.other(node))
                other = e.other(node)
                if world.nodes[other]["kind"] == "building" and other not in self.beliefs.loot:
                    self.beliefs.loot[other] = float(self._profile["loot_prior"])
        return found

    def observe_edge(self, a: str, b: str, storm: bool, minutes: float) -> float:
        """Update the travel-time belief; returns the prediction it replaced."""
        slot = self.beliefs.edge_minutes[edge_key(a, b)]
        state = "storm" if storm else "calm"
        predicted = slot[state]
        slot[state] = (1 - EMA) * predicted + EMA * minutes
        if storm and slot["storm"] < slot["calm"]:
            slot["storm"] = slot["calm"]
        return predicted

    def observe_signal(self, storm_followed: bool) -> None:
        """Only call this when the player could actually see the outcome."""
        if storm_followed:
            self.beliefs.signal_hits += 1
        else:
            self.beliefs.signal_misses += 1

    def observe_storm_duration(self, minutes: float) -> str:
        """A storm the player sat through or walked through teaches how long they last."""
        before = self.beliefs.storm_duration_est
        self.beliefs.storm_duration_est = minutes if before is None else (1 - EMA) * before + EMA * minutes
        self.beliefs.knows_storms_pass = True
        was = f"{before:.0f}" if before is not None else "неизвестно"
        return f"представление о длине бури: {was}→{self.beliefs.storm_duration_est:.0f} мин"

    def expected_storm_left(self, waited: float) -> float:
        """How much longer the player *thinks* the storm will last. Never reads the world."""
        est = self.beliefs.storm_duration_est or 90.0
        return max(0.0, est - waited)

    # --- planning --------------------------------------------------------
    def path(self, start: str, goal: str, storm: bool = False) -> tuple[float, list[str]]:
        state = "storm" if storm else "calm"
        graph: dict[str, list[tuple[str, float]]] = {}
        for (a, b), m in self.beliefs.edge_minutes.items():
            graph.setdefault(a, []).append((b, m[state]))
            graph.setdefault(b, []).append((a, m[state]))
        queue = [(0.0, start, [start])]
        seen = set()
        while queue:
            cost, node, route = heapq.heappop(queue)
            if node == goal:
                return cost, route
            if node in seen:
                continue
            seen.add(node)
            for nxt, w in graph.get(node, []):
                if nxt not in seen:
                    heapq.heappush(queue, (cost + w, nxt, route + [nxt]))
        return float("inf"), []

    def can_recheck(self, node: str) -> bool:
        """An estimate of zero is not a confirmed observation of emptiness."""
        return (self.allow_rechecks and node in self.visited
                and node in self.beliefs.loot
                and self.beliefs.loot[node] <= 0
                and node not in self.beliefs.confirmed_empty)

    def rank_targets(self) -> list[dict]:
        """Rank likely loot first; offer costly, uncertain rechecks only if unconfirmed."""
        ranked = []
        for node, loot in self.beliefs.loot.items():
            recheck = self.can_recheck(node)
            if loot <= 0 and not recheck:
                continue
            minutes, route = self.path("home", node)
            if not route:
                continue
            expected = RECHECK_EXPECTED_LOOT if recheck else min(loot, CARRY_CAPACITY)
            score = expected / (2 * minutes + SEARCH_CHUNK_MIN)
            ranked.append({"node": node, "minutes": minutes, "loot": loot,
                           "recheck": recheck, "score": score})
        return sorted(ranked, key=lambda r: -r["score"])

    def choose_target(self) -> str | None:
        ranked = self.rank_targets()
        return ranked[0]["node"] if ranked else None

    def learn_loot(self, node: str, found: int) -> str:
        """Only actual searched results update knowledge, never the world's inventory."""
        if found < 0:
            raise ValueError("loot found cannot be negative")
        before = self.beliefs.loot.get(node, 0.0)
        after = 0.0 if found == 0 else max(0.0, before - found)
        self.beliefs.loot[node] = after
        if found == 0:
            # In this toy world's search model, a complete 30-minute search
            # finds at least one item whenever any stock is available.
            # If search ever becomes probabilistic, this must change to
            # "empty in this searched area", not an entire-building truth.
            self.beliefs.confirmed_empty.add(node)
            return f"обыск {node}: ничего не найдено, пустота подтверждена наблюдением"
        self.beliefs.confirmed_empty.discard(node)
        return (f"оценка запасов {node}: {before:.0f}→{after:.0f}; "
                + ("возможно, здесь осталось ещё" if after <= 0 else "запасы ещё ожидаются"))

    def update_margin(self, scare: bool, on_time: bool) -> str:
        if scare:
            self.margin = max(self.margin * 2, self.base_margin)
            return "после испуга запас времени удвоен"
        if on_time:
            self.margin = max(5.0, self.margin * 0.85)
            return "всё прошло гладко — запас времени сокращён (привычка, возможна самоуверенность)"
        return ""
