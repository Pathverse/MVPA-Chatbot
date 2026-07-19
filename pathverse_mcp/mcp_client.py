"""JSON-RPC client for the Pathverse MCP server (tool listing and calls) with proactive
JWT re-minting, one minted session per participant.

The participant comes from the request-bound identity (pathverse_mcp.identity), so the
deep call sites in agent/ and db/ never pass credentials explicitly."""
import json
import time

import requests

from config import MCP_URL
from pathverse_mcp import identity
from pathverse_mcp.token_client import mint_mcp_token

# A minted JWT is only valid for ~30 minutes and ~50 tool calls (the MCP server was
# designed around single chat sessions staying under 30 minutes). Sessions here span
# many chats, so we remint proactively before either limit.
_TOKEN_TTL_SECONDS = 25 * 60
_TOKEN_MAX_CALLS = 45

_sessions = {}  # participant token -> {"jwt": str, "minted_at": float, "calls": int}


def _headers():
    participant = identity.current()
    session = _sessions.get(participant.token)
    stale = (
        session is None
        or time.monotonic() - session["minted_at"] >= _TOKEN_TTL_SECONDS
        or session["calls"] >= _TOKEN_MAX_CALLS
    )
    if stale:
        session = {
            "jwt": mint_mcp_token(participant.token),
            "minted_at": time.monotonic(),
            "calls": 0,
        }
        _sessions[participant.token] = session
    session["calls"] += 1
    return {
        "Authorization": f"Bearer {session['jwt']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def _force_remint():
    _sessions.pop(identity.current().token, None)


def _rpc(method: str, params: dict = None) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    resp = requests.post(MCP_URL, json=body, headers=_headers(), timeout=10)
    if resp.status_code in (401, 403):
        # Token expired/was revoked earlier than our proactive schedule expected —
        # remint once and retry before giving up.
        _force_remint()
        resp = requests.post(MCP_URL, json=body, headers=_headers(), timeout=10)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        data = None
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
                break
        if data is None:
            raise RuntimeError(f"No SSE data line in MCP response: {resp.text!r}")
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data["result"]


def list_tools() -> list:
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}}
        for t in _rpc("tools/list")["tools"]
    ]


def call_tool(name: str, arguments: dict) -> str:
    result = _rpc("tools/call", {"name": name, "arguments": arguments})
    texts = [item["text"] for item in result.get("content", []) if item.get("type") == "text"]
    text = "\n".join(texts) if texts else json.dumps(result)
    if result.get("isError"):
        raise RuntimeError(f"MCP tool '{name}' returned an error: {text}")
    return text
