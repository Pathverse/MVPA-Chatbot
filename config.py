"""Loads and validates the app's environment configuration (API keys, MCP endpoints, LLM settings), failing fast at startup if anything required is missing."""
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
MCP_PROGRAM_ID = os.getenv("MCP_PROGRAM_ID")
MCP_TOKEN_MINT_URL = os.getenv("MCP_TOKEN_MINT_URL")
MCP_URL = os.getenv("MCP_URL")
PATHVERSE_API_URL = os.getenv("PATHVERSE_API_URL")
# The browser UI has no Pathverse login, so it only makes sense in local development.
SERVE_FRONTEND = os.getenv("SERVE_FRONTEND", "").lower() in ("1", "true", "yes")
LLM_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.7   # conversational warmth without veering off-topic
LLM_TOP_P = 0.9         # broad vocabulary while staying coherent
MAX_HISTORY_TURNS = 10  # past user+assistant turn pairs fed to the LLM as chat history
TREND_HISTORY_WEEKS = 16  # how many trailing completed weeks are kept/shown for the self-monitoring trend

# Only the values without a default above can actually be missing.
for _name in ("OPENAI_API_KEY", "MCP_PROGRAM_ID", "MCP_TOKEN_MINT_URL", "MCP_URL", "PATHVERSE_API_URL"):
    if not globals()[_name]:
        raise RuntimeError(f"{_name} is not set in .env")

if not os.path.isfile(GOOGLE_APPLICATION_CREDENTIALS):
    raise RuntimeError(f"GOOGLE_APPLICATION_CREDENTIALS file not found: {GOOGLE_APPLICATION_CREDENTIALS}")
