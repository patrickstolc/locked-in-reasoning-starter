"""Controller-owned checks. Mounted read-only, never given to the editing tools."""
import unittest
from world import State, apply_action, get_schema, view

PROFILE = "opening"


def act(state, action, *, item="", target="", focus=""):
    return apply_action(state, dict(action=action, item=item, target=target, focus=focus))


def find_key():
    state = State()
    act(state, "look", target="room", focus="general")
    act(state, "look", target="desk", focus="general")
    act(state, "open", target="drawer")
    act(state, "look", target="drawer", focus="seams")
    act(state, "open", target="false_bottom")
    act(state, "take", item="brass_key")
    return state


class GameChecks(unittest.TestCase):
    def test_start_and_action_interface(self):
        state = State()
        self.assertEqual(set(view(state)["known_ids"]), {"room", "door"})
        self.assertEqual(view(state)["inventory"], [])
        self.assertNotIn("brass_key", str(view(state)))
        self.assertEqual(set(get_schema(state)["required"]), {"action", "item", "target", "focus"})
        with self.assertRaises(ValueError):
            act(state, "take", item="brass_key")
        act(state, "open", target="door")
        self.assertFalse(state.escaped)

    def test_wrong_target_and_key_consumption(self):
        state = find_key()
        act(state, "use", item="brass_key", target="reader")
        self.assertIn("brass_key", state.inventory)
        self.assertFalse(state.locker_open)
        act(state, "use", item="brass_key", target="locker")
        self.assertTrue(state.locker_open)
        self.assertIn("keycard", view(state)["visible_items"])
        if PROFILE == "single-use":
            self.assertNotIn("brass_key", state.inventory)
            act(state, "take", item="brass_key")
            self.assertNotIn("brass_key", state.inventory)
            self.assertNotIn("brass_key", view(state)["visible_items"])
        else:
            self.assertIn("brass_key", state.inventory)

    def test_complete_escape_route(self):
        state = find_key()
        act(state, "use", item="brass_key", target="locker")
        act(state, "take", item="keycard")
        act(state, "use", item="keycard", target="reader")
        self.assertFalse(state.door_unlocked)
        act(state, "look", target="radio", focus="back")
        act(state, "open", target="battery_hatch")
        act(state, "take", item="battery")
        act(state, "use", item="battery", target="reader")
        act(state, "use", item="keycard", target="reader")
        act(state, "open", target="door")
        self.assertTrue(state.escaped)


if __name__ == "__main__":
    unittest.main()
