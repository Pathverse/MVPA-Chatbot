"""Hermetic test environment: config.py validates env at import, so dummy values are
installed before any project module loads. No network, no real Firebase credentials."""
import os
import tempfile

_dummy_creds = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
_dummy_creds.write(b"{}")
_dummy_creds.close()

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", _dummy_creds.name)
os.environ.setdefault("MCP_PROGRAM_ID", "1")
os.environ.setdefault("MCP_TOKEN_MINT_URL", "https://mint.example.com/token")
os.environ.setdefault("MCP_URL", "https://mcp.example.com/rpc")
os.environ.setdefault("PATHVERSE_API_URL", "https://pv.example.com")
