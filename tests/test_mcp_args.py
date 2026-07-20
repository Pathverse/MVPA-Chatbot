"""The MCP get_phi schema demands strict ISO-8601 UTC ("...Z"), but the model writes
dates however it likes ("2026-07-19", no zone, or a local offset). Normalize its
arguments instead of letting the call fail validation."""
import sys
import types
from unittest.mock import MagicMock

sys.modules.setdefault("db.client", types.SimpleNamespace(db=MagicMock()))

import pytest

from agent.mcp_args import normalize_mcp_arguments


def _phi(frm, to):
    return {"payloads": [{"key": "k", "type": "mvpa", "from": frm, "to": to}]}


def _span(args):
    p = args["payloads"][0]
    return p["from"], p["to"]


def test_date_only_becomes_a_full_utc_day_span():
    args = normalize_mcp_arguments("get_phi", _phi("2026-07-19", "2026-07-19"))
    # a bare date must cover the whole day, or "yesterday" would query an empty instant
    assert _span(args) == ("2026-07-19T00:00:00Z", "2026-07-19T23:59:59Z")


def test_naive_datetime_is_treated_as_utc():
    args = normalize_mcp_arguments("get_phi", _phi("2026-07-19T10:30:00", "2026-07-19T11:00:00"))
    assert _span(args) == ("2026-07-19T10:30:00Z", "2026-07-19T11:00:00Z")


def test_offset_datetime_is_converted_to_utc():
    args = normalize_mcp_arguments("get_phi", _phi("2026-07-19T00:00:00-07:00", "2026-07-19T23:59:59-07:00"))
    assert _span(args) == ("2026-07-19T07:00:00Z", "2026-07-20T06:59:59Z")


def test_already_valid_utc_is_untouched():
    args = normalize_mcp_arguments("get_phi", _phi("2026-07-19T00:00:00Z", "2026-07-20T00:00:00Z"))
    assert _span(args) == ("2026-07-19T00:00:00Z", "2026-07-20T00:00:00Z")


def test_unparseable_value_is_left_for_the_server_to_reject():
    args = normalize_mcp_arguments("get_phi", _phi("last tuesday", "2026-07-19"))
    assert _span(args)[0] == "last tuesday"


def test_other_tools_and_shapes_pass_through_unchanged():
    assert normalize_mcp_arguments("get_intent", {}) == {}
    assert normalize_mcp_arguments("get_phi", {"payloads": "nonsense"}) == {"payloads": "nonsense"}
    assert normalize_mcp_arguments("list_goals", {"from": "2026-07-19"}) == {"from": "2026-07-19"}


def test_original_arguments_are_not_mutated():
    original = _phi("2026-07-19", "2026-07-19")
    normalize_mcp_arguments("get_phi", original)
    assert original["payloads"][0]["from"] == "2026-07-19"


def test_tool_call_path_normalizes_before_reaching_mcp(monkeypatch):
    """The model's raw arguments must never hit the MCP unnormalized."""
    import json

    from agent import messages

    sent = {}

    def fake_call_tool(name, arguments):
        sent["name"], sent["arguments"] = name, arguments
        return "{}"

    monkeypatch.setattr(messages.mcp_client, "call_tool", fake_call_tool)

    call = types.SimpleNamespace(
        function=types.SimpleNamespace(
            name="get_phi",
            arguments=json.dumps(_phi("2026-07-19", "2026-07-19")),
        )
    )
    messages._run_tool_call(call, False, None)

    assert _span(sent["arguments"]) == ("2026-07-19T00:00:00Z", "2026-07-19T23:59:59Z")
