"""D1.5 contracts: observed route beliefs and stamina-dependent follow-up task."""
import unittest

from lab.agent import Agent
from lab.body import Body
from lab.clothing_adaptation_study import (
    analyse_case, choose_clothing, make_world, study,
)
from lab.clothing_followthrough import WORK_START_STAMINA, followup_work
from lab.coupled_microloop import Equipment, DRY, EXPLORE
from lab.evening import Room


class BodyFollowthrough(unittest.TestCase):
    def test_tired_worker_may_defer_or_recover_at_real_cost(self):
        world=make_world("A_safe",1)
        body=Body(core_c=36.5,stamina=40)
        room=Room(fuel=1)
        defer=followup_work(body,room,world,rest_if_tired=False)
        self.assertEqual(defer["choice"],"defer")
        self.assertEqual(defer["total_minutes"],0)
        self.assertAlmostEqual(body.stamina,40)
        self.assertAlmostEqual(body.elapsed_minutes,0)
        action=followup_work(body,room,world,rest_if_tired=True)
        self.assertGreater(action["rest_minutes"],0)
        self.assertTrue(action["completed"])
        self.assertEqual(action["work_minutes"],60)
        self.assertAlmostEqual(body.elapsed_minutes,action["total_minutes"])
        self.assertGreaterEqual(body.stamina,0)
        self.assertLessEqual(body.stamina,100)

    def test_rest_is_not_required_if_stamina_sufficient(self):
        world=make_world("A_safe",1)
        body=Body(stamina=75)
        r=followup_work(body,Room(fuel=0),world)
        self.assertEqual(r["choice"],"work_now")
        self.assertEqual(r["rest_minutes"],0)
        self.assertTrue(r["completed"])
        self.assertAlmostEqual(body.elapsed_minutes,60)
        self.assertAlmostEqual(body.stamina,55.0)
        self.assertGreater(body.fatigue,0)

    def test_post_trip_work_preserves_wet_thermal_penalty(self):
        world=make_world("B_readable",1)
        def work(wet):
            body=Body(core_c=37,stamina=90)
            room=Room(fuel=0)
            result=followup_work(body,room,world,gear=Equipment(wetness=wet))
            self.assertTrue(result["completed"])
            self.assertAlmostEqual(body.elapsed_minutes,60)
            return body.core_c
        self.assertGreater(work(0),work(1))

    def test_terminal_body_has_no_future_actions(self):
        world=make_world("C_unreadable",1)
        body=Body(core_c=28.8,stamina=100)
        r=followup_work(body,Room(fuel=5),world)
        self.assertFalse(r["completed"])
        self.assertEqual(r["total_minutes"],0)
        self.assertTrue(body.terminal)


class ClothingBeliefAndChoice(unittest.TestCase):
    def test_short_trip_is_worth_leaving_while_long_trip_can_warrant_drying(self):
        for multiplier,expected in ((1,EXPLORE),(40,DRY)):
            world=make_world("A_safe",multiplier)
            agent=Agent("local",world)
            d=choose_clothing(agent,Body(),Room(fuel=world.start_fuel),
                              Equipment(wetness=1.0))
            self.assertEqual(d.choice,expected)
            self.assertEqual(len(d.alternatives),2)
            self.assertTrue(all(x["available"] for x in d.alternatives))

    def test_outcome_only_updates_own_beliefs_not_counterfactual(self):
        world=make_world("A_safe",24)
        agent=Agent("novice",world)
        prior=agent.path("home","house_a")[0]
        a=agent.beliefs
        self.assertEqual(a.wet_walk_samples,0)
        obs=a.observe_wet_walk(hours=2.0,stamina_demand=33,
                               core_before=37.0,core_after=35.0)
        self.assertIn("пережитая",obs)
        self.assertEqual(a.wet_walk_samples,1)
        self.assertNotEqual(a.wet_walk_stamina_per_h_est,16.0)
        agent.observe_edge("home","house_a",False,prior*1.5)
        self.assertGreater(agent.path("home","house_a")[0],prior)
        # No observed dry outcome: the agent does not gain perfect
        # foreknowledge of dry-specific physics.
        self.assertFalse(hasattr(a,"dry_counterfactual_return_probability"))

    def test_followup_is_stamina_sensitive_on_same_recorded_trip(self):
        r=analyse_case(1,"A_safe",40,profile="local")
        a=r["post_trip_second_action"]
        self.assertTrue(a["prepared_all"]["possible"])
        self.assertTrue(a["prepared_no_stamina"]["possible"])
        self.assertGreaterEqual(a["prepared_no_stamina"]["rest_or_work"]["rest_minutes"],
                                a["prepared_all"]["rest_or_work"]["rest_minutes"])
        self.assertEqual(a["prepared_all"]["state_before"]["elapsed_minutes"] +
                         a["prepared_all"]["rest_or_work"]["total_minutes"],
                         a["prepared_all"]["state_after"]["elapsed_minutes"])

    def test_fixed_case_and_paired_study_reproducible(self):
        self.assertEqual(analyse_case(2,"B_readable",8,"novice"),
                         analyse_case(2,"B_readable",8,"novice"))
        report=study(seeds=2)
        self.assertEqual(report["design"]["cases"],48)
        self.assertTrue(all(v==0 for v in report["checks"].values()),report["checks"])
        self.assertGreater(report["counts"].get("learned_from_real_return",0),0)
        self.assertTrue(report["design"]["simulated_agent_only"])


if __name__=="__main__":
    unittest.main()
