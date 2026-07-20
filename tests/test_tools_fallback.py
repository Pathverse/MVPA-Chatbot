"""The LLM turn must not die when the MCP server is unreachable — tool listing degrades
to the local (profile/goal) tools and retries MCP on the next turn instead of caching
the failure or poisoning the cache."""
import sys
import types
from unittest.mock import MagicMock

# db/client.py initialises firebase_admin at import; stub before agent.messages pulls it in.
sys.modules.setdefault("db.client", types.SimpleNamespace(db=MagicMock()))

import pytest

from agent import messages
from agent.tools import LOCAL_TOOLS


@pytest.fixture(autouse=True)
def reset_tools_cache():
    messages._all_tools_cache = None
    yield
    messages._all_tools_cache = None


def test_falls_back_to_local_tools_when_mcp_unreachable(monkeypatch):
    def boom():
        raise RuntimeError("mcp down")

    monkeypatch.setattr(messages.mcp_client, "list_tools", boom)

    assert messages._all_tools() == LOCAL_TOOLS


def test_mcp_failure_is_not_cached_and_recovers(monkeypatch):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("mcp down")
        return [{"type": "function", "function": {"name": "get_phi"}}]

    monkeypatch.setattr(messages.mcp_client, "list_tools", flaky)

    assert messages._all_tools() == LOCAL_TOOLS          # first turn degrades
    recovered = messages._all_tools()                     # second turn retries MCP
    assert len(recovered) == len(LOCAL_TOOLS) + 1
    messages._all_tools()                                 # third turn hits the cache
    assert len(calls) == 2
