"""The stove actor gets real alternatives, not the same scripted switch renamed."""
import unittest

from lab.agent import Agent
from lab.body import Body
from lab.evening import Room, UNDECIDED
from lab.heat_choice import LIGHT, SAVE, make_heat_decision
from lab.survival_loop import run
from lab.world import World


class HeatChoiceContracts(unittest.TestCase):
    def setUp(self):
        self.world = World.load("district_v0", "B_readable")
        self.agent = Agent("local", self.world)

    def test_both_real_alternatives_with_predicted_costs(self):
        dec = make_heat_decision(Body(), Room(fuel=3), self.agent.beliefs,
                                 UNDECIDED, -9.0, "утро", 1.0)
        self.assertEqual({x["option"] for x in dec.alternatives}, {LIGHT, SAVE})
        self.assertTrue(all(x["available"] for x in dec.alternatives))
        self.assertEqual(dec.point, "печь:утро")
        self.assertIn(dec.choice, (LIGHT, SAVE))
        self.assertNotEqual(dec.alternatives[0]["expected_fuel_spent"],
                            dec.alternatives[1]["expected_fuel_spent"])

    def test_same_observations_different_hidden_weather_or_loot_same_decision(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("local", world)
        person = Body(core_c=36.0)
        room = Room(fuel=2)
        first = make_heat_decision(person, room, agent.beliefs, UNDECIDED,
                                   -8, "вернулся", 1.0)
        world.loot = {node: 999 for node in world.loot}
        world.air_temp_c = 40.0
        second = make_heat_decision(person, room, agent.beliefs, UNDECIDED,
                                    -8, "вернулся", 1.0)
        self.assertEqual(first, second)

    def test_real_learning_not_copied_from_world(self):
        b = self.agent.beliefs
        old = b.shelter_core_cooling_est
        b.observe_shelter_cooling(37, 36.2, .5)
        self.assertNotEqual(old, b.shelter_core_cooling_est)
        self.assertGreater(b.shelter_core_cooling_est, 0)

    def test_human_provider_can_choose_both_without_changing_physics(self):
        for choice, expected in (("light", LIGHT), ("save", SAVE)):
            dec = make_heat_decision(Body(), Room(fuel=3), self.agent.beliefs,
                    UNDECIDED, -8, "возвращение", 1,
                    provider=lambda _: choice)
            self.assertEqual(dec.choice, expected)
        with self.assertRaises(ValueError):
            make_heat_decision(Body(), Room(fuel=3), self.agent.beliefs,
                    UNDECIDED, -8, "возвращение", 1,
                    provider=lambda _: "magic")

    def test_existing_four_baselines_are_not_implicitly_modified(self):
        for name in ("dusk", "at_dawn", "on_return", "cold_trigger_36c"):
            self.assertEqual(run(3, 3, variant="B_readable", heating_policy=name),
                             run(3, 3, variant="B_readable", heating_policy=name))

    def test_agent_real_decisions_stove_and_fuel_are_accounted(self):
        for variant in ("A_safe", "B_readable", "C_unreadable"):
            story = run(3, 3, variant=variant, heating_policy="agent")
            self.assertEqual(story["decision_source"], "agent")
            all_dec = [d for h in story["history"] for d in h["stove_decisions"]]
            self.assertTrue(all_dec, variant)
            for dec in all_dec:
                self.assertEqual(len(dec["alternatives"]), 2)
                self.assertTrue(dec["reason"] and dec["outcome"])
                self.assertIn(dec["choice"], (LIGHT, SAVE))
                self.assertTrue(dec["cues"])
            for d in story["history"]:
                self.assertGreaterEqual(d["fuel_burned_today"], 0)
                self.assertGreaterEqual(d["fire_hours_today"], 0)
                self.assertLessEqual(d["fuel_next_dawn"],
                    d["fuel_at_dawn"] + d["fuel_delivered"]
                    + 4 * (d["furniture_at_dawn"] - d["furniture_next_dawn"]) + .001)
            self.assertAlmostEqual(sum(d["minutes_accounted"] for d in story["history"]),
                                   story["elapsed_minutes"], places=4)

    def test_human_can_overrule_without_automatic_ignition(self):
        story = run(3, 1, variant="A_safe", heating_policy="agent",
                    decision_provider=lambda _: "save")
        self.assertEqual(story["decision_source"], "human")
        self.assertEqual(sum(len(d["early_ignitions"]) for d in story["history"]), 0)
        self.assertTrue(all(d["choice"] == SAVE for h in story["history"]
                            for d in h["stove_decisions"]))

    def test_no_interaction_after_terminal(self):
        body = Body(core_c=28.8)
        with self.assertRaises(ValueError):
            make_heat_decision(body, Room(fuel=3), self.agent.beliefs,
                    UNDECIDED, -20, "too_late", 1.0)


if __name__ == "__main__":
    unittest.main()
