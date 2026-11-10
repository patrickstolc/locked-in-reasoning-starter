"""Try the puzzle engine without spending API calls. Enter JSON actions."""
import argparse
import json

from world import OPENING, State, apply_action, get_schema, view

DEMO = [
    {"action": "look", "item": "", "target": "room", "focus": "general"},
    {"action": "look", "item": "", "target": "desk", "focus": "underneath"},
]


def perform(state, action):
    print(">", json.dumps(action))
    print(apply_action(state, action))
    print("Known:", ", ".join(view(state)["known_ids"]))
    print("Inventory:", ", ".join(view(state)["inventory"]) or "(empty)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    state = State()
    print(OPENING)
    if args.demo:
        for action in DEMO:
            perform(state, action)
        return
    print("Paste an action as JSON. Commands: /view, /schema, /reset, /quit")
    while True:
        try:
            text = input("\nJSON> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if text == "/quit":
            return
        if text == "/reset":
            state = State()
            print(OPENING)
            continue
        if text == "/view":
            print(json.dumps(view(state), indent=2))
            continue
        if text == "/schema":
            print(json.dumps(get_schema(state), indent=2))
            continue
        try:
            perform(state, json.loads(text))
        except (ValueError, TypeError, KeyError) as error:
            print("Invalid action:", error)


if __name__ == "__main__":
    main()
