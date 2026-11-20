"""Virtual player: acts only on its own beliefs and updates them from experience.

Confidence is not a stored number. It shows up in observables: prediction error,
safety margin, plan changes and how often the plan survives contact with the world.
"""
from __future__ import annotations

import heapq
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


def edge_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


@dataclass
class Beliefs:
    edge_minutes: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)
    loot: dict[str, float] = field(default_factory=dict)
    signal_hits: float = 1.0
    signal_misses: float = 1.0
    knows_storms_pass: bool = False
    storm_duration_est: float | None = None  # what the player believes, never the world's truth

    def signal_trust(self) -> float:
        return self.signal_hits / (self.signal_hits + self.signal_misses)


class Agent:
    def __init__(self, profile: str, world: World):
        p = PROFILES[profile]
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

    def rank_targets(self) -> list[dict]:
        """Buildings the player believes still hold loot, best value first."""
        ranked = []
        for node, loot in self.beliefs.loot.items():
            if loot <= 0:
                continue
            minutes, route = self.path("home", node)
            if not route:
                continue
            score = min(loot, CARRY_CAPACITY) / (2 * minutes + SEARCH_CHUNK_MIN)
            ranked.append({"node": node, "minutes": minutes, "loot": loot, "score": score})
        return sorted(ranked, key=lambda r: -r["score"])

    def choose_target(self) -> str | None:
        ranked = self.rank_targets()
        return ranked[0]["node"] if ranked else None

    def learn_loot(self, node: str, found: int) -> str:
        """The player only knows what it found: no access to the building's true stock."""
        before = self.beliefs.loot.get(node, 0.0)
        after = 0.0 if found == 0 else max(0.0, before - found)
        self.beliefs.loot[node] = after
        return f"оценка запасов {node}: {before:.0f}→{after:.0f}"

    def update_margin(self, scare: bool, on_time: bool) -> str:
        if scare:
            self.margin = max(self.margin * 2, self.base_margin)
            return "после испуга запас времени удвоен"
        if on_time:
            self.margin = max(5.0, self.margin * 0.85)
            return "всё прошло гладко — запас времени сокращён (привычка, возможна самоуверенность)"
        return ""
