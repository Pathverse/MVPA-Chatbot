import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MCP_TOKEN = os.getenv("MCP_TOKEN")
MCP_URL = os.getenv("MCP_URL", "https://mcp-appbuilder.pathverse.ca/api/mcp")
LLM_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.7   # conversational warmth without veering off-topic
LLM_TOP_P = 0.9         # broad vocabulary while staying coherent
MAX_HISTORY_TURNS = 50

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in .env")
if not MCP_TOKEN:
    raise RuntimeError("MCP_TOKEN is not set in .env")
if not MCP_URL:
    raise RuntimeError("MCP_URL is not set in .env")
