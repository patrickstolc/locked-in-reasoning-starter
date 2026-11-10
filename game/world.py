"""Deterministic room and discovery rules. This private module never goes to the LLM."""
from dataclasses import dataclass, field

ACTIONS = ["look", "take", "open", "use", "clarify"]
FOCUSES = ["", "general", "inside", "seams", "back", "underneath", "nearby"]
PORTABLE = {"brass_key", "battery", "keycard"}
OPENABLE = {"drawer", "false_bottom", "battery_hatch", "locker", "door"}
USE_TARGETS = {"locker", "reader", "door"}
LOCATION_FIELDS = {"brass_key": "key_location", "battery": "battery_location", "keycard": "card_location"}
ALIASES = {"exit": "door", "metal cabinet": "locker", "card reader": "reader",
           "bottom panel": "false_bottom", "raised base": "false_bottom", "rear hatch": "battery_hatch"}
OPENING = "The exit door clicks shut behind you. Emergency lighting hums overhead. What do you want to find out?"


@dataclass
class State:
    known: set[str] = field(default_factory=lambda: {"room", "door"})
    inventory: set[str] = field(default_factory=set)
    reader_examined: bool = False
    drawer_open: bool = False
    bottom_open: bool = False
    hatch_open: bool = False
    locker_open: bool = False
    reader_powered: bool = False
    door_unlocked: bool = False
    escaped: bool = False
    key_location: str = "under_bottom"
    battery_location: str = "in_radio"
    card_location: str = "in_locker"


def _visible(state):
    accessible = {
        "brass_key": state.drawer_open and state.bottom_open and state.key_location == "under_bottom",
        "battery": state.hatch_open and state.battery_location == "in_radio",
        "keycard": state.locker_open and state.card_location == "in_locker",
    }
    return sorted(item for item, available in accessible.items() if available and item in state.known)


def _description(state, target):
    if target == "room":
        return "Emergency lighting hums overhead. Discovered surroundings: " + ", ".join(obj.replace("_", " ") for obj in sorted(state.known - PORTABLE - {"room"})) + "."
    if target == "door":
        return "The exit door is " + ("open; you escaped." if state.escaped else "unlocked." if state.door_unlocked else "locked.")
    if target == "desk":
        return "A writing desk." + (" An old radio sits on top." if "radio" in state.known else "") + (" A deep drawer has a handle at the front." if "drawer" in state.known else "")
    if target == "radio":
        return "An old portable radio." + (" A rear hatch has a thumb catch." if "battery_hatch" in state.known else "")
    if target == "drawer":
        if not state.drawer_open:
            return "The deep desk drawer is closed."
        if not state.bottom_open:
            return "The drawer is open and looks empty. Its interior is noticeably shallower than its outside depth suggests."
        return "The drawer is open with its base panel lifted." + (" A brass key lies beneath it." if "brass_key" in _visible(state) else " The space beneath is empty.")
    if target == "false_bottom":
        if not state.bottom_open:
            return "A thin seam runs around the raised base. Scratches at the front edge suggest the panel can be lifted."
        return "The raised base panel is lifted." + (" A brass key is beneath it." if "brass_key" in _visible(state) else " The space beneath is empty.")
    if target == "battery_hatch":
        if not state.hatch_open:
            return "A small rear hatch has a thumb catch. It is closed."
        return "The rear hatch is open." + (" A battery is inside." if "battery" in _visible(state) else " The compartment is empty.")
    if target == "locker":
        if not state.locker_open:
            return "A locked metal locker with a small keyhole."
        return "The metal locker is open." + (" A keycard is inside." if "keycard" in _visible(state) else " It is empty.")
    if target == "reader":
        description = "The card reader beside the exit is " + ("powered." if state.reader_powered else "unlit.")
        if state.reader_examined:
            description += " A battery occupies its emergency power slot." if state.reader_powered else " The emergency battery slot is empty."
        return description
    if target in state.inventory:
        return "You are carrying " + target.replace("_", " ") + "."
    if target == "battery" and state.battery_location == "installed":
        return "The battery is installed in the reader."
    return {"brass_key": "A small brass key beneath the lifted panel.",
            "battery": "A battery inside the open radio hatch.",
            "keycard": "A plastic keycard inside the open locker."}[target]


def view(state: State) -> dict:
    """Only disclosed objects and their current observable state; no private locations."""
    statuses = {"door": {"locked": not state.door_unlocked, "escaped": state.escaped},
                "drawer": {"open": state.drawer_open}, "false_bottom": {"open": state.bottom_open},
                "battery_hatch": {"open": state.hatch_open}, "locker": {"open": state.locker_open},
                "reader": {"powered": state.reader_powered}}
    return {"objects": {obj: _description(state, obj) for obj in sorted(state.known)},
            "known_ids": sorted(state.known), "inventory": sorted(state.inventory),
            "visible_items": _visible(state),
            "status": {obj: data for obj, data in statuses.items() if obj in state.known},
            "aliases": {alias: obj for alias, obj in ALIASES.items() if obj in state.known}}


def get_schema(state: State) -> dict:
    enums = {"action": ACTIONS, "item": ["", *sorted(state.known & PORTABLE)],
             "target": ["", *sorted(state.known)], "focus": FOCUSES}
    return {"type": "object", "additionalProperties": False,
            "properties": {key: {"type": "string", "enum": values} for key, values in enums.items()},
            "required": list(enums)}


