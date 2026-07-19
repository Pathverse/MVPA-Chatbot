"""Tests for per-participant MCP credentials: token minting takes the participant's own
token, and the MCP client keeps one minted-JWT session per participant (keyed off the
request-bound identity) instead of module-global state."""
import pytest

from pathverse_mcp import identity, mcp_client, token_client


@pytest.fixture(autouse=True)
def clear_sessions():
    mcp_client._sessions.clear()
    yield
    mcp_client._sessions.clear()


def _bind(user_id, token):
    return identity.set_current(identity.Participant(user_id=user_id, token=token))


def test_mint_uses_the_given_participant_token(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"token": "jwt-abc"}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return FakeResponse()

    monkeypatch.setattr(token_client.requests, "post", fake_post)

    jwt = token_client.mint_mcp_token("participant-tok")

    assert jwt == "jwt-abc"
    assert calls[0][2]["Authorization"] == "Bearer participant-tok"
    assert calls[0][1] == {"program_id": "1"}


def test_headers_mint_one_session_per_participant(monkeypatch):
    minted = []

    def fake_mint(participant_token):
        minted.append(participant_token)
        return f"jwt-for-{participant_token}"

    monkeypatch.setattr(mcp_client, "mint_mcp_token", fake_mint)

    reset = _bind("1", "tok-A")
    try:
        headers_a = mcp_client._headers()
        headers_a_again = mcp_client._headers()
    finally:
        identity.reset_current(reset)

    reset = _bind("2", "tok-B")
    try:
        headers_b = mcp_client._headers()
    finally:
        identity.reset_current(reset)

    reset = _bind("1", "tok-A")
    try:
        headers_a_third = mcp_client._headers()
    finally:
        identity.reset_current(reset)

    assert headers_a["Authorization"] == "Bearer jwt-for-tok-A"
    assert headers_a_again["Authorization"] == "Bearer jwt-for-tok-A"
    assert headers_b["Authorization"] == "Bearer jwt-for-tok-B"
    assert headers_a_third["Authorization"] == "Bearer jwt-for-tok-A"
    # one mint per participant, not per call
    assert minted == ["tok-A", "tok-B"]


def test_headers_remints_after_call_budget(monkeypatch):
    minted = []

    def fake_mint(participant_token):
        minted.append(participant_token)
        return f"jwt-{len(minted)}"

    monkeypatch.setattr(mcp_client, "mint_mcp_token", fake_mint)

    reset = _bind("1", "tok-A")
    try:
        for _ in range(mcp_client._TOKEN_MAX_CALLS + 1):
            mcp_client._headers()
    finally:
        identity.reset_current(reset)

    assert minted == ["tok-A", "tok-A"]


def test_headers_without_bound_participant_raises():
    with pytest.raises(identity.AuthError):
        mcp_client._headers()


def test_force_remint_only_clears_current_participant(monkeypatch):
    monkeypatch.setattr(mcp_client, "mint_mcp_token", lambda tok: f"jwt-{tok}")

    reset = _bind("1", "tok-A")
    try:
        mcp_client._headers()
    finally:
        identity.reset_current(reset)

    reset = _bind("2", "tok-B")
    try:
        mcp_client._headers()
        mcp_client._force_remint()
    finally:
        identity.reset_current(reset)

    assert "tok-A" in mcp_client._sessions
    assert "tok-B" not in mcp_client._sessions
