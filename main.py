from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.chat import router as chat_router
from backend.goals import router as goals_router
from backend.wearable import router as wearable_router

app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend"), name="frontend")
app.include_router(chat_router)
app.include_router(goals_router, prefix="/api/goals")
app.include_router(wearable_router, prefix="/api/wearable")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")
