from fastapi import APIRouter
from goals.goal import list_goals, Goal

router = APIRouter()


@router.get("", response_model=list[Goal])
def get_goals():
    return list_goals()
