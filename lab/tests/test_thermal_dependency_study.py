"""The phase ledger and causal axes must not alter canonical gameplay."""
import unittest

from lab import body, evening, survival_loop
from lab.thermal_dependency_study import ARMS, PHASES, simulate, analyze


class ThermalDependencyStudyContract(unittest.TestCase):
    def test_control_is_actual_canonical_loop(self):
        for variant in ("B_readable", "C_unreadable"):
            expected = survival_loop.run(11, 4, variant=variant, profile="local")
            observed = simulate(11, variant, "local", "baseline", 4,
                                record=False)["story"]
            self.assertEqual(expected, observed)

    def test_observation_does_not_change_any_outcome(self):
        with_ledger = simulate(7, "B_readable", "local", "baseline", 4)
        without_ledger = simulate(7, "B_readable", "local", "baseline", 4,
                                  record=False)["story"]
        self.assertEqual(with_ledger["days"], without_ledger["days_completed"])
        self.assertAlmostEqual(with_ledger["last_core_c"],
                               without_ledger["history"][-1]["core_next_dawn"])
        self.assertLess(with_ledger["ledger_error"], 0.001)

    def test_thermal_ledger_only_tracks_actual_body(self):
        for arm in ARMS:
            trace = simulate(4, "C_unreadable", "novice", arm, 4)
            self.assertLess(trace["ledger_error"], 0.001, arm)
            self.assertTrue(all(trace["thermal_phases"][p]["h"] >= 0
                                for p in PHASES))
            self.assertEqual(len(trace["evening_options"]), trace["nights"])

    def test_weather_independent_and_patches_revert(self):
        first = survival_loop.run(5, 4, variant="B_readable", profile="local")
        burn = evening.FUEL_BURN_PER_H
        heat = evening.HEAT_SOURCE_OFFSET_C
        cooling = body.COOLING_COEF
        for arm in ARMS:
            a = simulate(5, "B_readable", "local", arm, 4)
            b = simulate(5, "B_readable", "local", arm, 4)
            self.assertEqual(a, b)
        self.assertEqual(evening.FUEL_BURN_PER_H, burn)
        self.assertEqual(evening.HEAT_SOURCE_OFFSET_C, heat)
        self.assertEqual(body.COOLING_COEF, cooling)
        self.assertEqual(survival_loop.run(5, 4, variant="B_readable",
                                          profile="local"), first)

    def test_pre_registered_study_not_success_tuned(self):
        report = analyze(seeds=2, days=4)
        self.assertEqual(report["design"]["cases_per_arm"], 12)
        self.assertEqual(set(report["by_variant"]["B_readable"]), set(ARMS))
        self.assertTrue(all(not n for n in report["checks"].values()),
                        report["checks"])
        # Under cold, every action can be poor. A fixed desired outcome
        # should never be encoded as a unit-test acceptance criterion.


if __name__ == "__main__":
    unittest.main()
