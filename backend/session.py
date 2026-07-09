"""FastAPI router for the chat/onboarding endpoints — the web surface that drives each conversation turn plus the reset/help/onboard command phrases."""
import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from agent.messages import process_message
from config import MAX_HISTORY_TURNS
from study.onboarding import get_next_onboarding_field, goal_slots, is_onboarding_complete, opening_question
from study.context import build_user_context
from db.user_store import (
    add_transcript_message,
    clear_transcript,
    create_user,
    current_user_id,
    get_transcript_history,
    get_user,
    get_wearable_summary,
    get_weekly_totals,
    record_exchange,
    reset_user,
)
from db.wearable_sync import get_current_week_daily_mvpa, sync_wearable_data

logger = logging.getLogger(__name__)

router = APIRouter()

RESET_PHRASE = "Hard-reset-123456789"
ONBOARD_PHRASE = "please help me onboard to the smartbot study"
HELP_PHRASE = "help me smartbot"

HELP_TEXT = (
    "I'm SMARTBot, your physical activity coach. Here's how I can help:\n\n"
    "- Set and track SMART goals for being more active\n"
    "- Review your activity data and see how your week is going\n"
    "- Talk through what's getting in the way and plan around it\n"
    "- Build a day-to-day plan for your goals and pick up where you left off next time\n\n"
    "Just tell me what you'd like to work on, for example \"help me set a new goal\" "
    "or \"how did my week look?\""
)


class MessageIn(BaseModel):
    message: str


def _get_or_create_user():
    user_id = current_user_id()
    user_data = get_user(user_id)
    if user_data is None:
        create_user(user_id)
        user_data = get_user(user_id)
    return user_data


def _with_wearable_summary(user_id, user_data):
    """build_user_context/process_message expect rolling total + trend alongside
    profile fields, but those now live in a separate wearable/summary doc."""
    return {**user_data, **get_wearable_summary(user_id)}


@router.post("/start")
def start_session():
    user_id = current_user_id()
    user_data = _get_or_create_user()

    try:
        sync_wearable_data(user_id)
        user_data = get_user(user_id)
    except Exception:
        logger.exception("wearable sync failed; using existing stored data")

    if not is_onboarding_complete(user_data):
        next_field, question = opening_question(user_data)
        # Record the opening question once, on a brand-new user's very first load —
        # otherwise every page refresh before it's answered would re-save it.
        if not get_transcript_history(user_id, limit=1):
            add_transcript_message(user_id, "assistant", question)
        return {
            "onboarding_complete": False,
            "next_field": next_field,
            "question": question,
        }

    weekly_totals = get_weekly_totals(user_id)
    daily_mvpa = get_current_week_daily_mvpa(user_id)
    return {
        "onboarding_complete": True,
        "name": user_data.get("name", ""),
        "system_prompt": build_user_context(_with_wearable_summary(user_id, user_data), weekly_totals, daily_mvpa),
        "smart_goals": goal_slots(user_data),
    }


@router.post("/message")
async def send_message(body: MessageIn):
    user_id = current_user_id()
    text = body.message.strip()

    if text == RESET_PHRASE:
        reset_user(user_id)
        clear_transcript(user_id)
        _, question = opening_question(get_user(user_id))
        response = f"Your profile has been cleared. You can restart onboarding.\n\n{question}"
        record_exchange(user_id, text, response)
        return {"response": response, "field_updated": True, "onboarding_complete": False}

    if text.lower() == HELP_PHRASE:
        record_exchange(user_id, text, HELP_TEXT)
        return {"response": HELP_TEXT, "field_updated": False}

    user_data = _get_or_create_user()

    if text.lower() == ONBOARD_PHRASE:
        if is_onboarding_complete(user_data):
            response = "You've already completed onboarding for the SMARTBot study."
            record_exchange(user_id, text, response)
            return {"response": response, "field_updated": False}
        _, question = opening_question(user_data)
        response = f"Sure, let's get you onboarded to the SMARTBot study.\n\n{question}"
        record_exchange(user_id, text, response)
        return {"response": response, "field_updated": False, "onboarding_complete": False}

    onboarded = is_onboarding_complete(user_data)
    weekly_totals = get_weekly_totals(user_id) if onboarded else []
    daily_mvpa = get_current_week_daily_mvpa(user_id) if onboarded else {}
    next_field = get_next_onboarding_field(user_data)
    history = get_transcript_history(user_id, limit=MAX_HISTORY_TURNS * 2)

    reply, field_updated = await asyncio.to_thread(
        process_message, text, history, _with_wearable_summary(user_id, user_data),
        weekly_totals, daily_mvpa, next_field
    )

    record_exchange(user_id, text, reply)

    if field_updated:
        user_data = get_user(user_id)

    return {
        "response": reply,
        "field_updated": field_updated,
        "onboarding_complete": user_data.get("onboarding_complete", False),
        "smart_goals": goal_slots(user_data),
    }
