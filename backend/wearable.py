"""FastAPI router exposing the participant's synced wearable MVPA data to the self-monitoring panel."""
import logging

from fastapi import APIRouter, Depends

from backend.auth import require_participant
from db.user_store import get_wearable_summary, get_weekly_totals
from db.wearable_sync import get_current_week_full, get_rolling_7d_daily, sync_wearable_data
from pathverse_mcp.identity import Participant

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
def get_wearable(participant: Participant = Depends(require_participant)):
    user_id = participant.user_id
    try:
        sync_wearable_data(user_id)
    except Exception:
        logger.exception("wearable sync failed; using existing stored data")

    summary = get_wearable_summary(user_id)
    return {
        "rolling_7d_total": summary.get("mvpa_rolling_7d_total", 0),
        "trend": summary.get("mvpa_trend", ""),
        "current_week": get_current_week_full(user_id),
        "rolling_7d_daily": get_rolling_7d_daily(user_id),
        "weekly_totals": get_weekly_totals(user_id),
    }
