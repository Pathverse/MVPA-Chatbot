"""Endpoint-level tests: every chat/wearable endpoint requires a valid Pathverse
participant token, and all storage is keyed by the authenticated participant — never by
deployment-wide state. Firestore is stubbed out before the app modules import it."""
import sys
import types
from unittest.mock import MagicMock

# db/client.py initialises firebase_admin with real credentials at import; stub it before
# any backend module pulls it in.
sys.modules.setdefault("db.client", types.SimpleNamespace(db=MagicMock()))

import pytest
from fastapi.testclient import TestClient

import main
from backend.session import HELP_TEXT
from pathverse_mcp import identity

client = TestClient(main.app)


@pytest.fixture
def as_participant(monkeypatch):
    participant = identity.Participant(user_id="42", token="tok-42")
    monkeypatch.setattr(identity, "resolve_participant", lambda header: participant)
    return participant


def test_session_start_requires_auth():
    response = client.post("/session/start")
    assert response.status_code == 401


def test_session_message_requires_auth():
    response = client.post("/session/message", json={"message": "hi"})
    assert response.status_code == 401


def test_wearable_requires_auth():
    response = client.get("/api/wearable")
    assert response.status_code == 401


def test_invalid_token_gets_401(monkeypatch):
    def deny(header):
        raise identity.AuthError("nope")

    monkeypatch.setattr(identity, "resolve_participant", deny)
    response = client.post(
        "/session/message", json={"message": "hi"}, headers={"Authorization": "Bearer bad"}
    )
    assert response.status_code == 401


def test_message_is_keyed_by_authenticated_participant(monkeypatch, as_participant):
    recorded = []
    monkeypatch.setattr(
        "backend.session.record_exchange", lambda user_id, text, reply: recorded.append(user_id)
    )

    response = client.post(
        "/session/message",
        json={"message": "help me smartbot"},
        headers={"Authorization": "Bearer tok-42"},
    )

    assert response.status_code == 200
    assert response.json()["response"] == HELP_TEXT
    assert recorded == ["42"]


def test_health_is_public():
    # load balancers and uptime checks probe without credentials
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_not_served_by_default():
    # SERVE_FRONTEND is unset in tests; the browser UI has no Pathverse login, so the
    # app must not expose it unless explicitly enabled for local development.
    response = client.get("/")
    assert response.status_code == 404
