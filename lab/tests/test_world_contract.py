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
            # The two runs can end on different days. Compare the common
            # weather prefix, not their lengths (which are gameplay outcomes).
            shared = min(len(on), len(off))
            self.assertEqual([(r.storm_start, r.storm_end) for r in on[:shared]],
                             [(r.storm_start, r.storm_end) for r in off[:shared]])
            import random
            world = World.load("district_v0", "B_readable")
            for d in on + off:
                expected = world.roll_weather(random.Random(f"{seed}:weather:{d.day}"))
                self.assertEqual((d.storm_start, d.storm_end),
                                 (expected.storm_start, expected.storm_end))

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


class ContinuityContract(unittest.TestCase):
    """The four contracts the author approved on 20.11.2026. Breaking one breaks the loop itself."""

    def test_the_day_and_the_night_make_a_whole_day(self):
        for variant in VARIANTS:
            world = World.load(WORLD, variant)
            self.assertAlmostEqual(world.daylight_hours + world.night_hours, 24.0, places=6)

    def test_the_clock_is_absolute_and_departure_follows_dawn(self):
        world = World.load(WORLD, "B_readable")
        for seed in range(1, 5):
            for r in run(WORLD, "B_readable", "local", 6, seed):
                if r.went_out:
                    self.assertGreaterEqual(r.actual_return, world.dawn_min)
                    self.assertLess(r.actual_return, 24 * 60 + world.dawn_min)

    def test_the_body_is_not_reset_at_dawn(self):
        """The hole that made every night meaningless: warmth went back to full each morning."""
        from lab.body import Body, step_core
        world = World.load(WORLD, "C_unreadable")
        body = Body()
        step_core(body, -30.0, 6.0)  # a bad night before the run starts
        chilled = body.core_c
        self.assertLess(chilled, 37.0)
        run(WORLD, "C_unreadable", "local", 3, seed=2, body=body)
        self.assertNotEqual(body.core_c, 37.0, "тело сбросилось к норме — непрерывность потеряна")

    def test_one_memory_carries_both_the_street_and_the_stove(self):
        world = World.load(WORLD, "B_readable")
        beliefs = Agent("local", world).beliefs
        for field in ("edge_minutes", "loot", "signal_hits", "storm_duration_est",
                      "cooling_rate_est", "burn_rate_est", "recovery_est"):
            self.assertTrue(hasattr(beliefs, field), f"память разошлась: нет {field}")

    def test_a_run_ends_with_a_stated_reason(self):
        """Resources are finite and do not come back, so a run must be able to end and say why."""
        ended = []
        for seed in range(1, 16):
            records = run(WORLD, "C_unreadable", "novice", 30, seed)
            last = records[-1]
            if last.run_end_reason:
                ended.append(last.run_end_reason)
                self.assertLess(len(records), 30, "прогон объявлен оконченным, но продолжался")
        self.assertTrue(ended, "ни один прогон из 15 не закончился — условие конца не работает")
        self.assertTrue(all(r for r in ended))

    def test_an_exposed_street_in_a_storm_is_colder_than_being_indoors(self):
        world = World.load(WORLD, "B_readable")
        storm = type("W", (), {"wind": staticmethod(lambda m: STORM_WIND)})()
        self.assertLess(world.felt_outdoors_c(0.9, 600, storm), world.felt_outdoors_c(0.15, 600, storm))
