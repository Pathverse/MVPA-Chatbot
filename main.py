"""FastAPI application entry point that wires up the routers and serves the frontend."""
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.session import router as session_router
from backend.wearable import router as wearable_router
from config import SERVE_FRONTEND

logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.include_router(session_router, prefix="/session")
app.include_router(wearable_router, prefix="/api/wearable")

# The browser UI has no Pathverse login, so it is opt-in for local development only;
# the Pathverse app talks straight to the API routes.
if SERVE_FRONTEND:
    app.mount("/static", StaticFiles(directory="frontend"), name="frontend")

    @app.get("/")
    def index():
        return FileResponse("frontend/index.html")