def validate_action(payload: dict, schema=None) -> dict:
    """A schema from get_schema also enforces the current discovery boundary."""
    schema = get_schema(State()) if schema is None else schema
    if type(payload) is not dict or set(payload) != {"action", "item", "target", "focus"}:
        raise ValueError("Expected exactly action, item, target and focus.")
    for key, value in payload.items():
        if type(value) is not str or value not in schema["properties"][key]["enum"]:
            raise ValueError(f"Invalid or undiscovered {key}.")
    kind, item, target, focus = (payload[k] for k in ("action", "item", "target", "focus"))
    valid = {"look": item == "" and target != "" and focus != "",
             "take": item != "" and target == focus == "",
             "open": item == focus == "" and target in OPENABLE,
             "use": item != "" and target in USE_TARGETS and focus == "",
             "clarify": item == target == focus == ""}
    if not valid[kind]:
        raise ValueError("Invalid combination of action, item, target and focus.")
    return dict(payload)


def _look(state, target, focus):
    if target == "room" and focus == "general":
        state.known.update({"desk", "radio", "locker", "reader"})
        return "A desk holds an old radio. Nearby stands a metal locker. " + _description(state, "door") + " " + _description(state, "reader")
    if target == "door" and focus == "nearby":
        state.known.add("reader")
        return _description(state, "reader")
    if target == "desk" and focus in {"general", "underneath"}:
        state.known.update({"drawer", "radio"})
        return _description(state, "desk")
    if target == "reader" and focus == "general":
        state.reader_examined = True
        return _description(state, "reader")
    if target == "drawer":
        if not state.drawer_open:
            return "The drawer is closed. You cannot inspect its interior from here."
        if focus in {"seams", "underneath"}:
            state.known.add("false_bottom")
            return _description(state, "false_bottom")
        if focus in {"general", "inside"}:
            return _description(state, "drawer")
    if target == "radio":
        if focus in {"back", "underneath", "seams"}:
            state.known.add("battery_hatch")
            return _description(state, "battery_hatch")
        if focus == "general":
            return "The radio's front has a dusty tuning dial and a speaker grille."
        if focus == "inside":
            return _description(state, "battery_hatch") if state.hatch_open else "The radio's casing is closed. You cannot see inside."
    if target == "battery_hatch" and focus == "inside":
        return _description(state, target)
    if target == "false_bottom" and focus == "inside":
        if not state.drawer_open:
            return "The drawer is closed. You cannot see beneath that panel."
        return _description(state, target) if state.bottom_open else "The base panel is still in place. You cannot see beneath it."
    if target == "locker" and focus != "general":
        if focus == "inside":
            return _description(state, "locker") if state.locker_open else "The locker is locked. You cannot see inside."
        return "You find no extra panel or compartment on that part of the locker."
    if focus == "general":
        return _description(state, target)
    return "From here you find no additional detail there."


def apply_action(state: State, payload: dict) -> str:
    """Discovery belongs to look; physical changes require an explicit action."""
    action = validate_action(payload, get_schema(state))
    kind, item, target, focus = (action[k] for k in ("action", "item", "target", "focus"))
    if kind == "clarify":
        return "Name one thing you want to inspect or one action you want to perform."
    if state.escaped:
        return "You have already escaped. Use /reset for a new game."
    if kind == "look":
        return _look(state, target, focus)
    if kind == "take":
        if item in state.inventory:
            return "You are already carrying that item."
        if item not in _visible(state):
            return "That item is not available to take."
        state.inventory.add(item)
        setattr(state, LOCATION_FIELDS[item], "inventory")
        return "You picked up " + item.replace("_", " ") + "."
    if kind == "open":
        if target == "drawer":
            state.drawer_open = True
            return _description(state, target)
        if target == "false_bottom":
            if not state.drawer_open:
                return "The drawer must be open before you can reach that panel."
            state.bottom_open = True
            state.known.add("brass_key")
            return _description(state, "drawer")
        if target == "battery_hatch":
            state.hatch_open = True
            state.known.add("battery")
            return _description(state, target)
        if target == "locker":
            return "The locker is already open." if state.locker_open else "The locker is locked."
        if not state.door_unlocked:
            return "The exit door is locked."
        state.escaped = True
        return "You open the exit door and escape."
    if item not in state.inventory:
        return "You are not carrying that item."
    if (item, target) == ("brass_key", "locker"):
        if state.locker_open:
            return "The locker is already open."
        state.locker_open = True
        state.known.add("keycard")
        return "The key opens the locker. A keycard is inside. You keep the key."
    if (item, target) == ("battery", "reader"):
        if state.reader_powered:
            return "The reader is already powered."
        state.inventory.remove("battery")
        state.battery_location = "installed"
        state.reader_powered = True
        return "You install the battery. The card reader powers on."
    if (item, target) == ("keycard", "reader"):
        if not state.reader_powered:
            return "The card reader has no power."
        if state.door_unlocked:
            return "The exit door is already unlocked."
        state.door_unlocked = True
        return "The reader accepts the keycard and unlocks the exit. You keep the card."
    return "That item cannot be used on that target."
