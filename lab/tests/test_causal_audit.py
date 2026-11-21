"""Causal study is reproducible and does not alter the main simulator."""
import unittest

from lab import evening
from lab.causal_audit import ARMS, analyze, simulate
from lab.survival_loop import run
from lab.world import World


class CausalAuditTest(unittest.TestCase):
    def test_control_arm_is_exactly_the_committed_gameplay(self):
        for seed in (1, 7):
            self.assertEqual(simulate(seed, "B_readable", "local", "baseline", 3),
                             run(seed, 3, variant="B_readable", profile="local"))

    def test_each_single_factor_intervention_is_reproducible(self):
        for arm in ARMS:
            self.assertEqual(simulate(7, "C_unreadable", "novice", arm, 3),
                             simulate(7, "C_unreadable", "novice", arm, 3))

    def test_study_does_not_assert_desired_success(self):
        data = analyze(2, 4)
        self.assertEqual(data["checks"]["weather_mismatches_across_paired_cases"], 0)
        self.assertEqual(data["design"]["cases_per_arm"], 2 * 3 * 2)
        self.assertEqual(set(data["arms"]), set(ARMS))
        self.assertIn("end_reasons", data["arms"]["baseline"])

    def test_patches_do_not_leak_into_the_real_gameplay(self):
        original = run(1, 3)
        start = World.load("district_v0", "B_readable").start_fuel
        original_burn = evening.FUEL_BURN_PER_H
        for arm in ARMS:
            simulate(1, "B_readable", "local", arm, 3)
        self.assertEqual(World.load("district_v0", "B_readable").start_fuel, start)
        self.assertEqual(evening.FUEL_BURN_PER_H, original_burn)
        self.assertEqual(run(1, 3), original)

    def test_auditor_alternatives_do_not_change_agent_history(self):
        trace = []
        with_probes = simulate(1, "B_readable", "local", "baseline", 3,
                               choice_trace=trace)
        without_probes = simulate(1, "B_readable", "local", "baseline", 3)
        self.assertEqual(len(trace), sum(
            d["evening"]["chose"] != "NOT_REACHED" for d in with_probes["history"]
        ))
        self.assertEqual(with_probes, without_probes)


if __name__ == "__main__":
    unittest.main()
