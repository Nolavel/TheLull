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

    def signal_trust(self) -> float:
        return self.signal_hits / (self.signal_hits + self.signal_misses)


class Agent:
    def __init__(self, profile: str, world: World):
        p = PROFILES[profile]
        self.profile = profile
        self.margin = float(p["margin_min"])
        self.base_margin = float(p["margin_min"])
        self.beliefs = Beliefs(knows_storms_pass=p["knows_storms_pass"])
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
        if storm_followed:
            self.beliefs.signal_hits += 1
        else:
            self.beliefs.signal_misses += 1

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

    def choose_target(self) -> str | None:
        best, best_score = None, 0.0
        for node, loot in self.beliefs.loot.items():
            if loot <= 0:
                continue
            minutes, _ = self.path("home", node)
            score = min(loot, CARRY_CAPACITY) / (2 * minutes + SEARCH_CHUNK_MIN)
            if score > best_score:
                best, best_score = node, score
        return best

    def update_margin(self, scare: bool, on_time: bool) -> str:
        if scare:
            self.margin = max(self.margin * 2, self.base_margin)
            return "после испуга запас времени удвоен"
        if on_time:
            self.margin = max(5.0, self.margin * 0.85)
            return "всё прошло гладко — запас времени сокращён (привычка, возможна самоуверенность)"
        return ""
