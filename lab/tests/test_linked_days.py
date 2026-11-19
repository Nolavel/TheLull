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
        self.assertTrue(all(v["choice"] in ("A", "B", "C") for v in r["by_intention"].values()))
        self.assertGreater(r["by_intention"][EXPEDITION.name]["expected_day_fatigue"],
                           r["by_intention"][SHORT_WALK.name]["expected_morning_fatigue"])

    def test_sweep_reports_negative_cases_without_inventing_differences(self):
        r = sweep_plans()
        self.assertEqual(r["cells"], 45)
        self.assertGreaterEqual(r["different_plan_changes_evening"], 0)
        self.assertLessEqual(r["different_plan_changes_evening"], 45)

    def test_cannot_use_negative_stock_or_invalid_wind(self):
        with self.assertRaises(ValueError):
            run_cycle([SHORT_WALK], depot_fuel=-1)
        with self.assertRaises(ValueError):
            do_next_day(SHORT_WALK, Body(), Room(), Depot(), wind=2.0)


if __name__ == "__main__":
    unittest.main()
