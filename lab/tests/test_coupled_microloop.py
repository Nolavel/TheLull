"""Conservation and actual clothing benefit contracts for 2x2 coupling."""
import random
import unittest

from lab.body import Body, CLOTHING_INSULATION_C
from lab.coupled_microloop import (
    CONDITIONS, POLICIES, DRY, WATER, Equipment, _advance, run
)
from lab.coupled_mechanics_study import study
from lab.evening import Room, step_body
from lab.world import World


class CoupledGreyboxContract(unittest.TestCase):
    def test_three_clothing_advantages_on_identical_route(self):
        world = World.load("district_v0", "B_readable")
        weather = world.roll_weather(random.Random("7:weather:1"))
        edge = world.edge("home", "house_a")
        clock = world.dawn_min
        wind = weather.wind(clock)
        baseline_mins = world.travel_minutes(edge, clock, weather)
        observed = {}

        for wet in (0.0, 0.5, 1.0):
            gear = Equipment(wetness=wet)
            body = Body()
            room = Room(fuel=0)
            costs = {"stamina_demand":0.0,"extra_fatigue":0.0,"walked_h":0.0,
                     "minimum_stamina":body.stamina,"wet_pace_delay_min":0.0}
            target_minutes = gear.travel_minutes(
                baseline_mins, wind=wind, exposure=edge.exposure
            )
            billed = _advance(
                body, room, world, gear, target_minutes, at_home=False,
                weather=weather, exposure=edge.exposure,
                travelling=True, walking_costs=costs
            )
            self.assertAlmostEqual(billed, target_minutes, places=4)
            self.assertFalse(body.terminal)
            observed[wet] = (body.core_c, body.stamina, body.fatigue,
                             billed, gear.movement_stability(
                                 wind=wind, exposure=edge.exposure
                             ), costs["stamina_demand"])
        dry, half, wet = [observed[x] for x in (0, 0.5, 1)]
        self.assertGreater(dry[0],half[0])
        self.assertGreater(half[0],wet[0])
        self.assertGreater(dry[1],half[1])
        self.assertGreater(half[1],wet[1])
        self.assertLess(dry[2],half[2])
        self.assertLess(half[2],wet[2])
        self.assertLess(dry[3],half[3])
        self.assertLess(half[3],wet[3])
        self.assertGreater(dry[4],half[4])
        self.assertGreater(half[4],wet[4])
        self.assertLess(dry[5],half[5])
        self.assertLess(half[5],wet[5])
        self.assertLess(wet[3] / dry[3], 1.06)  # SMALL movement modifier
        self.assertAlmostEqual(dry[4],1.0)

    def test_drying_restores_all_three_benefits_without_a_buff(self):
        world = World.load("district_v0", "A_safe")
        gear = Equipment(wetness=1.0)
        body = Body()
        room = Room(fuel=2, fire_lit=True)
        self.assertGreater(gear.walk_stamina_per_h, Equipment().walk_stamina_per_h)
        _advance(body,room,world,gear,90,at_home=True,work=DRY)
        self.assertAlmostEqual(gear.wetness,0.0)
        self.assertAlmostEqual(gear.clothing_c,Equipment().clothing_c)
        self.assertAlmostEqual(gear.walk_stamina_per_h,Equipment().walk_stamina_per_h)
        self.assertAlmostEqual(
            gear.movement_stability(wind=1,exposure=1),1.0
        )
        self.assertAlmostEqual(room.burned_fuel_total,1.5,places=4)
        self.assertGreater(room.fuel,0)  # finite fuel left, no creation

    def test_no_fuel_means_no_automatic_clothing_repair(self):
        world = World.load("district_v0", "A_safe")
        body, room, gear = Body(), Room(fuel=0), Equipment(wetness=1.0)
        _advance(body,room,world,gear,30,at_home=True,work=DRY)
        self.assertEqual(gear.wetness,1.0)
        self.assertEqual(room.burned_fuel_total,0.0)
        self.assertLess(gear.movement_stability(),1.0)

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
