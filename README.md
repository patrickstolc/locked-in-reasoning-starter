# Locked In: W46 reasoning starter

This repo gives you a working W45 editor to use as V0. In W46 you’ll build V1
(tool results guide the next action) and V2 (a separate review call checks the
evidence). Use your own W45 editor if you already have it running.

## 1. Run the baseline

You need Python 3.11 and Docker. From the repo root on macOS or Linux:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker build -t locked-in-executor .
python -m unittest -v test_editor
python editor.py --demo opening
```

On Windows PowerShell, create the environment with `py -3.11 -m venv .venv`
and activate it with `.\.venv\Scripts\Activate.ps1`. The remaining commands
are the same. Choose `d` to discard the demo so your game starts clean next
time. The demo uses a scripted model and needs no API key.

For a model run, set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in your
terminal, as in W45. Use a model that supports tool calling.

```sh
python editor.py --profile opening --request "Rewrite the opening as a storm shelter. Keep the same objects and rules, and don't reveal hidden items."
```

For the keycard request, use the same `opening` profile for your V0 run.
It checks the original brass key rule and the escape route. Record the keycard
checks separately. The `single-use` profile is the W45 **brass key** exercise.

## 2. Find the places to extend

| File | What to look for |
| --- | --- |
| `editor.py` | `build_agent` registers the three tools. The CLI shows the diff and verification result before asking whether to accept. |
| `dev_session.py` | A disposable workspace, the shared counter for up to three agent executions, and the checks that guard Accept. |
| `checks/verify_game.py` | Controller-owned tests. Use `act` and `find_key` to set up your own keycard checks. |
| `game/world.py` | The rules for using the keycard on the reader. The reader must have power before the card can unlock the exit. |

Save your baseline results, then follow the [W46 lab](https://moodle.easv.dk/course/section.php?id=422035).
Keep the same model and game starting state for every version. Discard proposed
changes after recording the results, or pass `--game` a fresh copy of the
`game/` folder. See `runs/` for the execution log, model messages and diff.
Keep keys out of that folder and out of Git.

See [small code examples](examples.md) for the shape of a tool result and a
review item. Your job is to decide how the editor uses them and how it handles
missing or failed checks.
