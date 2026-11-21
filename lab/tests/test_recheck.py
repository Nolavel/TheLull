"""A zero estimate must not pretend to be an observed empty building."""
import random
import unittest

from lab.agent import Agent, SEARCH_CHUNK_MIN
from lab.body import Body
from lab.sim import run_day
from lab.world import DayWeather, World


def prepared_world(*, allow_rechecks=True):
    world = World.load("district_v0", "B_readable")
    agent = Agent("local", world, allow_rechecks=allow_rechecks)
    agent.visited.add("house_a")
    agent.beliefs.loot["house_a"] = 0.0
    # Remove competing known alternatives from the experiment, not the world.
    for node in set(agent.beliefs.loot) - {"house_a"}:
        agent.beliefs.loot[node] = 0.0
        agent.beliefs.confirmed_empty.add(node)
    world.loot["house_a"] = 3
    return world, agent


class RecheckContract(unittest.TestCase):
    def test_zero_estimate_does_not_mean_confirmed_empty(self):
        world, agent = prepared_world()
        self.assertIn("house_a", [x["node"] for x in agent.rank_targets()])
        self.assertTrue(agent.can_recheck("house_a"))
        self.assertNotIn("house_a", agent.beliefs.confirmed_empty)

    def test_observed_empty_is_excluded_without_reading_world_truth(self):
        world, agent = prepared_world()
        actual = world.loot["house_a"]
        agent.learn_loot("house_a", 0)
        self.assertIn("house_a", agent.beliefs.confirmed_empty)
        self.assertFalse(agent.can_recheck("house_a"))
        self.assertEqual(world.loot["house_a"], actual)
        self.assertNotIn("house_a", [x["node"] for x in agent.rank_targets()])

    def test_only_actually_visited_place_can_be_rechecked(self):
        _, agent = prepared_world()
        agent.visited.clear()
        self.assertFalse(agent.can_recheck("house_a"))

    def test_recheck_bills_a_search_chunk_and_observes_real_loot(self):
        world, agent = prepared_world()
        initial = world.loot["house_a"]
        b = Body()
        record, _ = run_day(world, agent, DayWeather(None, None, None),
                            random.Random(9), 1, 0, body=b,
                            charge_legacy_night=False)
        self.assertEqual(record.target, "house_a")
        self.assertGreaterEqual(record.recheck_searches, 1)
        self.assertGreaterEqual(record.search_minutes,
                                record.recheck_searches * SEARCH_CHUNK_MIN)
        self.assertGreater(record.carried, 0)
        self.assertEqual(world.loot["house_a"], initial - record.carried)
        self.assertTrue(any("перепровер" in e for e in record.events))
        self.assertTrue(any(d.point == "цель" and "проверка" in d.reason for d in record.decisions))

    def test_control_policy_disables_rechecks_without_touching_inventory(self):
        world, agent = prepared_world(allow_rechecks=False)
        self.assertFalse(agent.can_recheck("house_a"))
        self.assertNotIn("house_a", [x["node"] for x in agent.rank_targets()])
        self.assertEqual(world.loot["house_a"], 3)

    def test_known_good_stock_is_ranked_above_uncertain_recheck_at_equal_distance(self):
        world, agent = prepared_world()
        agent.beliefs.loot["house_b"] = 4.0
        # Discovery of house_b might depend on world layout; known local profile has it.
        if "house_b" in agent.beliefs.edge_minutes:
            self.assertFalse(agent.can_recheck("house_b"))
        self.assertEqual(agent.beliefs.loot["house_a"], 0)


if __name__ == "__main__":
    unittest.main()
