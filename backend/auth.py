"""FastAPI dependency that turns the app's Authorization header into an authenticated
Pathverse participant and binds it to the request context for the MCP client."""
from fastapi import HTTPException, Request

from pathverse_mcp import identity


async def require_participant(request: Request) -> identity.Participant:
    try:
        participant = identity.resolve_participant(request.headers.get("Authorization"))
    except identity.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    identity.set_current(participant)
    return participant
