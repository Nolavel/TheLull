"""Controlled ignition times must be observable, billed and reproducible."""
import unittest

from lab.ignition_timing_study import experiment
from lab.survival_loop import HEATING_POLICIES, run


class IgnitionStudy(unittest.TestCase):
    def test_all_arms_are_reproducible(self):
        for policy in HEATING_POLICIES:
            self.assertEqual(
                run(5, 4, variant="B_readable", heating_policy=policy),
                run(5, 4, variant="B_readable", heating_policy=policy)
            )

    def test_default_equals_the_registered_dusk_control(self):
        for variant in ("A_safe", "B_readable", "C_unreadable"):
            self.assertEqual(run(2, 3, variant=variant),
                             run(2, 3, variant=variant, heating_policy="dusk"))

    def test_ignition_never_invents_fuel(self):
        result = experiment(seeds=2, days=4)
        self.assertEqual(result["design"]["cases_per_policy"], 12)
        self.assertTrue(all(x == 0 for x in result["checks"].values()), result["checks"])

    def test_no_future_weather_or_inventory_oracle(self):
        for policy in HEATING_POLICIES:
            result = run(4, 4, variant="C_unreadable", heating_policy=policy)
            events = [e for d in result["history"] for e in d["early_ignitions"]]
            for event in events:
                self.assertGreater(event["fuel_at_ignition"], 0)
                self.assertIn("core_at_ignition_c", event)

    def test_stop_in_room_cannot_auto_light_after_it(self):
        for policy in HEATING_POLICIES:
            result = run(9, 4, variant="C_unreadable", heating_policy=policy)
            if result["terminal_at_minute"] is not None:
                self.assertTrue(all(
                    e["elapsed_minute"] <= result["terminal_at_minute"]
                    for d in result["history"] for e in d["early_ignitions"]
                ))


if __name__ == "__main__":
    unittest.main()
