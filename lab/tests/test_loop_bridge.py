"""Compatibility and neutral experiment checks after removing the duplicate bridge."""
import unittest

from lab.diagnose_evening import RECOVERIES, TEMPERATURES, FUELS, diagnose
from lab.loop_bridge import linked, study
from lab.survival_loop import run


class LoopBridgeTests(unittest.TestCase):
    def test_the_old_entrypoint_reuses_the_real_integrator(self):
        self.assertEqual(linked(2, 3), run(2, 3))

    def test_same_seed_reproduces_connected_history(self):
        self.assertEqual(linked(3, 4), linked(3, 4))

    def test_one_world_clock_no_legacy_rollback(self):
        for d in linked(7, 5)["history"]:
            if d["completed_dawn"]:
                self.assertAlmostEqual(d["minutes_accounted"], 1440.0)
            else:
                self.assertLess(d["minutes_accounted"], 1440.0)
                self.assertIsNone(d["next_dawn_minute"])

    def test_study_is_deterministic(self):
        self.assertEqual(study(3, 4), study(3, 4))

    def test_grid_is_predefined_not_tuned_to_an_outcome(self):
        d = diagnose()
        self.assertEqual(len(d["cells"]), len(RECOVERIES) * len(TEMPERATURES) * len(FUELS))
        self.assertEqual(len(d["summary_by_recovery"]), len(RECOVERIES))

    def test_plan_influence_is_measured_not_required(self):
        result = diagnose()
        self.assertTrue(all(1 <= row["distinct_evening_choices"] <= 3
                            for row in result["cells"]))


if __name__ == "__main__":
    unittest.main()
