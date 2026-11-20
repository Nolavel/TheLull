"""Contracts of the world and of game time. Any integration of the lab must keep these green.

Owner: Claude (`world.py`, `agent.py`, `sim.py`, `experiment.py`). These tests do not care *how* the
evening cycle is written — they state what must stay true about the world underneath it, so the owner of
the evening cycle can rework it freely without silently breaking the simulation.

If a test here fails after an integration, it is not a style disagreement: either the contract is broken
or the contract itself needs changing, in writing, with the author.
"""
import random
import unittest
from dataclasses import asdict

from lab.agent import Agent
from lab.sim import run
from lab.world import CALM_WIND, STORM_WIND, World

WORLD, VARIANTS, PROFILES = "district_v0", ("A_safe", "B_readable", "C_unreadable"), ("novice", "local")


class ReproducibilityContract(unittest.TestCase):
    """Same inputs, same story — otherwise results cannot be compared between commits."""

    def test_the_same_seed_gives_the_same_days(self):
        for variant in VARIANTS:
            for profile in PROFILES:
                a = [asdict(r) for r in run(WORLD, variant, profile, 8, seed=7)]
                b = [asdict(r) for r in run(WORLD, variant, profile, 8, seed=7)]
                self.assertEqual(a, b, f"{variant}/{profile} не воспроизводится")

    def test_different_seeds_do_diverge(self):
        """A guard against a world that ignores its seed and always plays the same day."""
        stories = {tuple((r.target, round(r.actual_return or 0, 1)) for r in run(WORLD, "B_readable", "local", 8, s))
                   for s in range(1, 8)}
        self.assertGreater(len(stories), 1)


class WeatherContract(unittest.TestCase):
    """Weather is the world's own truth: it must not bend to what the player did."""

    def test_weather_depends_only_on_seed_and_day(self):
        world = World.load(WORLD, "B_readable")
        for seed in range(1, 6):
            for day in range(1, 9):
                a = world.roll_weather(random.Random(f"{seed}:weather:{day}"))
                b = world.roll_weather(random.Random(f"{seed}:weather:{day}"))
                self.assertEqual((a.storm_start, a.storm_end, a.signal_at),
                                 (b.storm_start, b.storm_end, b.signal_at))

    def test_player_actions_never_move_the_weather(self):
        """Paired conditions: change what the player may see, the storms must stay put."""
        for seed in range(1, 11):
            on = run(WORLD, "B_readable", "local", 8, seed, signals_visible=True)
            off = run(WORLD, "B_readable", "local", 8, seed, signals_visible=False)
            self.assertEqual([(r.storm_start, r.storm_end) for r in on],
                             [(r.storm_start, r.storm_end) for r in off],
                             f"seed {seed}: погода сдвинулась от поведения игрока")

    def test_one_seed_gives_one_day_in_every_variant(self):
        """Variants move thresholds, not the story: a stormy day stays stormy in a harsher variant."""
        calm, harsh = World.load(WORLD, "A_safe"), World.load(WORLD, "B_readable")
        for seed in range(1, 21):
            for day in range(1, 9):
                a = calm.roll_weather(random.Random(f"{seed}:weather:{day}"))
                b = harsh.roll_weather(random.Random(f"{seed}:weather:{day}"))
                if a.storm_start is not None:
                    self.assertEqual(a.storm_start, b.storm_start)
                    self.assertIsNotNone(b.storm_start)

    def test_wind_is_higher_in_a_storm_than_outside_one(self):
        world = World.load(WORLD, "B_readable")
        weather = world.roll_weather(random.Random("fixed"))
        if weather.storm_start is not None:
            self.assertEqual(weather.wind(weather.storm_start), STORM_WIND)
            self.assertEqual(weather.wind(max(0, weather.storm_start - 1)), CALM_WIND)


class KnowledgeContract(unittest.TestCase):
    """The player acts on what it experienced. The simulator's truth must not leak into its beliefs."""

    def test_the_agent_never_reads_the_true_remaining_loot(self):
        world = World.load(WORLD, "B_readable")
        agent = Agent("novice", world)
        agent.beliefs.loot["house_a"] = 6.0
        world.loot["house_a"] = 99
        agent.learn_loot("house_a", 0)
        self.assertEqual(agent.beliefs.loot["house_a"], 0.0)
        self.assertEqual(world.loot["house_a"], 99)

    def test_a_profile_starts_with_limited_knowledge_of_the_map(self):
        world = World.load(WORLD, "B_readable")
        self.assertLess(len(Agent("novice", world).beliefs.edge_minutes), len(world.edges))

    def test_hidden_signs_leave_no_sign_decisions(self):
        for seed in range(1, 6):
            for r in run(WORLD, "B_readable", "local", 8, seed, signals_visible=False):
                self.assertFalse([d for d in r.decisions if d.point == "сигнал"])


class TimeContract(unittest.TestCase):
    """Game time only moves forward, and everything that happens is billed to it."""

    def test_a_day_never_runs_backwards(self):
        for seed in range(1, 6):
            for r in run(WORLD, "B_readable", "local", 8, seed):
                if r.went_out:
                    self.assertIsNotNone(r.actual_return)
                    self.assertGreater(r.actual_return, 0.0)
                    self.assertGreaterEqual(r.actual_return, r.actual_travel)

    def test_walking_costs_time_and_the_forecast_is_recorded(self):
        for seed in range(1, 6):
            for r in run(WORLD, "B_readable", "novice", 8, seed):
                if r.went_out:
                    self.assertGreater(r.actual_travel, 0.0)
                    self.assertIsNotNone(r.travel_error)

    def test_a_storm_makes_an_exposed_street_slower(self):
        world = World.load(WORLD, "B_readable")
        edge = max(world.edges, key=lambda e: e.exposure)
        weather = type("W", (), {"wind": staticmethod(lambda m: STORM_WIND), "is_storm": lambda *_: True})()
        calm = type("W", (), {"wind": staticmethod(lambda m: CALM_WIND), "is_storm": lambda *_: False})()
        self.assertGreater(world.travel_minutes(edge, 10, weather), world.travel_minutes(edge, 10, calm))


class DecisionRecordContract(unittest.TestCase):
    """Every trip must stay explainable: what was wanted, what was weighed, what was chosen and why."""

    def test_each_trip_records_one_target_decision_with_a_reason(self):
        for seed in range(1, 6):
            for r in run(WORLD, "B_readable", "local", 8, seed):
                if not r.went_out:
                    continue
                target = [d for d in r.decisions if d.point in ("цель", "разведка")]
                self.assertEqual(len(target), 1, f"день {r.day}: целевых решений {len(target)}")
                self.assertTrue(target[0].reason and target[0].alternatives and target[0].outcome)

    def test_every_day_ends_with_a_next_intention(self):
        for r in run(WORLD, "B_readable", "local", 8, seed=3):
            self.assertTrue(r.next_intention)


if __name__ == "__main__":
    unittest.main()
