"""A terminal limit is a monotonic stop inside the SAME clock, not a morning report."""
import random
import unittest

from lab.body import Body, DEATH_C, step_core
from lab.evening import Room
from lab.evening_run import play
from lab.agent import Agent
from lab.sim import run_day
from lab.survival_loop import _shelter_wait, run
from lab.world import DayWeather, World


class TerminalContract(unittest.TestCase):
    def test_transition_is_exact_and_does_not_recover(self):
        person = Body(core_c=DEATH_C + 0.2)
        step_core(person, -18.0, 2.0)
        self.assertTrue(person.terminal)
        self.assertAlmostEqual(person.core_c, DEATH_C)
        self.assertGreater(person.terminal_at_minute, 0)
        self.assertLess(person.terminal_at_minute, 120)
        at = person.terminal_at_minute
        step_core(person, 40.0, 10.0)
        self.assertEqual(person.core_c, DEATH_C)
        self.assertEqual(person.terminal_at_minute, at)
        self.assertEqual(person.elapsed_minutes, at)
        self.assertEqual(person.last_step_hours, 0)

    def test_shelter_bills_only_time_and_fuel_before_stop(self):
        person = Body(core_c=DEATH_C + 0.2)
        room = Room(fuel=2, fire_lit=False)
        used = _shelter_wait(room, person, -18.0, 60.0)
        self.assertTrue(person.terminal)
        self.assertGreater(used, 0.0)
        self.assertLess(used, 60.0)
        self.assertEqual(room.fuel, 2)  # no heater active
        self.assertAlmostEqual(person.elapsed_minutes, used, places=5)
        self.assertEqual(_shelter_wait(room, person, 10.0, 50.0), 0.0)

    def test_terminal_during_unfinished_trip_is_not_a_homecoming(self):
        world = World.load("district_v0", "B_readable")
        agent = Agent("local", world)
        body = Body(core_c=DEATH_C + 0.01)
        rec, _ = run_day(world, agent, DayWeather(None, None, None),
                         random.Random(3), 1, 0, body=body,
                         charge_legacy_night=False)
        self.assertTrue(body.terminal)
        self.assertTrue(rec.went_out)
        self.assertIsNone(rec.actual_return)
        self.assertIsNotNone(rec.terminal_minute)
        self.assertEqual(rec.run_end_reason, body.terminal_reason)

    def test_unfinished_evening_work_creates_no_free_fuel(self):
        person = Body(core_c=DEATH_C + 0.04, fatigue=40)
        room = Room(fuel=0, furniture=2)
        from lab.agent import Beliefs
        outcome = play("A: разобрать мебель", -18.0, room, person,
                       Beliefs(), hours_of_night=14)
        self.assertTrue(person.terminal)
        self.assertLess(outcome["night_elapsed_h"], 1.5)
        self.assertEqual(room.fuel, 0)
        self.assertEqual(room.furniture, 2)
        self.assertNotIn("утро:", "\n".join(outcome["log"]))

    def test_cold_sleep_wakes_before_any_terminal_transition(self):
        from lab.agent import Beliefs
        sleeper = Body(core_c=35.8, fatigue=60)
        room = Room(fuel=1, fire_lit=True, furniture=0, heated_offset_c=12.0)
        result = play("B: лечь раньше на том, что есть", -12.0,
                      room, sleeper, Beliefs(), hours_of_night=14)
        self.assertGreater(result["woke_cold"], 0)
        self.assertTrue(result["wake_events"])
        # The model keeps its existing 'wake on cold' rule; terminal state
        # is not a new mechanism for skipping the interruption.
        if sleeper.terminal:
            self.assertLess(result["wake_events"][0]["at"],
                            result["night_elapsed_h"])

    def test_restored_body_at_limit_cannot_be_reheated(self):
        frozen_state = Body(core_c=DEATH_C, elapsed_minutes=97)
        self.assertTrue(frozen_state.terminal)
        self.assertEqual(frozen_state.terminal_at_minute, 97)
        step_core(frozen_state, 20, 5)
        self.assertEqual(frozen_state.elapsed_minutes, 97)
        self.assertEqual(frozen_state.core_c, DEATH_C)

    def test_canonical_saves_partial_day_not_a_fabricated_dawn(self):
        for variant in ("B_readable", "C_unreadable"):
            result = run(3, 7, variant=variant, profile="local")
            last = result["history"][-1]
            self.assertTrue(result["end_reason"])
            self.assertTrue(result["terminal_at_minute"] is not None)
            self.assertFalse(last["completed_dawn"])
            self.assertIsNone(last["next_dawn_minute"])
            self.assertLess(last["minutes_accounted"], 1440)
            self.assertLessEqual(result["elapsed_minutes"],
                                 result["days_started"] * 1440)
            self.assertAlmostEqual(result["terminal_at_minute"],
                                   result["elapsed_minutes"], places=3)
            self.assertEqual(result["days_completed"], 0)


if __name__ == "__main__":
    unittest.main()
