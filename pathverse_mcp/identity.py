"""Resolves the app's Authorization header to a Pathverse participant and carries that
identity through the request via a ContextVar, so deep call sites (MCP client) never
need it threaded through their signatures."""
import time
from contextvars import ContextVar
from dataclasses import dataclass

import requests

from config import PATHVERSE_API_URL

# Pathverse bearer tokens are stable per user, so a short TTL only bounds how long a
# revoked token keeps working here.
_CACHE_TTL_SECONDS = 10 * 60

_cache = {}  # participant token -> (user_id, cached_at)

_current: ContextVar = ContextVar("current_participant")


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Participant:
    user_id: str
    token: str


def resolve_participant(authorization: str | None) -> Participant:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Missing or malformed Authorization header")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise AuthError("Missing or malformed Authorization header")

    cached = _cache.get(token)
    if cached is not None and time.monotonic() - cached[1] < _CACHE_TTL_SECONDS:
        return Participant(user_id=cached[0], token=token)

    resp = requests.get(
        f"{PATHVERSE_API_URL.rstrip('/')}/users/get_user_id/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise AuthError(f"Pathverse rejected the token (status {resp.status_code})")
    try:
        user_id = resp.json()
    except ValueError:
        user_id = None
    # get_user_id returns an empty body for non-participant (admin) users
    if user_id is None or user_id == "":
        raise AuthError("Token does not belong to a participant")

    user_id = str(user_id)
    _cache[token] = (user_id, time.monotonic())
    return Participant(user_id=user_id, token=token)


def set_current(participant: Participant):
    return _current.set(participant)


def reset_current(reset_token):
    _current.reset(reset_token)


def current() -> Participant:
    try:
        return _current.get()
    except LookupError:
        raise AuthError("No participant bound to this request")
