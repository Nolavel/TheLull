"""Drying payoff: measurable opportunity cost vs independent thermal/stamina/pace channels."""
import unittest

from lab.clothing_payoff_study import ARMS, DISTANCE_MULTIPLIERS, evaluate, study


class PreparationPayoffContracts(unittest.TestCase):
    def test_same_departure_means_comparable_ablations(self):
        for variant in ("A_safe","B_readable","C_unreadable"):
            for length in (1,24):
                r=evaluate(3,variant,length)["arms"]
                self.assertEqual(set(r),set(ARMS))
                prepared=r["prepared_all"]
                heated=r["heated_wet"]
                self.assertAlmostEqual(prepared["departure_minute"],90,places=3)
                self.assertAlmostEqual(prepared["departure_minute"],heated["departure_minute"])
                for name in ARMS[2:]:
                    row=r[name]
                    self.assertAlmostEqual(row["departure_minute"],prepared["departure_minute"])
                    self.assertAlmostEqual(row["fuel_at_departure"],prepared["fuel_at_departure"])
                    self.assertAlmostEqual(row["core_at_departure"],prepared["core_at_departure"])
                    self.assertAlmostEqual(row["stamina_at_departure"],prepared["stamina_at_departure"])
                    self.assertEqual(row["wetness_after_preparation"],0)
                self.assertEqual(heated["wetness_after_preparation"],1)
                self.assertEqual(r["wet_now"]["wetness_after_preparation"],1)

    def test_triangular_physics_not_just_thermal(self):
        data=evaluate(2,"A_safe",1)["arms"]
        full=data["prepared_all"]
        self.assertTrue(full["completed_return"])
        self.assertTrue(data["heated_wet"]["completed_return"])
        # Same physical preparation; only one channel changed per arm.
        self.assertGreater(full["core_after_route"],
                           data["prepared_no_thermal"]["core_after_route"])
        self.assertGreater(full["stamina_after_route"],
                           data["prepared_no_stamina"]["stamina_after_route"])
        self.assertLess(full["travel_minutes"],
                        data["prepared_no_movement"]["travel_minutes"])
        self.assertGreater(full["stamina_after_route"],
                           data["prepared_heat_only"]["stamina_after_route"])
        self.assertLess(full["travel_minutes"],
                        data["prepared_heat_only"]["travel_minutes"])

    def test_drying_does_not_dominate_short_walk_time_and_fuel(self):
        data=evaluate(2,"A_safe",1)["arms"]
        wet=data["wet_now"]
        dry=data["prepared_all"]
        self.assertLess(wet["elapsed_minutes"],dry["elapsed_minutes"])
        self.assertGreater(wet["fuel_remaining"],dry["fuel_remaining"])
        self.assertGreater(dry["core_after_route"],wet["core_after_route"])
        self.assertGreater(dry["stamina_after_route"],wet["stamina_after_route"])

    def test_deterministic_and_finite(self):
        self.assertEqual(evaluate(5,"B_readable",8),evaluate(5,"B_readable",8))
        r=study(seeds=2)
        self.assertEqual(r["design"]["cases"],24)
        self.assertEqual(r["design"]["runs"],168)
        self.assertTrue(all(v==0 for v in r["checks"].values()),r["checks"])
        self.assertGreater(r["observations"]["paired_complete"],0)

    def test_real_actor_does_not_receive_unearned_future_knowledge(self):
        r=study(seeds=1)
        # Same '2h imagined route' decision for each route length is the
        # uncorrected agent weakness to measure, NOT assumed learning.
        for variant in ("A_safe","B_readable","C_unreadable"):
            choices=[r["by_world_distance"][variant][str(length)]["agent_morning_choice"]
                     for length in DISTANCE_MULTIPLIERS]
            self.assertEqual(len(set(choices)),1)
        self.assertTrue(r["design"]["no_human_participants"])


if __name__=="__main__":
    unittest.main()
