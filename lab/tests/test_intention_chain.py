"""End-to-end instrumented night->dawn links and optional clothing preparation."""
import random
import unittest

from lab.body import Body, CLOTHING_INSULATION_C
from lab.coupled_microloop import (
    DRY, WATER, EXPLORE, Equipment, _advance, _intention, run as coupled_run,
)
from lab.evening import Room
from lab.intention_chain_study import analyze
from lab.sim import run_day
from lab.survival_loop import run
from lab.world import World


class DryClothingAdvantage(unittest.TestCase):
    def test_wetness_is_not_an_obligatory_goal(self):
        gear=Equipment(wetness=1.0,raw_water=1)
        person=Body()
        room=Room(fuel=4)
        self.assertNotIn("просушить",_intention(gear,room,person))
        self.assertLess(gear.clothing_c,CLOTHING_INSULATION_C)
        # Wet clothing matters physically even when no decision forces drying.
        trace=coupled_run(3,"A_safe",wet=True,need_water=True,policy="agent")
        self.assertNotEqual(trace["next_intention_rule_based"],"просушить одежду")

    def test_drying_costs_fire_time_and_restores_protection(self):
        world=World.load("district_v0","A_safe")
        person=Body()
        room=Room(fuel=3,fire_lit=True)
        gear=Equipment(wetness=1.0)
        before=room.fuel
        used=_advance(person,room,world,gear,90,at_home=True,work=DRY)
        self.assertAlmostEqual(used,90)
        self.assertAlmostEqual(gear.wetness,0,places=6)
        self.assertAlmostEqual(gear.clothing_c,CLOTHING_INSULATION_C)
        self.assertAlmostEqual(before-room.fuel,1.5,places=4)
        self.assertAlmostEqual(gear.drying_hours,1.5)
        self.assertGreater(gear.clothing_c,Equipment(wetness=1).clothing_c)

    def test_without_fire_drying_does_not_magically_work(self):
        world=World.load("district_v0","A_safe")
        body=Body()
        room=Room(fuel=0,fire_lit=False)
        gear=Equipment(wetness=1.0)
        _advance(body,room,world,gear,30,at_home=True,work=DRY)
        self.assertEqual(gear.wetness,1.0)
        self.assertEqual(gear.drying_hours,0)

    def test_dry_clothes_cool_less_under_identical_world_and_clock(self):
        world=World.load("district_v0","B_readable")
        weather=world.roll_weather(random.Random("9:weather:1"))
        def exposed(wet):
            body=Body(core_c=36.5)
            room=Room(fuel=0)
            gear=Equipment(wetness=wet)
            _advance(body,room,world,gear,60,at_home=False,
                     exposure=0.8,weather=weather)
            return body
        dry=exposed(0.0)
        wet=exposed(1.0)
        self.assertAlmostEqual(dry.elapsed_minutes,wet.elapsed_minutes,places=4)
        self.assertGreater(dry.core_c,wet.core_c)
        self.assertLess(dry.core_c,36.5)


class NightToDawn(unittest.TestCase):
    def test_recovery_stay_is_real_alternative_not_free_reward(self):
        world=World.load("district_v0","A_safe")
        agent=__import__("lab.agent",fromlist=["Agent"]).Agent("local",world)
        body=Body(core_c=35.7)
        weather=world.roll_weather(random.Random(42))
        rec,_=run_day(world,agent,weather,random.Random(42),1,2,
                     body=body,charge_legacy_night=False,
                     stay_home_for_recovery=True)
        self.assertFalse(rec.went_out)
        self.assertEqual(rec.carried,0)
        self.assertTrue(any(d.choice=="остаться и восстановиться"
                            and len(d.alternatives)==2 for d in rec.decisions))
        self.assertAlmostEqual(body.elapsed_minutes,0)

    def test_previous_night_is_carried_not_invented(self):
        for name in ("A_safe","B_readable","C_unreadable"):
            result=run(5,days=4,variant=name,heating_policy="agent",
                       carry_night_intent=True)
            hist=result["history"]
            self.assertIsNone(hist[0]["arriving_intention"])
            for before,after in zip(hist,hist[1:]):
                self.assertEqual(after["arriving_intention"],
                                 before["night_formed_next_intention"])
                self.assertIsNotNone(before["evening_decision"])
                self.assertTrue(before["evening_decision"]["outcome"])
            for d in hist:
                if d["evening_decision"] is not None:
                    self.assertTrue(d["evening_decision"]["alternatives"])
                    self.assertIn("ночь",d["evening_decision"]["outcome"])

    def test_opt_in_change_keeps_old_physics_legacy(self):
        a=run(4,days=4,variant="A_safe",heating_policy="dusk")
        b=run(4,days=4,variant="A_safe",heating_policy="dusk",
              carry_night_intent=False)
        self.assertEqual(a,b)

    def test_sequence_research_has_no_missing_contracts(self):
        r=analyze(seeds=2,days=3)
        self.assertEqual(r["design"]["cases"],24)
        self.assertEqual(r["checks"],{k:0 for k in r["checks"]})
        self.assertTrue(r["design"]["no_human_participants"])
        self.assertGreater(r["observations"]["evening_decisions"],0)


if __name__=="__main__":
    unittest.main()
