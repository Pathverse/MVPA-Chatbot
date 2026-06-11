import json
import requests
from config import MCP_TOKEN, MCP_URL

_headers = {
    "Authorization": f"Bearer {MCP_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _rpc(method: str, params: dict = None) -> dict:
    resp = requests.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=_headers,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
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
    return "\n".join(texts) if texts else json.dumps(result)
