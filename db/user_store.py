"""Firestore read/write access for a participant's profile, goals, wearable summary, and chat transcript."""
from datetime import date as date_cls

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from db.client import db

# Fields cleared by a hard reset (profile, goals, onboarding).
RESETTABLE_FIELDS = {
    "name": "",
    "age": 0,
    "occupation": "",
    "user_reported_mvpa_mins": 0,
    "available_days_times": "",
    "available_resources": "",
    # Starts empty, not "none", so onboarding still asks the question;
    # the user's answer (e.g. "none") is what fills this field in.
    "physical_limitations": "",
    "preferred_activities": "",
    "primary_barrier": "",
    "personal_benefit": "",
    "why_active": "",
    "long_term_vision": "",
    "past_successes": "",
    "additional_info": "",
    "smart_goal_1": "",
    "smart_goal_2": "",
    "smart_goal_3": "",
    "plan_daily": "",
    "plan_goal_1": "",
    "plan_goal_2": "",
    "plan_goal_3": "",
    "plan_notes": "",
    "onboarding_complete": False,
}

DEFAULT_PROFILE = dict(RESETTABLE_FIELDS)

# Cached aggregate, never reset by onboarding — derived from the daily_mvpa
# subcollection by wearable sync, independent of the participant's profile.
DEFAULT_WEARABLE_SUMMARY = {"mvpa_rolling_7d_total": 0, "mvpa_trend": ""}


def _user_ref(user_id):
    return db.collection("users").document(user_id)


# Participant-entered data (profile, goals, onboarding state), kept separate from wearable
# data so each can evolve independently.
def _profile_ref(user_id):
    return _user_ref(user_id).collection("profile").document("data")


def get_user(user_id):
    snap = _profile_ref(user_id).get()
    return snap.to_dict() if snap.exists else None


def create_user(user_id):
    _profile_ref(user_id).set({**DEFAULT_PROFILE, "last_updated": firestore.SERVER_TIMESTAMP})
    _wearable_ref(user_id).set({**DEFAULT_WEARABLE_SUMMARY, "last_updated": firestore.SERVER_TIMESTAMP})


def update_user(user_id, fields):
    _profile_ref(user_id).set({**fields, "last_updated": firestore.SERVER_TIMESTAMP}, merge=True)


def mark_onboarding_complete(user_id):
    update_user(user_id, {"onboarding_complete": True})


def reset_user(user_id):
    update_user(user_id, RESETTABLE_FIELDS)


# Wearable data (rolling total, trend, and the daily/weekly history subcollections below),
# separate from the profile so it can be subdivided independently.
def _wearable_ref(user_id):
    return _user_ref(user_id).collection("wearable").document("summary")


def get_wearable_summary(user_id):
    snap = _wearable_ref(user_id).get()
    return snap.to_dict() if snap.exists else dict(DEFAULT_WEARABLE_SUMMARY)


def _update_wearable_summary(user_id, fields):
    _wearable_ref(user_id).set({**fields, "last_updated": firestore.SERVER_TIMESTAMP}, merge=True)


def _daily_mvpa_ref(user_id):
    return _wearable_ref(user_id).collection("daily_mvpa")


def _day_str(day):
    return day.isoformat() if isinstance(day, date_cls) else day


def write_daily_mvpa(user_id, day, minutes):
    """One document per calendar day — a re-sync of the same day just overwrites it,
    so this is always safe to call again (no stale-field risk, no double-counting)."""
    day_str = _day_str(day)
    _daily_mvpa_ref(user_id).document(day_str).set({
        "date": day_str,
        "minutes": max(int(minutes), 0),
        "synced_at": firestore.SERVER_TIMESTAMP,
    })


def get_daily_mvpa_range(user_id, start_day, end_day):
    """Returns {date_str: minutes} for every daily_mvpa doc in [start_day, end_day]."""
    docs = (
        _daily_mvpa_ref(user_id)
        .where(filter=FieldFilter("date", ">=", _day_str(start_day)))
        .where(filter=FieldFilter("date", "<=", _day_str(end_day)))
        .get()
    )
    return {(rec := d.to_dict())["date"]: rec["minutes"] for d in docs}


def set_rolling_7d_total(user_id, total):
    _update_wearable_summary(user_id, {"mvpa_rolling_7d_total": max(int(total), 0)})


