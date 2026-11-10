"""Scripted PydanticAI tool trace; real edits, unchanged checks and Docker results."""
import json
import difflib
import os
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart
from pydantic_ai.models.function import FunctionModel


def demo_model(session, profile):
    source = session.original["world.py"].decode()
    if profile == "opening":
        old = 'OPENING = "The exit door clicks shut behind you. Emergency lighting hums overhead. What do you want to find out?"'
        new = 'OPENING = "The station airlock seals behind you. Emergency lighting flickers through the abandoned cabin. What do you want to inspect?"'
        assert old in source
        changed = source.replace(old, new)
        check = "from world import OPENING\nassert 'station' in OPENING.lower()\nprint(OPENING)\n"
        calls = [
            ("Read the original game", "read_file", {"path": "world.py"}),
            ("Change only the opening", "write_file", {"path": "world.py", "content": changed}),
            ("Save a check for the new opening", "write_file", {"path": "check_change.py", "content": check}),
            ("Run the check inside Docker", "run_python", {"code": "exec(open('check_change.py').read())"}),
        ]
        expected = [0]
    else:
        old = '        return "The key opens the locker. A keycard is inside. You keep the key."'
        message = '        return "The key opens the locker, then snaps in the lock. A keycard is inside."'
        assert old in source
        # The first proposal changes the message but forgets the inventory mutation.
        broken = source.replace(old, message)
        repaired = source.replace(old, '        state.inventory.remove("brass_key")\n'
            '        state.key_location = "consumed"\n' + message)
        check = ("from world import State, apply_action\n"
            "s = State()\ns.known.update({'brass_key', 'locker', 'reader'})\n"
            "s.inventory.add('brass_key')\ns.key_location = 'inventory'\n"
            "apply_action(s, dict(action='use', item='brass_key', target='reader', focus=''))\n"
            "assert 'brass_key' in s.inventory, 'Wrong target consumed the key'\n"
            "assert not s.locker_open, 'Wrong target opened the locker'\n"
            "message = apply_action(s, dict(action='use', item='brass_key', target='locker', focus=''))\n"
            "print(message)\nprint('Inventory:', sorted(s.inventory))\n"
            "assert s.locker_open, 'Locker did not open'\n"
            "assert 'brass_key' not in s.inventory, 'Key still in inventory after successful use'\n"
            "print('Key behaviour passed')\n")
        calls = [
            ("Read the original game", "read_file", {"path": "world.py"}),
            ("Proposal 1: the message claims the key broke", "write_file", {"path": "world.py", "content": broken}),
            ("Save the behaviour check; it stays unchanged", "write_file", {"path": "check_change.py", "content": check}),
            ("Does the inventory agree with the message?", "run_python", {"code": "exec(open('check_change.py').read())"}),
            ("Repair world.py: consume the key after the unlock", "write_file", {"path": "world.py", "content": repaired}),
            ("Run the SAME check again", "run_python", {"code": "exec(open('check_change.py').read())"}),
        ]
        expected = [1, 0]
    calls = iter(calls)

    def respond(messages, info):
        # Stop the prepared trace if execution did not follow the expected scenario.
        events = [json.loads(line) for line in (session.run_dir / "execution.jsonl").read_text().splitlines()]
        results = [event['result'] for event in events if event['event'] == 'execute']
        for index, result in enumerate(results):
            if result['timed_out'] or result['exit_code'] != expected[index]:
                raise RuntimeError("Unexpected execution result; inspect the output before continuing.")
        if profile == 'single-use' and results and 'Key still in inventory' not in results[0]['stderr']:
            raise RuntimeError("The first execution failed for an unexpected reason.")
        try:
            label, name, args = next(calls)
            print(f"\n{label}", flush=True)
            if name == 'write_file':
                if args['path'] == 'world.py':
                    before = session.read_file('world.py')
                    print(''.join(difflib.unified_diff(before.splitlines(True), args['content'].splitlines(True),
                        fromfile='current proposal/world.py', tofile='next proposal/world.py')), flush=True)
                else:
                    print(args['content'], flush=True)
            if os.getenv('LECTURE_STEP') == '1':
                input('Press Enter to run this tool call: ')
            return ModelResponse(parts=[ToolCallPart(name, args)])
        except StopIteration:
            return ModelResponse(parts=[TextPart("Proposed edit and execution complete. Inspect the diff and independent checks before acceptance.")])

    return FunctionModel(respond, model_name="scripted-editor-demo")
