from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

MAX_GOALS = 3


class Goal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_goals: list[Goal] = []


def list_goals() -> list[Goal]:
    return list(_goals)


def save_goal(text: str) -> dict:
    if len(_goals) >= MAX_GOALS:
        return {"error": f"Maximum of {MAX_GOALS} goals reached. Delete one before adding another."}
    goal = Goal(text=text)
    _goals.append(goal)
    return {"ok": True, "id": goal.id}


def delete_goal(id: str) -> dict:
    for i, g in enumerate(_goals):
        if g.id == id:
            _goals.pop(i)
            return {"ok": True}
    return {"error": f"Goal {id!r} not found."}


def update_goal(id: str, text: str) -> dict:
    for g in _goals:
        if g.id == id:
            g.text = text
            return {"ok": True}
    return {"error": f"Goal {id!r} not found."}
