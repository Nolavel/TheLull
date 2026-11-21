"""Predeclared epistemic-policy experiment; no hard-coded desired effect."""
import unittest
from lab.recheck_study import study
from lab.survival_loop import run


class RecheckStudyContract(unittest.TestCase):
    def test_pairs_are_reproducible_without_rebalancing(self):
        self.assertEqual(study(2, 4), study(2, 4))

    def test_agent_policy_does_not_touch_objective_weather(self):
        result = study(2, 4)
        self.assertEqual(result["design"]["run_count"], 12)
        self.assertEqual(result["checks"]["same_seed_weather_mismatches"], 0)

    def test_finite_resources_and_search_charges(self):
        result = study(3, 5)
        for check in ("resource_conservation_failures",
                      "confirmed_empty_with_remaining_real_stock",
                      "more_than_one_recheck_chunk_in_trip"):
            self.assertEqual(result["checks"][check], 0, check)

    def test_old_control_does_not_perform_any_rechecks(self):
        result = run(9, 7, variant="A_safe", profile="local", recheck_policy=False)
        self.assertFalse(any(d["day_trip"]["recheck_searches"]
                             for d in result["history"]))

    def test_new_policy_does_not_create_items(self):
        result = run(9, 7, variant="A_safe", profile="local", recheck_policy=True)
        for d in result["history"]:
            self.assertLessEqual(d["fuel_next_dawn"], d["fuel_at_dawn"] + d["carried"] +
                                 4 * (d["furniture_at_dawn"] - d["furniture_next_dawn"]) + .01)


if __name__ == "__main__":
    unittest.main()
