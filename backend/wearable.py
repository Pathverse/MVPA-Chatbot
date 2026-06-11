import json
from datetime import timedelta, timezone, datetime

from fastapi import APIRouter, HTTPException
from mcp import mcp_client

router = APIRouter()

_DATA_TYPES = ["mvpa", "steps", "hrv", "ema"]


@router.get("")
def get_wearable():
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    today_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    payloads = [
        {"key": t, "type": t, "from": week_ago, "to": today_str}
        for t in _DATA_TYPES
    ]
    try:
        raw = mcp_client.call_tool("get_phi", {"payloads": payloads})
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = raw
    return {"data": parsed, "from": week_ago[:10], "to": today_str[:10]}
