"""D1.9 continuity tests: real weather/day/night and no invented next dawn."""
import unittest

from lab.agent import Agent
from lab.body import Body
from lab.evening import Room
from lab.goal_priority_study import FUEL, PROTECT, WORK
from lab.overnight_goal_policy import (
    RECOVER, FORAGE, FINISH, pressure, choose_morning,
)
from lab.overnight_goal_study import study, audit_history
from lab.survival_loop import run
from lab.world import World


class GoalOvernightContracts(unittest.TestCase):
    def test_three_goals_rank_same_real_morning_state_differently(self):
        w=World.load("district_v0","A_safe")
        a=Agent("local",w)
        b=Body(stamina=85)
        r=Room(fuel=2)
        choices={
            goal:choose_morning(goal,b,r,a,w,pending_work=True,
                                deadline_minute=2880)
            for goal in (PROTECT,FUEL,WORK)
        }
        self.assertEqual(choices[PROTECT]["choice"],RECOVER)
        self.assertEqual(choices[FUEL]["choice"],FORAGE)
        self.assertEqual(choices[WORK]["choice"],FINISH)
        for row in choices.values():
            self.assertEqual(len(row["alternatives"]),3)
            self.assertIn(row["choice"],[
                x["option"] for x in row["alternatives"] if x["available"]
            ])

    def test_pressures_depend_on_observed_body_and_fuel_not_night_label(self):
        w=World.load("district_v0","A_safe")
        body=Body(core_c=36.8,stamina=100)
        room=Room(fuel=4)
        p=pressure(body,room,w,pending_work=True,deadline_minute=2880)
        self.assertEqual(p["goal"],WORK)
        body.core_c=35.7
        q=pressure(body,room,w,pending_work=True,deadline_minute=2880)
        self.assertEqual(q["goal"],PROTECT)
        body.core_c=36.8
        room.fuel=1
        v=pressure(body,room,w,pending_work=True,deadline_minute=2880)
        self.assertEqual(v["goal"],FUEL)

    def test_canonical_full_day_is_paid_and_next_dawn_receives_night_intent(self):
        row=run(1,3,variant="A_safe",profile="local",
                goal_policy="adaptive",initial_goal=FUEL)
        self.assertTrue(row["history"])
        self.assertEqual(audit_history(row)["checks"],{})
        for first,second in zip(row["history"],row["history"][1:]):
            self.assertTrue(first["completed_dawn"])
            self.assertAlmostEqual(first["core_next_dawn"],second["core_at_dawn"])
            self.assertAlmostEqual(first["fuel_next_dawn"],second["fuel_at_dawn"])
            self.assertEqual(second["goal_continuity"]["goal_at_this_dawn"],
                             first["goal_continuity"]["after_night"]["goal"])

    def test_frozen_goal_never_changes_across_true_dawns(self):
        for goal in (PROTECT,FUEL,WORK):
            r=run(2,3,variant="A_safe",goal_policy="frozen",
                  initial_goal=goal)
            self.assertEqual(audit_history(r)["checks"],{})
            self.assertTrue(all(
                d["goal_continuity"]["goal_at_this_dawn"]==goal
                for d in r["history"]
            ))

    def test_finite_job_can_complete_once_and_stay_completed(self):
        r=run(2,3,variant="A_safe",goal_policy="adaptive",
              initial_goal=WORK)
        self.assertEqual(audit_history(r)["checks"],{})
        accomplished=[
            d["goal_continuity"]["work_action"]["completed"]
            for d in r["history"] if d["goal_continuity"]["work_action"]
        ]
        self.assertLessEqual(sum(accomplished),1)
        if accomplished:
            self.assertFalse(r["pending_work_at_end"])

    def test_old_canonical_results_unmodified_when_goal_mode_off(self):
        baseline=run(4,3,variant="B_readable")
        explicit=run(4,3,variant="B_readable",goal_policy=None)
        self.assertEqual(baseline,explicit)
        self.assertTrue(all(
            d["goal_continuity"] is None for d in baseline["history"]
        ))

    def test_terminal_cannot_generate_fake_following_dawn(self):
        for variant in ("B_readable","C_unreadable"):
            r=run(1,3,variant=variant,goal_policy="adaptive",
                  initial_goal=FUEL)
            self.assertEqual(audit_history(r)["checks"],{})
            self.assertEqual(r["days_completed"],
                             sum(d["completed_dawn"] for d in r["history"]))
            if r["terminal_at_minute"] is not None:
                self.assertAlmostEqual(r["elapsed_minutes"],
                                       r["terminal_at_minute"],places=5)

    def test_two_policy_trial_is_repeatable_with_no_forced_success(self):
        a=study(seeds=2,days=3)
        b=study(seeds=2,days=3)
        self.assertEqual(a,b)
        self.assertEqual(a["design"]["pair_count"],36)
        self.assertTrue(all(v==0 for v in a["checks"].values()),a["checks"])
        self.assertEqual(a["design"]["human_participants"],0)


if __name__=="__main__":
    unittest.main()
