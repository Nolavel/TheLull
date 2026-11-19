import unittest

from lab.evening import (COOLING_RATE_C_PER_H, DEATH_C, HYPOTHERMIC_C, START_CORE_C, Body, Room,
                         sleep_refusal, step_body)
from lab.evening_run import OUTSIDE_C, compare, three_days


class ThermalTest(unittest.TestCase):
    def test_a_prepared_room_can_actually_rewarm_the_body(self):
        """Hoarbound's load-bearing lesson: without a reachable rewarm state the loop cannot close."""
        room = Room(fuel=10, fire_lit=True, heated_offset_c=12.0)
        body = Body(core_c=HYPOTHERMIC_C)
        for _ in range(8):  # two hours
            room.step(0.25)
            step_body(body, room, OUTSIDE_C, 0.25, asleep=True)
        self.assertGreater(body.core_c, HYPOTHERMIC_C)
        self.assertAlmostEqual(body.core_c, START_CORE_C, delta=0.6)  # doc: back to normal in about 2 h

    def test_core_temperature_never_runs_past_death(self):
        room, body = Room(fuel=0, fire_lit=False), Body()
        for _ in range(400):
            step_body(body, room, OUTSIDE_C, 0.25, asleep=True)
        self.assertGreaterEqual(body.core_c, DEATH_C)

    def test_room_keeps_its_warmth_a_while_after_the_fire_dies(self):
        room = Room(fuel=0.1, fire_lit=True, heated_offset_c=12.0)
        room.step(0.25)
        self.assertFalse(room.fire_lit)
        warm_right_after = room.heated_offset_c
        room.step(1.0)
        self.assertLess(room.heated_offset_c, warm_right_after)
        self.assertGreater(room.heated_offset_c, 0.0)  # not an instant switch to cold

    def test_fatigue_slows_breath_coming_back(self):
        self.assertGreater(Body(fatigue=0).stamina_recovery_per_h(), Body(fatigue=90).stamina_recovery_per_h())

    def test_sleep_is_refused_with_a_named_reason(self):
        cold = sleep_refusal(Room(fuel=0, fire_lit=False), Body(fatigue=50), OUTSIDE_C)
        self.assertEqual(cold, "слишком холодно, чтобы ложиться")
        rested = sleep_refusal(Room(fuel=5, fire_lit=True, heated_offset_c=12), Body(fatigue=5), OUTSIDE_C)
        self.assertEqual(rested, "ещё не устал настолько, чтобы заснуть")


class ChoiceTest(unittest.TestCase):
    def test_no_option_wins_on_every_axis(self):
        """If one option dominated, the evening would be a right answer, not a decision."""
        for cooling in (1.5, COOLING_RATE_C_PER_H, 6.0):
            self.assertIsNone(compare(OUTSIDE_C, cooling)["dominant_option"], f"cooling={cooling}")

    def test_last_night_is_felt_the_next_morning(self):
        days = three_days(OUTSIDE_C, COOLING_RATE_C_PER_H, 3)["days"]
        self.assertGreater(days[-1]["result"]["morning_fatigue"], days[0]["result"]["morning_fatigue"])

    def test_the_player_learns_fuel_burns_faster_than_it_thought(self):
        days = three_days(OUTSIDE_C, COOLING_RATE_C_PER_H, 3)["days"]
        self.assertTrue(any("расход топлива" in d["lesson"] for d in days))
        first = days[0]["considered"][0]["fire_hours_expected"]
        last = days[-1]["considered"][0]["fire_hours_expected"]
        self.assertLess(last, first)  # the estimate moved, and in the direction experience showed


if __name__ == "__main__":
    unittest.main()