def _weekly_totals_ref(user_id):
    return _wearable_ref(user_id).collection("weekly_totals")


def lock_week_total(user_id, week_start, week_end, total, today):
    """week_start/week_end: 'YYYY-MM-DD' strings. Doc id is the week's Monday date,
    so locking is naturally idempotent and needs no separate week-number bookkeeping.
    Refuses any week not entirely behind `today` (the participant's local date)."""
    if date_cls.fromisoformat(week_end) >= today:
        raise ValueError(f"refusing to lock week {week_start}..{week_end}: not over as of {today}")

    _weekly_totals_ref(user_id).document(week_start).set({
        "week_start": week_start,
        "week_end": week_end,
        "total_minutes": total,
        "locked": True,
    })
    return calculate_and_update_trend(user_id)


def calculate_and_update_trend(user_id):
    locked_weeks = _weekly_totals_ref(user_id).order_by("week_start").get()
    totals = [w.to_dict()["total_minutes"] for w in locked_weeks]

    if len(totals) < 2:
        trend = "insufficient_data"
    else:
        diff = totals[-1] - totals[-2]
        if diff >= 15:
            trend = "improving"
        elif diff <= -15:
            trend = "declining"
        else:
            trend = "stable"

    _update_wearable_summary(user_id, {"mvpa_trend": trend})
    return trend


def get_weekly_totals(user_id):
    docs = _weekly_totals_ref(user_id).order_by("week_start").get()
    return [d.to_dict() for d in docs]


def prune_daily_mvpa(user_id, cutoff_day):
    """Deletes daily_mvpa docs older than cutoff_day, keeping storage bounded to the
    trailing history window."""
    cutoff_str = _day_str(cutoff_day)
    docs = _daily_mvpa_ref(user_id).where(filter=FieldFilter("date", "<", cutoff_str)).get()
    for d in docs:
        d.reference.delete()


def prune_weekly_totals(user_id, cutoff_week_start):
    """Deletes weekly_totals docs (doc id == week_start) older than cutoff_week_start."""
    cutoff_str = _day_str(cutoff_week_start)
    docs = _weekly_totals_ref(user_id).where(filter=FieldFilter("week_start", "<", cutoff_str)).get()
    for d in docs:
        d.reference.delete()


def prune_future_weekly_totals(user_id, this_week_start):
    """Deletes weekly_totals docs at or after the current Monday — weeks that cannot
    legitimately be locked. Returns the deleted week_starts."""
    cutoff_str = _day_str(this_week_start)
    docs = _weekly_totals_ref(user_id).where(filter=FieldFilter("week_start", ">=", cutoff_str)).get()
    deleted = []
    for d in docs:
        deleted.append(d.id)
        d.reference.delete()
    return deleted


def prune_future_daily_mvpa(user_id, today):
    """Deletes daily_mvpa docs dated after today."""
    docs = _daily_mvpa_ref(user_id).where(filter=FieldFilter("date", ">", _day_str(today))).get()
    for d in docs:
        d.reference.delete()


# Full conversation transcript, stored server-side so the browser doesn't carry it (a
# refresh used to lose it entirely).
def _transcript_ref(user_id):
    return _user_ref(user_id).collection("transcripts")


def add_transcript_message(user_id, role, content):
    _transcript_ref(user_id).add({
        "role": role,
        "content": content,
        "created_at": firestore.SERVER_TIMESTAMP,
    })


def record_exchange(user_id, user_text, assistant_text):
    """Store a user message and the assistant's reply as a pair."""
    add_transcript_message(user_id, "user", user_text)
    add_transcript_message(user_id, "assistant", assistant_text)


def clear_transcript(user_id):
    """Deletes the full stored conversation, e.g. on a hard reset — otherwise the
    LLM would keep seeing old conversation content after the profile was wiped."""
    for d in _transcript_ref(user_id).get():
        d.reference.delete()


def get_transcript_history(user_id, limit=None):
    """Returns [{"role": ..., "content": ...}, ...] oldest first, suitable for
    feeding straight into the LLM's messages list. `limit` caps to the most
    recent N messages when given."""
    query = _transcript_ref(user_id).order_by("created_at", direction=firestore.Query.DESCENDING)
    if limit:
        query = query.limit(limit)
    docs = list(query.get())
    docs.reverse()
    return [{"role": (rec := d.to_dict())["role"], "content": rec["content"]} for d in docs]
