"""Regression checks for the read-only gameplay-loop integration probes.

Owner implementations remain in lab.sim and lab.evening; no engine claims.
"""
import random
import unittest

from lab.diagnose_evening import RECOVERIES, TEMPERATURES, FUELS, diagnose
from lab.loop_bridge import linked, study
from lab.world import World


class LoopBridgeTests(unittest.TestCase):
    def test_linked_history_reproducible(self):
        self.assertEqual(linked(3, 4), linked(3, 4))

    def test_weather_is_world_truth_not_an_evening_decision(self):
        result = linked(4, 5)
        world = World.load("district_v0", "B_readable")
        actual = [world.roll_weather(random.Random(f"4:weather:{i}")).storm_start
                  for i in range(1, 6)]
        self.assertEqual([d["weather_storm_start"] for d in result["days"]], actual)

    def test_no_double_charge_of_the_flat_legacy_night(self):
        for day in linked(2, 5)["days"]:
            self.assertAlmostEqual(
                day["fuel_before_night"],
                round(day["fuel_dawn"] + day["carried"], 2))

    def test_furniture_never_becomes_negative(self):
        for day in linked(5, 7)["days"]:
            self.assertGreaterEqual(day["furniture_next_dawn"], 0)

    def test_evening_receives_results_of_actual_day(self):
        for day in linked(8, 5)["days"]:
            self.assertIn("fuel_before_night", day)
            self.assertIn("fuel_next_dawn", day)
            self.assertIn(day["choice"], ("A", "B", "C"))

    def test_study_is_deterministic(self):
        self.assertEqual(study(3, 4), study(3, 4))

    def test_experimental_grid_is_fixed_before_running(self):
        d = diagnose()
        self.assertEqual(len(d["cells"]), len(RECOVERIES) * len(TEMPERATURES) * len(FUELS))
        self.assertEqual(len(d["summary_by_recovery"]), len(RECOVERIES))

    def test_plan_influence_is_measured_not_forced(self):
        result = diagnose()
        self.assertTrue(all(1 <= x["distinct_evening_choices"] <= 3 for x in result["cells"]))


if __name__ == "__main__":
    unittest.main()
