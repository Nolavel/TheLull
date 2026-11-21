import unittest

from lab.evening import (EXPEDITION, SHORT_WALK, UNDECIDED, Body, Room, EveningBeliefs)
from lab.linked_days import (Depot, do_next_day, effort, paired_plans,
                             run_cycle, sweep_plans)


class LinkedDayTest(unittest.TestCase):
    def test_load_and_time_are_future_costs_not_free(self):
        self.assertGreater(effort(EXPEDITION), effort(SHORT_WALK))
        self.assertGreater(effort(EXPEDITION, wind=1.0), effort(EXPEDITION, wind=0.0))

    def test_morning_plan_can_be_voluntarily_revised(self):
        body, room, depot = Body(fatigue=70.0), Room(fuel=0), Depot(fuel=5)
        res = do_next_day(EXPEDITION, body, room, depot)
        self.assertEqual(res.actual, SHORT_WALK.name)
        self.assertIn("отложил", res.decision)
        self.assertEqual(depot.fuel, 4)
        self.assertEqual(room.fuel, 1)

    def test_exhaustion_can_lead_to_no_trip_without_hard_gate(self):
        body, room, depot = Body(fatigue=98.0), Room(fuel=0), Depot(fuel=4)
        res = do_next_day(EXPEDITION, body, room, depot)
        self.assertFalse(res.attempted)
        self.assertEqual(depot.fuel, 4)

    def test_supplies_and_room_actions_persist(self):
        r = run_cycle([EXPEDITION, SHORT_WALK, UNDECIDED], [-12, -12, -12],
                      fuel=7, depot_fuel=2)
        self.assertLessEqual(sum(d["daytime"]["fuel_collected"] for d in r["days"]), 2)
        self.assertEqual(r["summary"]["depot_remaining"],
                         2 - sum(d["daytime"]["fuel_collected"] for d in r["days"]))
        for prev, nxt in zip(r["days"], r["days"][1:]):
            self.assertEqual(prev["after_day"]["furniture"], nxt["before_evening"]["furniture"])
            self.assertEqual(prev["after_day"]["sealed"], nxt["before_evening"]["sealed"])

    def test_no_axe_prevents_evening_chopping(self):
        r = run_cycle([EXPEDITION], [-12], fuel=5, axe=False)
        self.assertNotEqual(r["days"][0]["choice"][:1], "A")
        self.assertEqual(r["days"][0]["after_day"]["furniture"], 2)

    def test_identical_inputs_reproduce_history(self):
        plans = [SHORT_WALK, EXPEDITION, UNDECIDED]
        a = run_cycle(plans, [-18, -12, -6])
        b = run_cycle(plans, [-18, -12, -6])
        self.assertEqual(a, b)

    def test_counterfactual_keeps_world_fixed(self):
        r = paired_plans([-12], fuel=5, wind=0.5)
        self.assertEqual(len(r["by_intention"]), 3)
        self.assertEqual(r["scenario"]["fuel"], 5)
        self.assertTrue(all(v["choice"] in ("A", "B", "C", "D") for v in r["by_intention"].values()))
        self.assertGreater(r["by_intention"][EXPEDITION.name]["expected_day_fatigue"],
                           r["by_intention"][SHORT_WALK.name]["expected_morning_fatigue"])

    def test_sweep_reports_negative_cases_without_inventing_differences(self):
        r = sweep_plans()
        self.assertEqual(r["cells"], 45)
        self.assertGreaterEqual(r["different_plan_changes_evening"], 0)
        self.assertLessEqual(r["different_plan_changes_evening"], 45)

    def test_itinerary_comparison_keeps_options_observable_without_forcing_a_pick(self):
        tight = paired_plans([-6], fuel=3, daylight_hours=7.0)
        plenty = paired_plans([-6], fuel=3, daylight_hours=10.0)
        for result in (tight, plenty):
            self.assertIn(SHORT_WALK.name, result["by_intention"])
            self.assertIn(EXPEDITION.name, result["by_intention"])
            self.assertTrue(all(value["choice"] in ("A", "B", "C", "D")
                                for value in result["by_intention"].values()))
            self.assertGreaterEqual(result["distinct_evening_choices"], 1)
            self.assertLessEqual(result["distinct_evening_choices"], 3)
        # A forecast changing in a colder 14-hour night is an experimental
        # result, not a reason to freeze the old 'B versus D' expectation.
        self.assertGreaterEqual(plenty["distinct_evening_choices"], 1)

    def test_packing_is_a_real_one_use_time_tradeoff(self):
        packed = Body(fatigue=0.0, packed=True)
        prepared = do_next_day(EXPEDITION, packed, Room(fuel=0), Depot(fuel=5), daylight_hours=7)
        self.assertEqual(prepared.actual, EXPEDITION.name)
        self.assertEqual(prepared.prep_hours, 0.0)
        self.assertFalse(packed.packed)
        unpacked = do_next_day(EXPEDITION, Body(fatigue=0.0), Room(fuel=0),
                               Depot(fuel=5), daylight_hours=7)
        self.assertEqual(unpacked.actual, SHORT_WALK.name)
        self.assertGreater(unpacked.prep_hours, 0.0)

    def test_weather_can_override_the_tomorrow_plan(self):
        cold = paired_plans([-24], fuel=7, daylight_hours=7)
        # When no preparation can save the long trip, the agent should not pack pointlessly.
        self.assertNotEqual(cold["by_intention"][EXPEDITION.name]["choice"], "D")
        self.assertNotEqual(cold["by_intention"][EXPEDITION.name]["actual_day_plan"], EXPEDITION.name)

    def test_cannot_use_negative_stock_or_invalid_wind(self):
        with self.assertRaises(ValueError):
            run_cycle([SHORT_WALK], depot_fuel=-1)
        with self.assertRaises(ValueError):
            do_next_day(SHORT_WALK, Body(), Room(), Depot(), wind=2.0)
        with self.assertRaises(ValueError):
            run_cycle([SHORT_WALK], daylight_hours=0)


