"""Tests for pathverse_mcp/identity.py — resolving the app's Authorization header to a
Pathverse participant via GET /users/get_user_id/, with caching and hard failure on
invalid tokens."""
import pytest

from pathverse_mcp import identity


class FakeResponse:
    def __init__(self, status_code, body=""):
        self.status_code = status_code
        self._body = body

    def json(self):
        import json

        return json.loads(self._body)


@pytest.fixture(autouse=True)
def clear_cache():
    identity._cache.clear()
    yield
    identity._cache.clear()


def test_missing_or_malformed_header_rejected():
    for header in [None, "", "Basic abc123", "Bearer", "Bearer "]:
        with pytest.raises(identity.AuthError):
            identity.resolve_participant(header)


def test_resolves_user_id_via_pathverse(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return FakeResponse(200, "17")

    monkeypatch.setattr(identity.requests, "get", fake_get)

    participant = identity.resolve_participant("Bearer tok-1")

    assert participant.user_id == "17"
    assert participant.token == "tok-1"
    assert calls == [
        ("https://pv.example.com/users/get_user_id/", {"Authorization": "Bearer tok-1"})
    ] or calls[0][0] == "https://pv.example.com/users/get_user_id/"
    assert calls[0][1]["Authorization"] == "Bearer tok-1"


def test_resolution_is_cached_per_token(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(200, "17")

    monkeypatch.setattr(identity.requests, "get", fake_get)

    identity.resolve_participant("Bearer tok-1")
    identity.resolve_participant("Bearer tok-1")

    assert len(calls) == 1


def test_invalid_token_raises_and_is_not_cached(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(401, "")

    monkeypatch.setattr(identity.requests, "get", fake_get)

    with pytest.raises(identity.AuthError):
        identity.resolve_participant("Bearer bad-token")
    assert "bad-token" not in identity._cache


def test_non_participant_token_raises(monkeypatch):
    # /users/get_user_id/ returns an empty 200 for admin (non-participant) users
    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(200, "")

    monkeypatch.setattr(identity.requests, "get", fake_get)

    with pytest.raises(identity.AuthError):
        identity.resolve_participant("Bearer admin-token")


def test_current_participant_contextvar_roundtrip():
    participant = identity.Participant(user_id="42", token="tok-42")
    reset_token = identity.set_current(participant)
    try:
        assert identity.current() is participant
    finally:
        identity.reset_current(reset_token)
    with pytest.raises(identity.AuthError):
        identity.current()
