"""Coached goals must exist in the pathverse app, not just in the chat: add/edit write
through the MCP goal tools (create_goal/update_goal) as the authenticated participant,
per-slot server ids keep edits mapped, and an MCP outage never loses the coached goal.
The LLM's own toolbox drops the MCP goal write tools so the write-through is the only
path that creates app goals."""
import json
import sys
import types
from unittest.mock import MagicMock

sys.modules.setdefault("db.client", types.SimpleNamespace(db=MagicMock()))

import pytest

from agent import messages, tools
from pathverse_mcp import identity


@pytest.fixture
def store(monkeypatch):
    data = {"onboarding_complete": True}
    monkeypatch.setattr(tools, "get_user", lambda uid: dict(data))
    monkeypatch.setattr(tools, "update_user", lambda uid, fields: data.update(fields))
    monkeypatch.setattr(tools, "mark_onboarding_complete", lambda uid: data.update({"onboarding_complete": True}))
    reset = identity.set_current(identity.Participant(user_id="42", token="tok-42"))
    yield data
    identity.reset_current(reset)


@pytest.fixture
def mcp(monkeypatch):
    calls = []

    def fake_call(name, args):
        calls.append((name, args))
        if name == "create_goal":
            return json.dumps({"id": 700 + len(calls), "goal_title": args["title"]})
        return json.dumps({"ok": True})

    monkeypatch.setattr(tools.mcp_client, "call_tool", fake_call)
    return calls


def _local(name, args):
    return json.loads(tools.call_local_tool(name, args))


def test_add_goal_creates_app_goal_and_stores_server_id(store, mcp):
    result = _local("add_goal", {"text": "Walk 30 minutes, 5 days a week"})

    assert result["ok"] is True
    assert mcp == [("create_goal", {"title": "Walk 30 minutes, 5 days a week"})]
    assert store["smart_goal_1"] == "Walk 30 minutes, 5 days a week"
    assert store["goal_server_id_1"] == 701


def test_add_goal_survives_mcp_outage(store, monkeypatch):
    def boom(name, args):
        raise RuntimeError("mcp down")

    monkeypatch.setattr(tools.mcp_client, "call_tool", boom)

    result = _local("add_goal", {"text": "Cycle twice a week"})

    assert result["ok"] is True                      # the coached goal is never lost
    assert result["app_sync"] == "failed"            # but the LLM can tell the user
    assert store["smart_goal_1"] == "Cycle twice a week"


def test_edit_goal_updates_the_mapped_app_goal(store, mcp):
    store.update({"smart_goal_1": "Walk 30 minutes", "goal_server_id_1": 555})

    result = _local("edit_goal", {"position": 1, "text": "Walk 45 minutes"})

    assert result["ok"] is True
    assert mcp == [("update_goal", {"id": 555, "title": "Walk 45 minutes"})]


def test_edit_goal_backfills_app_goal_when_id_missing(store, mcp):
    store.update({"smart_goal_1": "Walk 30 minutes"})   # pre-writethrough goal, no id

    result = _local("edit_goal", {"position": 1, "text": "Walk 45 minutes"})

    assert result["ok"] is True
    assert mcp == [("create_goal", {"title": "Walk 45 minutes"})]
    assert store["goal_server_id_1"] == 701


def test_remove_goal_shifts_server_ids_and_flags_app_leftover(store, mcp):
    store.update(
        {
            "smart_goal_1": "Goal A", "goal_server_id_1": 111,
            "smart_goal_2": "Goal B", "goal_server_id_2": 222,
        }
    )

    result = _local("remove_goal", {"position": 1})

    assert result["ok"] is True
    assert result["app_goal_removed"] is False       # MCP has no delete tool yet
    assert store["smart_goal_1"] == "Goal B"
    assert store["goal_server_id_1"] == 222
    assert store["goal_server_id_2"] == ""


def test_llm_toolbox_excludes_mcp_goal_write_tools(monkeypatch):
    mcp_tools = [
        {"type": "function", "function": {"name": n, "description": "", "parameters": {}}}
        for n in ["get_phi", "get_intent", "create_goal", "update_goal", "list_goals"]
    ]
    monkeypatch.setattr(messages.mcp_client, "list_tools", lambda: list(mcp_tools))
    messages._all_tools_cache = None
    try:
        names = {t["function"]["name"] for t in messages._all_tools()}
    finally:
        messages._all_tools_cache = None

    assert "create_goal" not in names and "update_goal" not in names
    assert {"get_phi", "get_intent", "list_goals", "add_goal"} <= names
