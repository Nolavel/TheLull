"""D1.7: causal attribution must be evidence-conditional, not an oracle."""
import unittest

from lab.agent import Agent
from lab.clothing_adaptation_study import make_world
from lab.contextual_intent_study import (
    PATTERNS, WAIT, choose_next, observed_legs_cue, run_case,
    study, wait_and_walk, weather_for,
)
from lab.clothing_payoff_study import evaluate
from lab.coupled_microloop import DRY, EXPLORE


class ContextualTripEvidence(unittest.TestCase):
    def setUp(self):
        self.world=make_world("A_safe",8)
        self.actor=Agent("local",self.world)
        self.b=self.actor.beliefs
        self.route="home→house_a→home"

    def observe(self,cue,actual_m,actual_core=1.5):
        self.b.observe_contextual_trip(
            self.route,weather_cue=cue,
            predicted_minutes=60,actual_minutes=actual_m,
            predicted_stamina=15,actual_stamina=20,
            predicted_core=1,actual_core=actual_core,
        )

    def test_one_storm_is_not_a_permanent_calm_route_tax(self):
        self.observe("calm",60,1.0)
        self.observe("calm",60,1.0)
        before=self.b.contextual_assessment(self.route,current_cue="calm")
        self.observe("storm",180,4.0)
        after=self.b.contextual_assessment(self.route,current_cue="calm")
        self.assertEqual(before["bonus"],after["bonus"])
        self.assertEqual(after["matching_samples"],2)
        self.assertEqual(after["other_weather_samples"],1)
        self.assertGreater(self.b.contextual_assessment(
            self.route,current_cue="storm")["bonus"],0)

    def test_repeated_unexpected_calm_cost_is_retained(self):
        for _ in range(3):
            self.observe("calm",95,2.0)
        x=self.b.contextual_assessment(self.route,current_cue="calm")
        self.assertGreater(x["bonus"],0)
        self.assertEqual(x["attribution"],"repeatable_calm_route_underestimate")
        self.assertEqual(x["matching_samples"],3)

    def test_good_surprises_have_negative_not_forced_dry_risk(self):
        for _ in range(3):
            self.b.observe_contextual_trip(
                self.route,weather_cue="calm",
                predicted_minutes=120,actual_minutes=70,
                predicted_stamina=30,actual_stamina=15,
                predicted_core=3,actual_core=1,
            )
        x=self.b.contextual_assessment(self.route,current_cue="calm")
        self.assertLess(x["bonus"],0)
        self.assertEqual(x["attribution"],"cost_not_underestimated")

    def test_no_oracle_weather_context(self):
        self.assertRaises(ValueError,self.b.contextual_assessment,
                          self.route,current_cue="future_unknown")
        self.assertRaises(ValueError,self.b.observe_contextual_trip,
                          self.route,weather_cue="future",
                          predicted_minutes=10,actual_minutes=20,
                          predicted_stamina=10,actual_stamina=20,
                          predicted_core=1,actual_core=2)
        self.assertFalse(self.b.contextual_trip_history)


class ContextualExperiment(unittest.TestCase):
    def test_wind_observed_on_actual_legs_not_future_schedule(self):
        world=make_world("B_readable",8)
        calm=weather_for(world,"calm",1)
        storm=weather_for(world,"storm",1)
        a=evaluate(1,"B_readable",8,weather_override=calm)
        b=evaluate(1,"B_readable",8,weather_override=storm)
        self.assertEqual(observed_legs_cue(world,calm,a["arms"]["wet_now"]),"calm")
        self.assertEqual(observed_legs_cue(world,storm,b["arms"]["wet_now"]),"storm")
        self.assertLess(a["arms"]["wet_now"]["travel_minutes"],
                        b["arms"]["wet_now"]["travel_minutes"])

    def test_wait_has_real_price_and_no_fuel_creation(self):
        variant="B_readable"
        world=make_world(variant,8)
        weather=weather_for(world,"storm",1)
        immediate=evaluate(1,variant,8,weather_override=weather)["arms"]["wet_now"]
        waiting=wait_and_walk(1,variant,8,weather)
        self.assertGreater(waiting["elapsed_minutes"],immediate["elapsed_minutes"])
        self.assertEqual(waiting["fuel_burned"],0)
        self.assertEqual(waiting["fuel_remaining"],world.start_fuel)

    def test_wait_requires_observed_storm_and_local_knowledge(self):
        world=make_world("A_safe",24)
        for profile in ("local","novice"):
            a=Agent(profile,world)
            a.beliefs.observe_contextual_trip(
                "home→house_a→home",weather_cue="storm",
                predicted_minutes=40,actual_minutes=120,
                predicted_stamina=10,actual_stamina=30,
                predicted_core=1,actual_core=4)
            a.beliefs.observe_contextual_trip(
                "home→house_a→home",weather_cue="storm",
                predicted_minutes=40,actual_minutes=120,
                predicted_stamina=10,actual_stamina=30,
                predicted_core=1,actual_core=4)
            a.beliefs.observe_contextual_trip(
                "home→house_a→home",weather_cue="calm",
                predicted_minutes=40,actual_minutes=41,
                predicted_stamina=10,actual_stamina=11,
                predicted_core=1,actual_core=1)
            if profile=="novice":
                self.assertNotEqual(choose_next(a,world,cue="storm",
                                                 mode="causal_wait")["choice"],WAIT)
            self.assertNotEqual(choose_next(a,world,cue="calm",
                                             mode="causal_wait")["choice"],WAIT)

    def test_case_deterministic_and_all_policies_have_real_alternatives(self):
        a=run_case(2,"A_safe","novice",8,"late_storm_spike")
        self.assertEqual(a,run_case(2,"A_safe","novice",8,"late_storm_spike"))
        self.assertEqual(len(a["history"]),3)
        self.assertEqual(set(a["decisions"]),
                         {"ema","last_error","contextual","causal_wait"})
        for decision in a["decisions"].values():
            self.assertEqual(len(decision["alternatives"]),3)
            self.assertIn(decision["choice"],[p["option"] for p in
                          decision["alternatives"] if p["available"]])
        self.assertEqual(a["next_current_observed_cue"],"calm")
        self.assertTrue(a["heldout"]["seed"]==10002)

    def test_small_study_preserves_negative_results_without_forcing(self):
        r=study(seeds=1)
        self.assertEqual(r["design"]["cases"],len(PATTERNS)*3*2*4)
        self.assertEqual(r["design"]["human_participants"],0)
        self.assertEqual(r["checks"],{key:0 for key in r["checks"]})
        for c in r["policy_outcomes"].values():
            self.assertEqual(c["trials"],r["design"]["cases"])


if __name__=="__main__":
    unittest.main()
