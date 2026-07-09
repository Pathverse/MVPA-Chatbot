"""JSON-RPC client for the Pathverse MCP server (tool listing and calls) with proactive JWT re-minting."""
import json
import time

import requests
from config import MCP_URL
from pathverse_mcp.token_client import mint_mcp_token

# The minted JWT is only valid for ~30 minutes and ~50 tool calls (the server was
# designed around single chat sessions staying under 30 minutes). This process is
# long-running across many sessions, so we remint proactively before either limit
# instead of relying on the token minted once at import time.
_TOKEN_TTL_SECONDS = 25 * 60
_TOKEN_MAX_CALLS = 45

_token = None
_token_minted_at = 0.0
_token_call_count = 0


def _headers():
    global _token, _token_minted_at, _token_call_count
    stale = (
        _token is None
        or time.monotonic() - _token_minted_at >= _TOKEN_TTL_SECONDS
        or _token_call_count >= _TOKEN_MAX_CALLS
    )
    if stale:
        _token = mint_mcp_token()
        _token_minted_at = time.monotonic()
        _token_call_count = 0
    _token_call_count += 1
    return {
        "Authorization": f"Bearer {_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def _force_remint():
    global _token
    _token = None


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
