"""FastAPI application entry point that wires up the routers and serves the frontend."""
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.session import router as session_router
from backend.wearable import router as wearable_router

logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend"), name="frontend")
app.include_router(session_router, prefix="/session")
app.include_router(wearable_router, prefix="/api/wearable")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")