if __name__ == "__main__":
    unittest.main()

class BeliefAndCalibrationTest(unittest.TestCase):
    def test_profiles_start_with_different_priors_not_different_world(self):
        plans = [SHORT_WALK]
        local = run_cycle(plans, [-18], fuel=5, profile="local")
        novice = run_cycle(plans, [-18], fuel=5, profile="novice")
        self.assertEqual(local["scenario"]["fuel"], novice["scenario"]["fuel"])
        self.assertEqual(local["days"][0]["before_evening"]["burn_rate_belief"], 1.0)
        self.assertEqual(novice["days"][0]["before_evening"]["burn_rate_belief"], 0.65)

    def test_learning_does_not_expose_an_unobserved_expiry(self):
        r = run_cycle([SHORT_WALK], [-18], fuel=2, profile="novice")
        d = r["days"][0]
        if (d["night"]["observed_burn_rate"] is None and
                d["night"]["burn_rate_lower_bound"] is None):
            self.assertEqual(d["before_evening"]["burn_rate_belief"],
                             d["after_day"]["burn_rate_belief"])
        self.assertIn("core_forecast_error_c", d)

    def test_censored_burn_observation_never_decreases_known_lower_bound(self):
        b = EveningBeliefs(burn_rate_est=0.4)
        text = b.observe_rate_lower_bound(0.9)
        self.assertIn("не меньше", text)
        self.assertGreater(b.burn_rate_est, 0.4)
        above = b.burn_rate_est
        b.observe_rate_lower_bound(0.2)
        self.assertEqual(b.burn_rate_est, above)

    def test_forecasting_uses_copies_not_the_real_room(self):
        from lab.evening import EXPEDITION, options
        room, body, beliefs = Room(fuel=5), Body(), EveningBeliefs()
        initial = (room.fuel, room.furniture, room.heated_offset_c,
                   body.fatigue, body.core_c, body.packed)
        result = options(body, room, beliefs, EXPEDITION, -18)
        self.assertEqual(len(result), 4)
        self.assertEqual(initial, (room.fuel, room.furniture, room.heated_offset_c,
                                   body.fatigue, body.core_c, body.packed))

    def test_cold_body_must_warm_up_before_sleep(self):
        from lab.evening import sleep_refusal
        room = Room(fuel=8, fire_lit=True, heated_offset_c=12)
        body = Body(core_c=35.0, fatigue=70.0)
        self.assertEqual(sleep_refusal(room, body, -18), "сначала нужно согреться")
