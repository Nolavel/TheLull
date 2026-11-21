"""D1.6: actor error comes from prior prediction and observed return only."""
import unittest

from lab.agent import Agent
from lab.body import Body
from lab.clothing_adaptation_study import choose_clothing, make_world
from lab.coupled_microloop import Equipment
from lab.evening import Room
from lab.forecast_error_study import ROUTE_ID, evaluate_case, study


class ErrorMemoryContracts(unittest.TestCase):
    def test_signed_error_stores_bad_and_good_surprise(self):
        a=Agent("novice",make_world("A_safe",8)).beliefs
        msg=a.observe_trip_prediction(
            ROUTE_ID, predicted_minutes=100,actual_minutes=140,
            predicted_stamina_demand=25,actual_stamina_demand=18,
            predicted_core_loss=2,actual_core_loss=3,
        )
        e=a.trip_prediction_errors[ROUTE_ID]
        self.assertEqual(e["minutes"],40)
        self.assertEqual(e["stamina"],-7)
        self.assertEqual(e["core"],1)
        self.assertIn("ошибка",msg)
        self.assertEqual(e["samples"],1)
        a.observe_trip_prediction(
            ROUTE_ID, predicted_minutes=140,actual_minutes=100,
            predicted_stamina_demand=18,actual_stamina_demand=20,
            predicted_core_loss=3,actual_core_loss=1,
        )
        self.assertEqual(a.trip_prediction_errors[ROUTE_ID]["minutes"],-40)
        self.assertEqual(a.trip_prediction_errors[ROUTE_ID]["samples"],2)

    def test_invalid_observation_does_not_change_memory(self):
        a=Agent("local",make_world("A_safe",1)).beliefs
        for value in (float("nan"),float("inf"),-1):
            with self.assertRaises(ValueError):
                a.observe_trip_prediction(
                    ROUTE_ID,predicted_minutes=10,actual_minutes=value,
                    predicted_stamina_demand=1,actual_stamina_demand=2,
                    predicted_core_loss=1,actual_core_loss=2,
                )
        self.assertFalse(a.trip_prediction_errors)

    def test_opt_in_policy_does_not_demand_suspicious_benefit(self):
        world=make_world("A_safe",1)
        actor=Agent("local",world)
        state=(Body(),Room(fuel=world.start_fuel),Equipment(wetness=1))
        untouched=choose_clothing(actor,*state)
        empty=choose_clothing(actor,*state,consider_prediction_error=True)
        self.assertEqual(untouched.choice,empty.choice)
        actor.beliefs.observe_trip_prediction(
            ROUTE_ID,predicted_minutes=10,actual_minutes=5,
            predicted_stamina_demand=10,actual_stamina_demand=5,
            predicted_core_loss=3,actual_core_loss=1,
        )
        better=choose_clothing(actor,*state,consider_prediction_error=True)
        self.assertEqual(untouched.choice,better.choice)
        self.assertIn("добавочная страховка",better.reason)
        self.assertIn("0.00",better.reason)

    def test_complete_trip_precommits_forecast_then_observes_own_cost(self):
        r=evaluate_case(3,"A_safe",1,"local")
        self.assertTrue(r["eligible"])
        self.assertTrue(r["prediction"]["measured_before_training"])
        self.assertAlmostEqual(
            r["signed_error"]["travel_minutes"],
            r["observation"]["travel_minutes"]-r["prediction"]["travel_minutes"],
        )
        self.assertAlmostEqual(
            r["signed_error"]["stamina_demand"],
            r["observation"]["stamina_demand"]-r["prediction"]["stamina_demand"],
        )
        self.assertAlmostEqual(
            r["signed_error"]["core_loss"],
            r["observation"]["core_loss"]-r["prediction"]["core_loss"],
        )
        self.assertEqual(r["heldout"]["seed"],10003)
        self.assertEqual(set(r["decisions"]),{"prior","ema","error"})

    def test_terminal_training_is_never_taught_as_completed_route(self):
        # C×40 failed in D1.4 for each seed — avoid falsely learning a
        # complete route from a terminal *partial* trip.
        r=evaluate_case(2,"C_unreadable",40,"novice")
        self.assertFalse(r["eligible"])
        self.assertIsNone(r["decisions"])
        self.assertIsNone(r["observed_error"])
        self.assertIsNone(r["heldout"])

    def test_same_case_reproducible_with_matched_second_weather(self):
        a=evaluate_case(18,"B_readable",24,"novice")
        b=evaluate_case(18,"B_readable",24,"novice")
        self.assertEqual(a,b)
        self.assertEqual(a["heldout"]["seed"],10018)

    def test_small_paired_audit_has_no_hardwired_positive_result(self):
        a=study(seeds=2)
        self.assertEqual(a["design"]["cases"],48)
        self.assertEqual(a["design"]["human_participants"],0)
        self.assertEqual(a["checks"],{name:0 for name in a["checks"]})
        n=a["counts"]["observed_full_training"]
        self.assertEqual(a["policy_outcomes_heldout"]["prior"]["trials"],n)
        self.assertEqual(a["policy_outcomes_heldout"]["ema"]["trials"],n)
        self.assertEqual(a["policy_outcomes_heldout"]["error"]["trials"],n)


if __name__=="__main__":
    unittest.main()
