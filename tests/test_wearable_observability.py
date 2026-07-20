"""A silent journal must not be ambiguous: the MVPA fetch logs the span it asked for and
what came back, so "sync ran and the server has no rows" is distinguishable from "sync
never ran" when debugging a live deployment."""
import json
import logging
import sys
import types
from datetime import date
from unittest.mock import MagicMock

sys.modules.setdefault("db.client", types.SimpleNamespace(db=MagicMock()))

import pytest

from db import wearable_sync


def test_logs_span_and_day_count_when_rows_returned(monkeypatch, caplog):
    monkeypatch.setattr(
        wearable_sync.mcp_client,
        "call_tool",
        lambda name, args: json.dumps({"mvpa_0": [{"date": "2026-07-19", "minutes": 25}]}),
    )

    with caplog.at_level(logging.INFO, logger="db.wearable_sync"):
        result = wearable_sync._fetch_mvpa_minutes_by_day(date(2026, 7, 14), date(2026, 7, 20))

    assert result == {date(2026, 7, 19): 25}
    message = caplog.text
    assert "2026-07-14" in message and "2026-07-20" in message
    assert "1 day" in message and "25" in message


def test_logs_explicitly_when_server_returns_no_rows(monkeypatch, caplog):
    monkeypatch.setattr(
        wearable_sync.mcp_client, "call_tool", lambda name, args: json.dumps({"mvpa_0": []})
    )

    with caplog.at_level(logging.INFO, logger="db.wearable_sync"):
        result = wearable_sync._fetch_mvpa_minutes_by_day(date(2026, 7, 14), date(2026, 7, 20))

    assert result == {}
    assert "no MVPA rows" in caplog.text
