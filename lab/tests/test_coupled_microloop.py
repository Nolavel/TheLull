"""Conservation contracts for a single real physical clock and 2x2 coupling."""
import unittest

from lab.body import Body, CLOTHING_INSULATION_C
from lab.coupled_microloop import (CONDITIONS, POLICIES, DRY, WATER,
                                   Equipment, run)
from lab.coupled_mechanics_study import study
from lab.evening import Room, step_body


class CoupledGreyboxContract(unittest.TestCase):
    def test_dry_default_is_unchanged_and_wet_body_loses_more_heat(self):
        a=Body()
        b=Body()
        room_a=Room(fuel=0)
        room_b=Room(fuel=0)
        room_a.step(.25)
        room_b.step(.25)
        step_body(a,room_a,-12,.25,False,clothing_c=CLOTHING_INSULATION_C)
        step_body(b,room_b,-12,.25,False,clothing_c=Equipment(wetness=1).clothing_c)
        self.assertLess(b.core_c,a.core_c)

    def test_all_four_conditions_are_reproducible(self):
        for wet,water in CONDITIONS:
            for policy in POLICIES:
                r=run(5,"A_safe","local",wet=wet,need_water=water,policy=policy)
                self.assertEqual(r,run(5,"A_safe","local",wet=wet,
                                       need_water=water,policy=policy))
                self.assertLessEqual(r["elapsed_minutes"],1440.00001)
                self.assertGreater(r["elapsed_minutes"],0)
                self.assertEqual(r["raw_water_left"]+r["safe_water_final"],int(water))
                self.assertGreaterEqual(r["fuel_final"],0)
                self.assertLessEqual(
                    r["fuel_final"]+r["fuel_burned"],
                    r["initial_fuel"]+r["delivered"]+.002
                )

    def test_scenario_factors_are_not_free_resources(self):
        for wet,water in CONDITIONS:
            r=run(1,"A_safe","local",wet=wet,need_water=water,policy="agent")
            self.assertEqual(r["loot_before"]-r["loot_after"],r["found"])
            self.assertLessEqual(r["delivered"],r["found"])
            if not wet:
                self.assertEqual(r["wet_final"],0)
            if not water:
                self.assertEqual(r["safe_water_final"],0)
            for d in r["decisions"]:
                self.assertIn(d["choice"],{o["option"] for o in d["alternatives"]
                                           if o["available"]})
                self.assertTrue(d["intention"] and d["reason"] and d["outcome"])

    def test_controlled_pairing_has_zero_physical_violations(self):
        r=study(seeds=2)
        self.assertEqual(r["design"]["blocks"],12)
        self.assertEqual(r["design"]["runs"],192)
        self.assertTrue(all(v==0 for v in r["checks"].values()),r["checks"])

    def test_real_optional_human_action_is_checked(self):
        chosen=[]
        def chooser(d):
            available=[x["option"] for x in d.alternatives if x["available"]]
            chosen.append(available)
            return available[0]
        r=run(1,"A_safe","local",wet=True,need_water=True,
              provider=chooser)
        self.assertEqual(r["participant_source"],"human")
        self.assertTrue(chosen)
        with self.assertRaises(ValueError):
            run(1,"A_safe","local",wet=True,need_water=True,
                provider=lambda _: "телепорт")

    def test_cli_questionnaire_is_instrumented_without_live_participant(self):
        from lab.coupled_playtest import run_session
        prompts=[]
        def mock_answer(prompt):
            prompts.append(prompt)
            return "1" if "номер" in prompt else "изучить последствия"
        result=run_session(1,"A_safe",wet=True,need_water=True,
                           ask=mock_answer,show=lambda _:None)
        self.assertTrue(result["human_choice_notes"])
        self.assertEqual(result["human_story"]["participant_source"],"human")
        self.assertIn("own_next_intention",result["interview"])
        self.assertTrue(any("Почему" in x for x in prompts))
        self.assertEqual(result["same_seed_agent_story"]["participant_source"],
                         "simulated_agent")

    def test_no_claim_that_agent_predicted_human_fun(self):
        r=study(seeds=1)
        self.assertIn("fun", " ".join(r["limits"]))
        self.assertEqual(r["design"]["source"].count("human participants=0"),1)


if __name__=="__main__":
    unittest.main()
