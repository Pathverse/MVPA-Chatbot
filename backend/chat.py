import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from agent.messages import process_message

router = APIRouter()


@router.websocket("/ws/chat")
async def chat(ws: WebSocket):
    await ws.accept()
    history: list = []
    try:
        while True:
            data = json.loads(await ws.receive_text())
            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            reply, goal_mutated = await asyncio.to_thread(process_message, user_text, history)

            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": reply})

            if goal_mutated:
                await ws.send_text(json.dumps({"type": "goal_saved"}))
            await ws.send_text(json.dumps({"type": "message", "text": reply}))
    except WebSocketDisconnect:
        pass
