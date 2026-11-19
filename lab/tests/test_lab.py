import unittest
from dataclasses import asdict

from lab.agent import Agent
from lab.sim import run
from lab.world import World


class LabTest(unittest.TestCase):
    def test_same_seed_same_story(self):
        a = [asdict(r) for r in run("district_v0", "B_readable", "novice", 8, seed=3)]
        b = [asdict(r) for r in run("district_v0", "B_readable", "novice", 8, seed=3)]
        self.assertEqual(a, b)

    def test_travel_belief_moves_toward_experience(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("novice", world)
        before = agent.beliefs.edge_minutes[("home", "house_a")]["calm"]
        agent.observe_edge("home", "house_a", storm=False, minutes=before * 3)
        after = agent.beliefs.edge_minutes[("home", "house_a")]["calm"]
        self.assertGreater(after, before)
        self.assertLess(after, before * 3)

    def test_novice_knows_only_the_direct_street(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("novice", world)
        self.assertEqual(set(agent.beliefs.edge_minutes), {("home", "house_a")})
        found = agent.discover("house_a", world)
        self.assertIn("shed", found)

    def test_scare_widens_margin_success_narrows_it(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("local", world)
        m = agent.margin
        agent.update_margin(scare=False, on_time=True)
        self.assertLess(agent.margin, m)
        agent.update_margin(scare=True, on_time=False)
        self.assertGreaterEqual(agent.margin, m)


if __name__ == "__main__":
    unittest.main()
