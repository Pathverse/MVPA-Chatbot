"""Defines and executes the local function-calling tools (update_field, add/edit/remove_goal) the agent uses to write profile and goal data."""
import json

from study.onboarding import GOAL_FIELDS, is_onboarding_complete
from db.user_store import current_user_id, get_user, mark_onboarding_complete, update_user

_IMMUTABLE_POST_ONBOARDING = {"name", "user_reported_mvpa_mins"}
NUMERIC_FIELDS = {"age", "user_reported_mvpa_mins"}
# Sanity bounds to reject garbage (e.g. age 400), not the study's eligibility criteria (18-64).
_NUMERIC_BOUNDS = {"age": (13, 110), "user_reported_mvpa_mins": (0, 1500)}
# Goals go through add/edit/remove_goal (which keep the slots gap-free), never update_field.
# Wearable-derived fields (mvpa_rolling_7d_total, mvpa_trend) and bookkeeping
# (onboarding_complete, last_updated) are deliberately absent.
_UPDATABLE_FIELDS = sorted({
    "name", "age", "occupation", "user_reported_mvpa_mins", "available_days_times",
    "available_resources", "physical_limitations", "preferred_activities",
    "primary_barrier", "personal_benefit", "why_active", "long_term_vision",
    "past_successes", "additional_info",
    "plan_daily", "plan_goal_1", "plan_goal_2", "plan_goal_3", "plan_notes",
})

MAX_GOALS = 3

# Positionally aligned with GOAL_FIELDS so a goal's plan follows it when _remove_goal shifts
# the remaining goals up to close a gap.
_PLAN_GOAL_FIELDS = ["plan_goal_1", "plan_goal_2", "plan_goal_3"]

LOCAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_field",
            "description": (
                "Save or update one profile field for the participant. Call this once per "
                "distinct fact the user states. Never call this for SMART goals (use "
                "add_goal/edit_goal/remove_goal) or for MVPA/activity-minute data (synced "
                "automatically from the wearable)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": _UPDATABLE_FIELDS},
                    "value": {
                        "type": "string",
                        "description": "The new value as a string; numeric fields are parsed automatically.",
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_goal",
            "description": (
                "Add a new, approved SMART goal. It is placed in the next open slot "
                "automatically — never specify a position. Fails if the participant already "
                "has 3 goals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The full final SMART goal sentence."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_goal",
            "description": (
                "Replace the text of an existing goal. Position is the goal's number as the "
                "participant sees it in the Goals panel (1 for the first goal, 2 for the second, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "position": {"type": "integer", "description": "1-based position of the goal to edit."},
                    "text": {"type": "string", "description": "The new full SMART goal sentence."},
                },
                "required": ["position", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_goal",
            "description": (
                "Delete an existing goal. Position is the goal's number as the participant "
                "sees it in the Goals panel. Remaining goals shift up to close the gap."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "position": {"type": "integer", "description": "1-based position of the goal to remove."},
                },
                "required": ["position"],
            },
        },
    },
]


def _update_field(field: str, value: str) -> dict:
    if field not in _UPDATABLE_FIELDS:
        return {"error": f"Field {field!r} cannot be updated."}

    user_id = current_user_id()
    user_data = get_user(user_id) or {}
    if field in _IMMUTABLE_POST_ONBOARDING and user_data.get("onboarding_complete"):
        return {"error": f"Field {field!r} cannot be changed after onboarding."}

    if field in NUMERIC_FIELDS:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return {"error": f"Field {field!r} requires an integer value, got {value!r}."}
        lo, hi = _NUMERIC_BOUNDS[field]
        if not lo <= value <= hi:
            return {"error": f"{value} is not a plausible value for {field!r} (expected {lo}-{hi})."}
    elif not str(value).strip():
        # A blank reads as unanswered to get_next_onboarding_field, so it would never advance
        # onboarding. Negations must be saved as the literal word ("none", "no"); reject blanks.
        return {"error": f"Field {field!r} cannot be saved as an empty value; use the participant's own word (e.g. 'none', 'no')."}

    update_user(user_id, {field: value})

    merged = {**user_data, field: value}
    if not user_data.get("onboarding_complete") and is_onboarding_complete(merged):
        mark_onboarding_complete(user_id)

    return {"ok": True, "field": field}


def _current_goals(user_data: dict) -> list[str]:
    """The goals as an ordered, gap-free list, ignoring empty slots."""
    return [g for f in GOAL_FIELDS if (g := (user_data.get(f) or "").strip())]


def _write_goals(user_id: str, goals: list[str]) -> None:
    """Repack the list into the three slots so there is never a gap between goals."""
    update_user(user_id, {f: (goals[i] if i < len(goals) else "") for i, f in enumerate(GOAL_FIELDS)})


def _add_goal(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "Goal text is empty."}
    user_id = current_user_id()
    user_data = get_user(user_id) or {}
    goals = _current_goals(user_data)
    if len(goals) >= MAX_GOALS:
        return {"error": f"Already at the maximum of {MAX_GOALS} goals; remove one first."}
    goals.append(text)
    _write_goals(user_id, goals)

    merged = {**user_data, **{f: (goals[i] if i < len(goals) else "") for i, f in enumerate(GOAL_FIELDS)}}
    if not user_data.get("onboarding_complete") and is_onboarding_complete(merged):
        mark_onboarding_complete(user_id)

    return {"ok": True, "position": len(goals)}


def _edit_goal(position, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "Goal text is empty."}
    try:
        position = int(position)
    except (TypeError, ValueError):
        return {"error": f"Position must be a number, got {position!r}."}
    user_id = current_user_id()
    goals = _current_goals(get_user(user_id) or {})
    if not 1 <= position <= len(goals):
        return {"error": f"No goal at position {position}."}
    goals[position - 1] = text
    _write_goals(user_id, goals)
    return {"ok": True, "position": position}


def _remove_goal(position) -> dict:
    try:
        position = int(position)
    except (TypeError, ValueError):
        return {"error": f"Position must be a number, got {position!r}."}
    user_id = current_user_id()
    user_data = get_user(user_id) or {}
    goals = _current_goals(user_data)
    if not 1 <= position <= len(goals):
        return {"error": f"No goal at position {position}."}
    removed = goals.pop(position - 1)
    plans = [user_data.get(f, "") for f in _PLAN_GOAL_FIELDS]
    plans.pop(position - 1)
    _write_goals(user_id, goals)
    update_user(user_id, {f: (plans[i] if i < len(plans) else "") for i, f in enumerate(_PLAN_GOAL_FIELDS)})
    return {"ok": True, "removed": removed}


_LOCAL_HANDLERS = {
    "update_field": lambda args: _update_field(args["field"], args["value"]),
    "add_goal": lambda args: _add_goal(args["text"]),
    "edit_goal": lambda args: _edit_goal(args["position"], args["text"]),
    "remove_goal": lambda args: _remove_goal(args["position"]),
}

LOCAL_TOOL_NAMES = set(_LOCAL_HANDLERS)


def call_local_tool(name: str, arguments: dict) -> str:
    result = _LOCAL_HANDLERS[name](arguments)
    return json.dumps(result)
