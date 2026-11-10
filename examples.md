# Small code examples

## Inspect one tool result

In the starter, `run_python` returns a dictionary. A timeout and a nonzero
exit code are both useful observations. Use the output to decide what to check
or repair next.

```python
# session is the current DevSession. This executes inside Docker.
result = session.run_python("from world import State\nassert not State().escaped")
if result["timed_out"]:
    print("The check timed out.")
elif result["exit_code"] != 0:
    print(result["stderr"] or result["stdout"])
```

## Represent one review item

Give the reviewer the request, diff and check results. Ask for a row like this
for each requirement. This example comes from a run that skipped a check.

```python
review_item = {
    "requirement": "The keycard survives a wrong target",
    "status": "unverified",
    "evidence": "No check tried the keycard on a wrong target.",
}
```

Decide how to validate the returned rows and where to stop a revision if the
current session has used its execution budget.
