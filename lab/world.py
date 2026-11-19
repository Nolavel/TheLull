"""World model: a small district graph, daily weather and finite loot.

The world knows the truth; agents only see what they experience.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

WORLDS_DIR = Path(__file__).parent / "worlds"

WALK_SPEED_M_PER_MIN = 72.0  # ~1.2 m/s in snow
CALM_WIND = 0.2
STORM_WIND = 1.0


@dataclass
class Edge:
    a: str
    b: str
    length_m: float
    exposure: float  # 0 = between buildings, 1 = open street

    def other(self, node: str) -> str:
        return self.b if node == self.a else self.a


@dataclass
class DayWeather:
    """Truth for one day; minutes are counted from the start of the day."""

    storm_start: int | None
    storm_end: int | None
    signal_at: int | None  # when a readable sign appears (may be a false alarm)

    def wind(self, minute: float) -> float:
        if self.storm_start is not None and self.storm_start <= minute < self.storm_end:
            return STORM_WIND
        return CALM_WIND

    def is_storm(self, minute: float) -> bool:
        return self.wind(minute) >= STORM_WIND


@dataclass
class World:
    name: str
    variant: str
    day_length: int
    fuel_per_night: int
    start_fuel: int
    nodes: dict[str, dict]
    edges: list[Edge]
    weather_rules: dict
    loot: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, name: str, variant: str) -> "World":
        data = json.loads((WORLDS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        v = data["variants"][variant]
        edges = [Edge(**e) for e in data["edges"]]
        loot = {n: int(round(d.get("loot", 0) * v["loot_scale"])) for n, d in data["nodes"].items()}
        return cls(
            name=name,
            variant=variant,
            day_length=data["day_length_min"],
            fuel_per_night=data["fuel_per_night"],
            start_fuel=data["start_fuel"],
            nodes=data["nodes"],
            edges=edges,
            weather_rules=v,
            loot=loot,
        )

    def neighbours(self, node: str) -> list[Edge]:
        return [e for e in self.edges if node in (e.a, e.b)]

    def edge(self, a: str, b: str) -> Edge:
        for e in self.edges:
            if {e.a, e.b} == {a, b}:
                return e
        raise KeyError((a, b))

    def travel_minutes(self, edge: Edge, minute: float, weather: DayWeather) -> float:
        base = edge.length_m / WALK_SPEED_M_PER_MIN
        slow = 1.0 + edge.exposure * weather.wind(minute) * 1.5
        dark = 1.5 if minute >= self.day_length else 1.0
        return base * slow * dark

    def warmth_loss_per_min(self, exposure: float, minute: float, weather: DayWeather) -> float:
        return 0.3 + exposure * weather.wind(minute) * 2.5

    def roll_weather(self, rng: random.Random) -> DayWeather:
        """Always draws four numbers, so one seed gives the same day in every variant.

        Variants only move the thresholds: a day stormy in a calm variant stays stormy in a harsher one.
        """
        r = self.weather_rules
        u_storm, u_time, u_len, u_false = (rng.random() for _ in range(4))
        if u_storm < r["storm_chance"]:
            storm_start = int(90 + u_time * (self.day_length - 150))
            storm_end = storm_start + int(60 + u_len * 60)
            signal_at = storm_start - r["signal_lead_min"] if r["signal_lead_min"] > 0 else None
            return DayWeather(storm_start, storm_end, signal_at)
        if u_false < r["false_signal_chance"]:
            return DayWeather(None, None, int(60 + u_time * (self.day_length - 120)))
        return DayWeather(None, None, None)
