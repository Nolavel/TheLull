"""Reproducibility and human console observables for one real lab choice."""
import unittest

from lab.heat_choice import LIGHT, SAVE
from lab.human_stove_session import human_provider, session
from lab.stove_choice_study import ARMS, measure


class StoveStudyContracts(unittest.TestCase):
    def test_registered_paired_axes_and_resource_invariants(self):
        report = measure(seeds=2, days=3)
        self.assertEqual(report["design"]["paired_cases_per_arm"], 12)
        self.assertEqual(report["design"]["human_participant_count"], 0)
        self.assertTrue(all(v == 0 for v in report["checks"].values()),
                        report["checks"])
        for v in ("A_safe","B_readable","C_unreadable"):
            self.assertEqual(set(report["groups"][v]), set(ARMS))
            self.assertGreater(report["groups"][v]["agent"]["decisions"], 0)

    def test_human_sees_cues_and_choices_not_agent_advice(self):
        from lab.agent import Agent
        from lab.body import Body
        from lab.evening import Room, UNDECIDED
        from lab.heat_choice import make_heat_decision
        from lab.world import World
        agent = Agent("local", World.load("district_v0", "B_readable"))
        d = make_heat_decision(Body(), Room(fuel=3), agent.beliefs,
                               UNDECIDED, -9, "утро", 1)
        messages = []
        replies = iter(["nope","2","сохранить на ночь"])
        got = human_provider(d, ask=lambda _: next(replies),
                             show=messages.append)
        self.assertEqual(got, "save")
        self.assertTrue(any("Ответь 1 или 2" in line for line in messages))
        self.assertFalse(any("expected_cost" in line for line in messages))
        self.assertFalse(any("выбрал" in line for line in messages))
        self.assertIn("сохранить на ночь", d.reason)

    def test_complete_one_day_human_session_with_no_real_person(self):
        shown = []
        def provider(prompt):
            if "Твой выбор" in prompt:
                return "2"
            if "Почему" in prompt:
                return "дров мало"
            return "сделать вылазку"
        result = session(1, "A_safe", ask=provider, show=shown.append)
        self.assertEqual(result["participant_count"], 1)  # simulated CLI user in test only
        self.assertEqual(result["human_run"]["decision_source"], "human")
        self.assertEqual(result["agent_same_seed"]["decision_source"], "agent")
        self.assertTrue(result["human_run"]["history"][0]["stove_decisions"])
        self.assertTrue(all(d["choice"] == SAVE for h in result["human_run"]["history"]
                            for d in h["stove_decisions"]))
        self.assertTrue(result["interview"]["next_intention"])
        self.assertEqual(result["seed"], 1)


if __name__ == "__main__":
    unittest.main()
