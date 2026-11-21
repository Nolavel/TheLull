"""D1.8 — priorities explain choices, costs and causal goal transitions."""
import copy
import unittest

from lab.agent import Agent
from lab.body import Body
from lab.coupled_microloop import Equipment
from lab.evening import Room, HEAVY
from lab.goal_priority_study import (
    PROTECT,FUEL,WORK,GOALS,REST,HEAT,CHOP,DO_WORK,
    Session,plan,execute,update_goal,case,study,
)
from lab.world import World


class GoalPriorityContractTests(unittest.TestCase):
    def setup_state(self,*,core=36.8,stamina=85,fuel=3,deadline=240,variant="A_safe"):
        w=World.load("district_v0",variant)
        return w,Agent("local",w),Session(
            Body(core_c=core,stamina=stamina,fatigue=15),
            Room(fuel=fuel,furniture=2,has_axe=True),Equipment(wetness=0),
            deadline_minute=deadline,
        )

    def test_same_physics_different_goal_changes_action_without_hardcoding(self):
        w,a,s=self.setup_state()
        decisions={g:plan(a,s,g) for g in GOALS}
        self.assertEqual(decisions[FUEL]["choice"],CHOP)
        self.assertEqual(decisions[WORK]["choice"],DO_WORK)
        self.assertEqual(decisions[PROTECT]["choice"],REST)
        self.assertEqual(len({d["choice"] for d in decisions.values()}),3)
        self.assertTrue(all(len(x["alternatives"])==4
                            for x in decisions.values()))
        self.assertTrue(all(x["choice"] in [o["option"] for o in x["alternatives"]
                                            if o["available"]]
                            for x in decisions.values()))

    def test_fuel_requires_finite_furniture_time_and_real_stamina(self):
        w,a,s=self.setup_state(stamina=85)
        before=(s.body.elapsed_minutes,s.body.stamina,s.room.fuel,s.room.furniture)
        r=execute(s,CHOP,w)
        self.assertTrue(r["completed"])
        self.assertEqual(r["elapsed_minutes"],90)
        self.assertEqual(s.room.fuel,before[2]+HEAVY.fuel)
        self.assertEqual(s.room.furniture,before[3]-1)
        self.assertAlmostEqual(s.body.stamina,before[1]-HEAVY.stamina_cost)
        self.assertAlmostEqual(s.body.elapsed_minutes,before[0]+90)

    def test_work_is_not_automatically_generated_or_free(self):
        w,a,s=self.setup_state(stamina=85)
        r=execute(s,DO_WORK,w)
        self.assertTrue(r["completed"])
        self.assertFalse(s.pending_work)
        self.assertEqual(r["elapsed_minutes"],60)
        self.assertAlmostEqual(s.body.stamina,65)
        self.assertEqual(s.room.fuel,3)

    def test_real_chopping_consequence_reprioritizes_preserving_strength(self):
        w,a,s=self.setup_state(core=36.8,stamina=85)
        first=plan(a,s,FUEL)
        self.assertEqual(first["choice"],CHOP)
        r=execute(s,first["choice"],w)
        g=update_goal(s,FUEL)
        self.assertTrue(r["completed"])
        self.assertEqual(g["next_goal"],PROTECT)
        adapted=plan(a,s,g["next_goal"])
        frozen=plan(a,s,FUEL)
        self.assertNotEqual(adapted["goal"],frozen["goal"])
        self.assertIn("stamina",g["because"])

    def test_work_completion_changes_priority_without_false_repeating_work(self):
        w,a,s=self.setup_state()
        execute(s,DO_WORK,w)
        next_goal=update_goal(s,WORK)
        self.assertEqual(next_goal["next_goal"],PROTECT)
        self.assertFalse(any(o["option"]==DO_WORK and o["available"]
                             for o in plan(a,s,PROTECT)["alternatives"]))

    def test_cold_pressure_can_override_initial_fuel_goal(self):
        w,a,s=self.setup_state(core=35.4,stamina=85,fuel=3,variant="B_readable")
        # On direct observation it is legitimate to change the goal;
        # without an action no such event is to be misrepresented as learning.
        d=update_goal(s,FUEL)
        self.assertEqual(d["next_goal"],PROTECT)

    def test_choice_is_based_on_belief_not_hidden_outcome(self):
        w,a,s=self.setup_state()
        p=plan(a,s,PROTECT)
        # Changes to subjective cooling estimate affect the predicted
        # alternatives, while the true World and Body have not changed.
        a.beliefs.shelter_core_cooling_est=5
        q=plan(a,s,PROTECT)
        x={o["option"]:o for o in p["alternatives"]}
        y={o["option"]:o for o in q["alternatives"]}
        self.assertNotEqual(x[REST]["predicted_core"],y[REST]["predicted_core"])
        self.assertEqual(s.body.core_c,36.8)

    def test_adaptive_and_frozen_physical_continuations_share_post_state(self):
        row=case("A_safe",36.8,85,3,0,240,FUEL)
        self.assertEqual(row["first_intention"]["choice"],CHOP)
        self.assertTrue(row["goal_update"]["changed"])
        self.assertEqual(row["goal_update"]["after"],PROTECT)
        # Assigned FUEL was already at odds with what the state would have
        # inferred before chopping. A "replan" from this alone is NOT
        # proof of learning from the action; separate that baseline.
        self.assertEqual(row["goal_update"]["pressure_inferred_before_action"]["next_goal"],WORK)
        self.assertTrue(row["goal_update"]["pressure_truly_changed_after_action"])
        self.assertEqual(row["decision_chain"]["forecast_committed_before_action"]["option"],CHOP)
        self.assertEqual(row["decision_chain"]["next_action"],row["next_intentions"]["adapted"]["choice"])
        # Both agents can legitimately choose rest here: after chopping,
        # stamina < 55 makes a second chop unavailable. A revised goal is
        # NOT a promise that every individual case changes the action.
        for r in row["next_actual_physical_continuations"].values():
            self.assertEqual(r["before"]["minutes"],
                             row["state_after_first"]["elapsed_minutes"])
            self.assertEqual(r["before"]["fuel"],row["state_after_first"]["fuel"])

    def test_terminal_body_cannot_magically_act(self):
        w,a,s=self.setup_state(core=28.8)
        d=plan(a,s,FUEL)
        self.assertIsNone(d["choice"])
        self.assertIsNone(update_goal(s,FUEL)["next_goal"])
        for action in (REST,HEAT,CHOP,DO_WORK):
            with self.assertRaises(ValueError):
                execute(s,action,w)

    def test_same_initial_state_different_actual_outcome_changes_emergent_goal(self):
        w,a,s=self.setup_state(core=36.8,stamina=85,fuel=1,deadline=240)
        clone=copy.deepcopy(s)
        execute(s,CHOP,w)
        execute(clone,REST,w)
        self.assertEqual(update_goal(s,WORK)["next_goal"],PROTECT)
        self.assertEqual(update_goal(clone,WORK)["next_goal"],FUEL)

    def test_disagreement_with_assigned_goal_is_not_counted_as_new_pressure(self):
        row=case("A_safe",35.4,55,3,0,240,FUEL)
        self.assertEqual(row["goal_update"]["before"],FUEL)
        self.assertEqual(row["goal_update"]["pressure_inferred_before_action"]["next_goal"],PROTECT)
        self.assertTrue(row["goal_update"]["changed"])
        self.assertFalse(row["goal_update"]["pressure_truly_changed_after_action"])

    def test_all_grid_conservation_and_comparisons(self):
        r=study()
        self.assertEqual(r["design"]["distinct_initial_states"],96)
        self.assertEqual(r["design"]["total_cases"],288)
        self.assertEqual(r["checks"],{k:0 for k in r["checks"]},r["checks"])
        self.assertGreater(r["counts"].get("goal_revisions",0),0)
        self.assertGreater(r["counts"].get("goal_caused_next_action_change",0),0)
        self.assertGreater(r["counts"].get("new_pressure_after_actual_action",0),0)
        self.assertGreater(r["counts"].get("consequence_changed_goal_and_next_action",0),0)
        self.assertGreater(r["counts"].get("same_state_distinct_first_actions",0),0)
        self.assertEqual(r["design"]["human_participants"],0)


if __name__=="__main__":
    unittest.main()
