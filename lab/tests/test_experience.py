"""Tests for behavior audits, independent of any specific world implementation."""
import unittest
from dataclasses import dataclass

from lab.experience import audit, compare


@dataclass
class Day:
    day: int
    went_out: bool = False
    target: str | None = None
    carried: int = 0
    plan_changes: int = 0
    caught_in_storm: bool = False
    after_dark: bool = False
    crisis: bool = False
    cold_night: bool = False
    min_warmth: float = 100.0
    margin: float = 20.0
    return_error: float | None = None


class ExperienceTest(unittest.TestCase):
    def test_no_departures_is_not_mislabeled_as_boredom(self):
        a = audit([Day(1), Day(2), Day(3, cold_night=True)])
        self.assertEqual(a.longest_no_trip_streak, 3)
        self.assertEqual(a.trip_days, 0)
        self.assertIsNone(a.departure_error_first_half_min)
        self.assertEqual(a.cold_nights, 1)

    def test_detects_repeat_without_claiming_boredom(self):
        rows = [Day(1, True, "house_a", 1), Day(2, True, "house_a", 2),
                Day(3, True, "house_a", 1), Day(4, True, "house_b", 1)]
        a = audit(rows)
        self.assertEqual(a.unchallenged_repeat_target_days, 2)
        self.assertEqual(a.distinct_targets, 2)
        self.assertEqual(a.resource_return_days, 4)

    def test_pressure_and_replanning_are_separate(self):
        rows = [Day(1, True, "house_a", 1, caught_in_storm=True),
                Day(2, True, "house_a", 1, plan_changes=1, caught_in_storm=True),
                Day(3, True, "house_b", 0, plan_changes=1)]
        a = audit(rows)
        self.assertEqual(a.pressure_without_replan_days, 1)
        self.assertEqual(a.replanned_trip_days, 2)
        self.assertEqual(a.unchallenged_repeat_target_days, 0)

    def test_forecast_trend_needs_repeated_observations(self):
        rows = [Day(i, True, "house_a", 1, margin=50 - i * 5,
                    return_error=e) for i, e in enumerate([20, -10, 5, -3], start=1)]
        a = audit(rows)
        self.assertEqual(a.departure_error_first_half_min, 15)
        self.assertEqual(a.departure_error_second_half_min, 4)
        self.assertEqual(a.margin_first_trip_min, 45)
        self.assertEqual(a.margin_last_trip_min, 30)
        self.assertIsNone(audit(rows[:3]).departure_error_second_half_min)

    def test_storm_resets_unchallenged_repeat(self):
        rows = [Day(1, True, "house_a", 1), Day(2, True, "house_a", 1, caught_in_storm=True),
                Day(3, True, "house_a", 1), Day(4, True, "house_a", 1)]
        self.assertEqual(audit(rows).unchallenged_repeat_target_days, 1)

    def test_compare_rejects_empty_experiment(self):
        with self.assertRaises(ValueError):
            compare("district_v0", ["B_readable"], ["local"], 8, seeds=0)


if __name__ == "__main__":
    unittest.main()
