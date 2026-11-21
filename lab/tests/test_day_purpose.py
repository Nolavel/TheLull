"""D2.0: a physical night can destroy work opportunity; the next day is paid."""
import copy
import unittest

from lab.agent import Agent
from lab.body import Body
from lab.coupled_microloop import Equipment
from lab.evening import Room
from lab.lost_opportunity_study import (
    MAIN,REST,PREPARE,INSULATE,CHOP,
    work_opportunity,decide,execute,_case,study
)
from lab.world import DAY_MINUTES, World


class DayPurposeContracts(unittest.TestCase):
    def setUp(self):
        self.world=World.load("district_v0","A_safe")
        self.agent=Agent("local",self.world)
        self.deadline=DAY_MINUTES+180

    def body(self,core=36.8,stamina=85,fatigue=20,minute=DAY_MINUTES):
        return Body(core_c=core,stamina=stamina,fatigue=fatigue,
                    elapsed_minutes=minute)

    def test_job_feasibility_separates_physical_and_clock_blocks(self):
        b=self.body()
        self.assertTrue(work_opportunity(b,self.deadline)["available"])
        b.core_c=35.8
        self.assertIn("core below outdoor/heavy-work readiness",
                      work_opportunity(b,self.deadline)["blockers"])
        b.core_c=36.8
        b.fatigue=80
        self.assertIn("fatigue above task threshold",
                      work_opportunity(b,self.deadline)["blockers"])
        b.fatigue=20
        b.elapsed_minutes=self.deadline-40
        self.assertIn("insufficient scheduled time",
                      work_opportunity(b,self.deadline)["blockers"])

    def test_still_possible_work_is_really_completed_and_billed(self):
        b=self.body()
        r=Room(fuel=4)
        event=execute(b,r,self.world,Equipment(),MAIN,self.deadline,True)
        self.assertTrue(event["completed"])
        self.assertEqual(event["actual_minutes"],60)
        self.assertFalse(event["after"]["pending"])
        self.assertAlmostEqual(b.stamina,65)
        self.assertAlmostEqual(b.elapsed_minutes,DAY_MINUTES+60)

    def test_insulating_and_packing_produce_distinct_persistent_benefits(self):
        b=self.body()
        r=Room(fuel=4)
        g=Equipment()
        event=execute(b,r,self.world,g,INSULATE,self.deadline,True)
        self.assertTrue(event["completed"])
        self.assertTrue(r.sealed)
        self.assertAlmostEqual(r.cooling_rate,1.5)
        self.assertEqual(event["actual_minutes"],45)
        another=execute(b,r,self.world,g,PREPARE,self.deadline,True)
        self.assertTrue(another["completed"])
        self.assertTrue(b.packed)
        self.assertEqual(another["actual_minutes"],45)

    def test_furniture_chop_has_real_duration_stamina_and_finite_source(self):
        b=self.body()
        r=Room(fuel=1,furniture=1)
        result=execute(b,r,self.world,Equipment(),CHOP,self.deadline,True)
        self.assertTrue(result["completed"])
        self.assertAlmostEqual(b.stamina,30)
        self.assertEqual(result["actual_minutes"],90)
        self.assertEqual(r.furniture,0)
        self.assertEqual(r.fuel,5)
        with self.assertRaises(ValueError):
            execute(b,r,self.world,Equipment(),CHOP,self.deadline,True)

    def test_identical_real_morning_can_select_different_purpose(self):
        b=self.body(core=35.7,stamina=85,fatigue=10)
        r=Room(fuel=1,furniture=2)
        adaptive=decide(self.agent,b,r,self.deadline,True,
                        policy="opportunity",reported_plan=MAIN)
        sticky=decide(self.agent,b,r,self.deadline,True,
                      policy="continue_job",reported_plan=MAIN)
        self.assertNotEqual(adaptive["choice"],sticky["choice"])
        self.assertEqual(adaptive["choice"],CHOP)
        self.assertEqual(sticky["choice"],REST)
        self.assertIn("core below",adaptive["reason"])
        self.assertIn("job_blockers",adaptive["cues"])
        for d in (adaptive,sticky):
            self.assertEqual(len(d["alternatives"]),5)
            self.assertIn(d["choice"],[
                o["option"] for o in d["alternatives"] if o["available"]
            ])

    def test_cold_needs_rest_even_with_fuel_pressure(self):
        b=self.body(core=34.8,stamina=85,fatigue=10)
        d=decide(self.agent,b,Room(fuel=0),self.deadline,True,
                 policy="opportunity",reported_plan=MAIN)
        self.assertEqual(d["choice"],REST)
        self.assertEqual(d["current_goal"],
                         "сначала восстановить способность действовать")

    def test_physical_night_attribution_requires_actual_dawn(self):
        row=_case("A_safe",36.8,0,85,10,"B")
        no_night=row["same_time_without_physical_night"]
        self.assertTrue(no_night["available"])
        if row["real_night"]["reached_next_dawn"]:
            actual=row["actual_morning_job_opportunity"]
            self.assertEqual(
                row["physically_lost_job_opportunity"],
                no_night["available"] and not actual["available"]
            )
            self.assertEqual(
                row["policies"]["opportunity"]["first_decision"]["cues"]["core"],
                row["policies"]["continue_job"]["first_decision"]["cues"]["core"]
            )
        else:
            self.assertFalse(row["physically_lost_job_opportunity"])
            self.assertEqual(row["policies"],{})

    def test_repeatable_paired_full_grid_resource_contracts(self):
        a=study()
        b=study()
        self.assertEqual(a,b)
        self.assertEqual(a["design"]["constructed_evenings"],288)
        self.assertEqual(a["design"]["human_participants"],0)
        self.assertTrue(all(v==0 for v in a["checks"].values()),a["checks"])
        self.assertEqual(a["counts"]["constructed_evenings"],288)
        self.assertEqual(
            a["counts"]["constructed_evenings"],
            a["counts"]["real_mornings"]+
            a["counts"]["nights_without_next_dawn"]
        )
        self.assertEqual(len(a["all_cases"]),288)


if __name__=="__main__":
    unittest.main()
