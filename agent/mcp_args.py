"""Normalizes the model's MCP tool arguments to what the server's schema demands.

get_phi's `from`/`to` are validated as strict ISO-8601 UTC (a trailing "Z"), but the model
writes dates the way a person would — "2026-07-19", no timezone, or a local offset — and
the call fails validation before it ever reaches the data. Repair what is unambiguous and
leave anything unparseable for the server to reject."""
import logging
from datetime import date, datetime, time, timezone

logger = logging.getLogger(__name__)

_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _normalize_instant(value, *, end_of_day: bool):
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return value

    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        parsed = None
    if parsed is not None:
        # A bare date means the whole day: an empty instant would return no rows.
        boundary = time.max.replace(microsecond=0) if end_of_day else time.min
        return datetime.combine(parsed, boundary, tzinfo=timezone.utc).strftime(_UTC_FORMAT)

    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.info("leaving unparseable MCP datetime %r for the server to reject", value)
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(_UTC_FORMAT)


def normalize_mcp_arguments(name: str, arguments: dict) -> dict:
    """Return a copy of `arguments` with get_phi's payload spans coerced to UTC."""
    if name != "get_phi" or not isinstance(arguments, dict):
        return arguments
    payloads = arguments.get("payloads")
    if not isinstance(payloads, list):
        return arguments

    normalized = []
    for payload in payloads:
        if not isinstance(payload, dict):
            normalized.append(payload)
            continue
        repaired = dict(payload)
        if "from" in repaired:
            repaired["from"] = _normalize_instant(repaired["from"], end_of_day=False)
        if "to" in repaired:
            repaired["to"] = _normalize_instant(repaired["to"], end_of_day=True)
        normalized.append(repaired)
    return {**arguments, "payloads": normalized}
