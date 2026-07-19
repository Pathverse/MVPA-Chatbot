"""Mints a short-lived Pathverse MCP access token from a participant's own credentials."""
import requests

from config import MCP_PROGRAM_ID, MCP_TOKEN_MINT_URL


def mint_mcp_token(participant_token: str) -> str:
    resp = requests.post(
        MCP_TOKEN_MINT_URL,
        json={"program_id": MCP_PROGRAM_ID},
        headers={"Authorization": f"Bearer {participant_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]
