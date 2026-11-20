import unittest
from dataclasses import asdict

from lab.agent import Agent
from lab.sim import run
from lab.world import World


class LabTest(unittest.TestCase):
    def test_same_seed_same_story(self):
        a = [asdict(r) for r in run("district_v0", "B_readable", "novice", 8, seed=3)]
        b = [asdict(r) for r in run("district_v0", "B_readable", "novice", 8, seed=3)]
        self.assertEqual(a, b)

    def test_travel_belief_moves_toward_experience(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("novice", world)
        before = agent.beliefs.edge_minutes[("home", "house_a")]["calm"]
        agent.observe_edge("home", "house_a", storm=False, minutes=before * 3)
        after = agent.beliefs.edge_minutes[("home", "house_a")]["calm"]
        self.assertGreater(after, before)
        self.assertLess(after, before * 3)

    def test_novice_knows_only_the_direct_street(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("novice", world)
        self.assertEqual(set(agent.beliefs.edge_minutes), {("home", "house_a")})
        found = agent.discover("house_a", world)
        self.assertIn("shed", found)

    def test_scare_widens_margin_success_narrows_it(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("local", world)
        m = agent.margin
        agent.update_margin(scare=False, on_time=True)
        self.assertLess(agent.margin, m)
        agent.update_margin(scare=True, on_time=False)
        self.assertGreaterEqual(agent.margin, m)


if __name__ == "__main__":
    unittest.main()


class OracleAndDecisionTest(unittest.TestCase):
    def test_same_seed_same_weather_across_variants(self):
        from lab.world import World as W
        calm, harsh = W.load("district_v0", "A_safe"), W.load("district_v0", "B_readable")
        import random
        for seed in range(30):
            ra, rb = random.Random(seed), random.Random(seed)
            for _ in range(8):
                a, b = calm.roll_weather(ra), harsh.roll_weather(rb)
                if a.storm_start is not None:
                    self.assertEqual(a.storm_start, b.storm_start)
                    self.assertIsNotNone(b.storm_start)

    def test_agent_never_sees_true_loot(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("novice", world)
        agent.beliefs.loot["house_a"] = 6.0
        world.loot["house_a"] = 9  # truth is larger; belief must not follow it
        agent.learn_loot("house_a", 0)
        self.assertEqual(agent.beliefs.loot["house_a"], 0.0)
        self.assertEqual(world.loot["house_a"], 9)

    def test_trip_days_record_decisions_with_reasons(self):
        records = run("district_v0", "B_readable", "local", 8, seed=1)
        trips = [r for r in records if r.went_out]
        self.assertTrue(trips)
        for r in trips:
            target = [d for d in r.decisions if d.point in ("цель", "разведка")]
            self.assertEqual(len(target), 1)
            self.assertTrue(target[0].reason)
            self.assertTrue(target[0].alternatives)
            self.assertTrue(target[0].outcome)
            self.assertIsNotNone(r.travel_error)


class PairedConditionsTest(unittest.TestCase):
    def test_weather_identical_when_signals_hidden(self):
        # One factor only: visibility of signs. Weather truth must not move with player choices.
        for seed in range(1, 11):
            on = run("district_v0", "B_readable", "local", 8, seed, signals_visible=True)
            off = run("district_v0", "B_readable", "local", 8, seed, signals_visible=False)
            self.assertEqual([(r.storm_start, r.storm_end) for r in on],
                             [(r.storm_start, r.storm_end) for r in off])

    def test_hidden_signals_produce_no_signal_decisions(self):
        for seed in range(1, 6):
            for r in run("district_v0", "B_readable", "local", 8, seed, signals_visible=False):
                self.assertFalse([d for d in r.decisions if d.point == "сигнал"])


class ObservableLearningTest(unittest.TestCase):
    def test_no_learning_from_a_storm_after_dark(self):
        from lab.sim import DayWeather, run_day
        world = World.load("district_v0", "B_readable")
        agent = Agent("local", world)
        before = agent.beliefs.signal_trust()
        # Sign at midday, storm only after the day ends: the player sleeps through it.
        weather = DayWeather(storm_start=world.day_length + 30, storm_end=world.day_length + 120,
                             signal_at=120)
        import random
        rec, _ = run_day(world, agent, weather, random.Random(0), 1, 0)
        sig = [d for d in rec.decisions if d.point == "сигнал"]
        if sig:
            self.assertEqual(agent.beliefs.signal_trust(), before)
            self.assertIn("не видел", sig[0].outcome)

    def test_agent_does_not_know_when_the_storm_ends(self):
        from lab.sim import DayWeather, run_day
        world = World.load("district_v0", "B_readable")
        agent = Agent("local", world)
        agent.beliefs.storm_duration_est = 30.0  # believes storms are short
        import random
        # A storm far longer than the belief: the player must give up waiting, not sit it out exactly.
        weather = DayWeather(storm_start=0, storm_end=world.day_length, signal_at=None)
        rec, _ = run_day(world, agent, weather, random.Random(0), 1, 0)
        self.assertFalse(rec.waited_out_storm)

    def test_storm_duration_is_learned_not_given(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("novice", world)
        self.assertIsNone(agent.beliefs.storm_duration_est)
        agent.observe_storm_duration(80.0)
        self.assertEqual(agent.beliefs.storm_duration_est, 80.0)
        agent.observe_storm_duration(120.0)
        self.assertGreater(agent.beliefs.storm_duration_est, 80.0)
        self.assertLess(agent.beliefs.storm_duration_est, 120.0)

    def test_waiting_in_a_waypoint_costs_more_than_at_home(self):
        from lab.sim import DayWeather
        world = World.load("district_v0", "B_readable")
        storm = DayWeather(0, 200, None)
        self.assertGreater(world.wait_loss_per_min("shed", 10, storm),
                           world.wait_loss_per_min("home", 10, storm))
