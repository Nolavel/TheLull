"""Acceptance tests for the FIRST shared dawn-to-dawn gameplay sequence.

These must fail on broken time/body/fuel continuity rather than claiming
that one authored evening decision must always be preferred.
"""
import unittest

from lab.body import Body
from lab.evening import EXPEDITION, SHORT_WALK
from lab.survival_loop import run, study


class SurvivalLoopContract(unittest.TestCase):
    def test_one_day_uses_exactly_1440_minutes(self):
        for variant in ("A_safe", "B_readable", "C_unreadable"):
            for seed in range(1, 8):
                story = run(seed=seed, variant=variant, days=4)
                self.assertTrue(story["history"])
                for day in story["history"]:
                    self.assertAlmostEqual(day["minutes_accounted"], 1440.0)
                    self.assertEqual(day["next_dawn_minute"] - day["starting_dawn_minute"], 1440)

    def test_the_same_body_continues_across_dawn(self):
        result = run(seed=3, days=4)
        for previous, following in zip(result["history"], result["history"][1:]):
            self.assertAlmostEqual(previous["core_next_dawn"], following["core_at_dawn"])
            self.assertAlmostEqual(previous["fatigue_next_dawn"], following["fatigue_at_dawn"])

    def test_fuel_and_furniture_carry_between_days(self):
        result = run(seed=5, days=7)
        for previous, following in zip(result["history"], result["history"][1:]):
            self.assertAlmostEqual(previous["fuel_next_dawn"], following["fuel_at_dawn"])
            self.assertEqual(previous["furniture_next_dawn"], following["furniture_at_dawn"])

    def test_fuel_cannot_appear_from_the_absence_of_furniture(self):
        result = run(seed=2, days=5, initial_furniture=0)
        for day in result["history"]:
            self.assertEqual(day["furniture_next_dawn"], 0)
            self.assertNotEqual(day["evening"]["chose"][:1], "A")
            self.assertLessEqual(day["fuel_next_dawn"], day["fuel_at_dawn"] + day["carried"] + 1e-6)

    def test_world_resources_are_conserved(self):
        for seed in range(1, 10):
            result = run(seed=seed, days=7)
            for d in result["history"]:
                max_fuel = d["fuel_at_dawn"] + d["carried"] + 4 * (
                    d["furniture_at_dawn"] - d["furniture_next_dawn"])
                self.assertLessEqual(d["fuel_next_dawn"], max_fuel + 1e-6)
                self.assertGreaterEqual(d["fuel_next_dawn"], 0)
                self.assertTrue(all(v >= 0 for v in d["remaining_loot"].values()))

    def test_paired_plans_preserve_the_weather_truth(self):
        a = run(seed=3, days=4, intentions=[SHORT_WALK])
        b = run(seed=3, days=4, intentions=[EXPEDITION])
        for x, y in zip(a["history"], b["history"]):
            self.assertEqual(x["world_weather"], y["world_weather"])

    def test_reproduction_by_seed(self):
        self.assertEqual(run(seed=9, days=4), run(seed=9, days=4))
        self.assertEqual(study(seeds=3, days=4), study(seeds=3, days=4))

    def test_day_and_night_share_the_one_body_model(self):
        from lab import evening
        self.assertIs(evening.Body, Body)

    def test_day_and_night_share_one_belief_class(self):
        from lab.agent import Beliefs
        from lab.evening import EveningBeliefs
        self.assertIs(EveningBeliefs, Beliefs)

    def test_run_reports_end_or_explicit_horizon(self):
        for seed in range(1, 6):
            story = run(seed=seed, days=7)
            self.assertEqual(story["days_completed"], len(story["history"]))
            self.assertTrue(story["end_reason"] or story["days_completed"] == 7)


if __name__ == "__main__":
    unittest.main()
