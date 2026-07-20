"""Defines and executes the local function-calling tools (update_field, add/edit/remove_goal) the agent uses to write profile and goal data."""
import json
import logging

from study.onboarding import GOAL_FIELDS, is_onboarding_complete
from db.user_store import get_user, mark_onboarding_complete, update_user
from pathverse_mcp import identity, mcp_client

logger = logging.getLogger(__name__)

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

# Pathverse goal id behind each slot (via MCP create_goal), shifted in step with the slots
# so edits always PATCH the app goal the participant is looking at.
_SERVER_ID_FIELDS = ["goal_server_id_1", "goal_server_id_2", "goal_server_id_3"]

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

    user_id = identity.current().user_id
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


def _extract_goal_id(reply_text: str):
    try:
        data = json.loads(reply_text)
    except (TypeError, ValueError):
        return None
    if isinstance(data, dict):
        if isinstance(data.get("id"), int):
            return data["id"]
        inner = data.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("id"), int):
            return inner["id"]
    return None


def _push_goal_to_app(user_id: str, position: int, text: str, server_id=None) -> dict:
    """Write the slot's goal through to the pathverse app (MCP create/update as the
    authenticated participant). The coached goal must survive an MCP outage, so failures
    are reported in the tool result — never raised."""
    try:
        if server_id:
            mcp_client.call_tool("update_goal", {"id": server_id, "title": text})
            logger.info("goal write-through: updated app goal id=%s for slot %s", server_id, position)
            return {}
        reply = mcp_client.call_tool("create_goal", {"title": text})
        new_id = _extract_goal_id(reply)
        if new_id is None:
            logger.warning("create_goal reply had no goal id; slot %s left unmapped: %s", position, reply[:300])
            return {"app_sync": "failed"}
        update_user(user_id, {_SERVER_ID_FIELDS[position - 1]: new_id})
        logger.info("goal write-through: created app goal id=%s for slot %s", new_id, position)
        return {}
    except Exception:
        logger.exception("goal write-through to the app failed for slot %s", position)
        return {"app_sync": "failed"}


def _add_goal(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "Goal text is empty."}
    user_id = identity.current().user_id
    user_data = get_user(user_id) or {}
    goals = _current_goals(user_data)
    if len(goals) >= MAX_GOALS:
        return {"error": f"Already at the maximum of {MAX_GOALS} goals; remove one first."}
    goals.append(text)
    _write_goals(user_id, goals)

    merged = {**user_data, **{f: (goals[i] if i < len(goals) else "") for i, f in enumerate(GOAL_FIELDS)}}
    if not user_data.get("onboarding_complete") and is_onboarding_complete(merged):
        mark_onboarding_complete(user_id)

    sync = _push_goal_to_app(user_id, len(goals), text)
    return {"ok": True, "position": len(goals), **sync}


def _edit_goal(position, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "Goal text is empty."}
    try:
        position = int(position)
    except (TypeError, ValueError):
        return {"error": f"Position must be a number, got {position!r}."}
    user_id = identity.current().user_id
    user_data = get_user(user_id) or {}
    goals = _current_goals(user_data)
    if not 1 <= position <= len(goals):
        return {"error": f"No goal at position {position}."}
    goals[position - 1] = text
    _write_goals(user_id, goals)
    # No mapped app goal (pre-writethrough or an earlier failed sync): create it now.
    server_id = user_data.get(_SERVER_ID_FIELDS[position - 1]) or None
    sync = _push_goal_to_app(user_id, position, text, server_id)
    return {"ok": True, "position": position, **sync}


def _remove_goal(position) -> dict:
    try:
        position = int(position)
    except (TypeError, ValueError):
        return {"error": f"Position must be a number, got {position!r}."}
    user_id = identity.current().user_id
    user_data = get_user(user_id) or {}
    goals = _current_goals(user_data)
    if not 1 <= position <= len(goals):
        return {"error": f"No goal at position {position}."}
    removed = goals.pop(position - 1)
    plans = [user_data.get(f, "") for f in _PLAN_GOAL_FIELDS]
    plans.pop(position - 1)
    server_ids = [user_data.get(f, "") for f in _SERVER_ID_FIELDS]
    removed_server_id = server_ids.pop(position - 1)
    _write_goals(user_id, goals)
    update_user(user_id, {f: (plans[i] if i < len(plans) else "") for i, f in enumerate(_PLAN_GOAL_FIELDS)})
    update_user(user_id, {f: (server_ids[i] if i < len(server_ids) else "") for i, f in enumerate(_SERVER_ID_FIELDS)})
    result = {"ok": True, "removed": removed}
    if removed_server_id:
        # MCP has no delete tool yet, so the app-side goal outlives the coached one.
        result["app_goal_removed"] = False
        result["note"] = "The matching goal still exists in the app; the participant can delete it from the Goals screen."
    return result


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
