"""Mints a short-lived Pathverse MCP access token from the participant's program credentials."""
import requests
from config import MCP_PARTICIPANT_TOKEN, MCP_PROGRAM_ID, MCP_TOKEN_MINT_URL


def mint_mcp_token() -> str:
    resp = requests.post(
        MCP_TOKEN_MINT_URL,
        json={"program_id": MCP_PROGRAM_ID},
        headers={"Authorization": f"Bearer {MCP_PARTICIPANT_TOKEN}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]
