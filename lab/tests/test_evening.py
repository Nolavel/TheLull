import unittest

from lab.evening import (COOLING_RATE_C_PER_H, DEATH_C, HYPOTHERMIC_C, START_CORE_C, Body, Room,
                         sleep_refusal, step_body)
from lab.evening_run import fresh, play
from lab.evening_run import OUTSIDE_C, compare, sweep, three_days


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
    def test_the_sweep_finds_conditions_where_a_real_choice_exists(self):
        """Not an assumption that a choice always exists: a map of where it does."""
        res = sweep(COOLING_RATE_C_PER_H)
        kinds = {r["verdict"] for r in res["rows"]}
        self.assertIn("настоящий выбор", kinds)
        self.assertIn("одна вынужденная работа", kinds)  # too cold: one answer, not a decision
        self.assertGreater(res["cells_with_a_real_choice"], 0)

    def test_a_cell_called_a_real_choice_has_no_dominant_option(self):
        res = sweep(COOLING_RATE_C_PER_H)
        cell = next(r for r in res["rows"] if r["verdict"] == "настоящий выбор")
        detail = compare(cell["outside_c"], COOLING_RATE_C_PER_H, cell["start_fuel"])
        self.assertIsNone(detail["dominant_option"])
        self.assertGreater(len(detail["viable_options"]), 1)

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


class WakeFromColdTest(unittest.TestCase):
    """Author's rule, 19.11.2026: a cold night wakes the sleeper; it must not kill them in their sleep."""

    def test_a_bad_night_wakes_the_sleeper_instead_of_killing_them(self):
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=4)
        res = play("B: лечь раньше на том, что есть", -18.0, room, body, beliefs)
        self.assertGreater(res["woke_cold"], 0)
        self.assertGreater(res["morning_core_c"], DEATH_C)

    def test_waking_costs_sleep_and_leaves_a_problem_to_answer(self):
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=4)
        res = play("B: лечь раньше на том, что есть", -18.0, room, body, beliefs)
        self.assertGreater(res["awake_at_night_h"], 0.0)
        self.assertLess(res["slept_hours"], 8.0)
        self.assertTrue(res["wake_events"])
        self.assertTrue(all(w["core_c"] < 36.0 for w in res["wake_events"]))

    def test_with_nothing_left_to_burn_the_night_is_sat_out_awake(self):
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=4)
        room.furniture = 0
        res = play("B: лечь раньше на том, что есть", -18.0, room, body, beliefs)
        self.assertIn("нет доступного топлива", " ".join(w["did"] for w in res["wake_events"]))
        self.assertGreater(res["awake_at_night_h"], 0)  # interrupted rest, not automatic sleep

    def test_breaking_furniture_uses_it_up(self):
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=5)
        before = room.furniture
        play("A: разобрать мебель, топить дольше", -6.0, room, body, beliefs)
        self.assertLess(room.furniture, before)

class ToolAndBeliefTest(unittest.TestCase):
    def test_no_axe_cannot_convert_furniture_to_fuel(self):
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=1)
        room.has_axe = False
        with self.assertRaises(ValueError):
            play("A: разобрать мебель, топить дольше", -18, room, body, beliefs)
        play("B: лечь раньше на том, что есть", -18, room, body, beliefs)
        self.assertEqual(room.furniture, 2)

    def test_sealing_cannot_be_repeated_for_free(self):
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=5)
        play("C: утеплить комнату и лечь раньше", -6, room, body, beliefs)
        self.assertTrue(room.sealed)
        self.assertAlmostEqual(room.cooling_rate, COOLING_RATE_C_PER_H * 0.5)
        with self.assertRaises(ValueError):
            play("C: утеплить комнату и лечь раньше", -6, room, body, beliefs)

    def test_unavailable_actions_not_selected(self):
        from lab.evening import EXPEDITION, choose
        room, body, beliefs = fresh(COOLING_RATE_C_PER_H, fuel=5)
        room.has_axe = False
        room.sealed = True
        choice, _, _ = choose(body, room, beliefs, EXPEDITION, -18)
        self.assertTrue(choice["option"].startswith("B:"))

    def test_burn_rate_learning_is_bidirectional(self):
        from lab.evening import EveningBeliefs
        b = EveningBeliefs()
        b.observe_burn_rate(1.6)
        self.assertGreater(b.burn_rate_est, 1.0)
        b.observe_burn_rate(0.5)
        self.assertLess(b.burn_rate_est, 1.3)
        with self.assertRaises(ValueError):
            b.observe_burn_rate(0.0)

    def test_incomplete_fuel_step_not_full_hour_of_heating(self):
        room = Room(fuel=0.1, fire_lit=True, heated_offset_c=0.0)
        room.step(1.0)
        self.assertFalse(room.fire_lit)
        self.assertAlmostEqual(room.fuel, 0.0)
        self.assertLess(room.heated_offset_c, 1.0)
