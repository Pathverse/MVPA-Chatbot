"""Pulls Apple Health MVPA via MCP and syncs it into Firestore — daily minutes, locked weekly totals, trend, and history pruning."""
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from pathverse_mcp import mcp_client

from config import TREND_HISTORY_WEEKS

logger = logging.getLogger(__name__)
from db.user_store import (
    calculate_and_update_trend,
    get_daily_mvpa_range,
    get_weekly_totals,
    lock_week_total,
    prune_daily_mvpa,
    prune_future_daily_mvpa,
    prune_future_weekly_totals,
    prune_weekly_totals,
    set_rolling_7d_total,
    write_daily_mvpa,
)

# All "today"/"this week" boundaries are computed in the participant's local time
# (Pacific), not UTC — otherwise a late-night workout can land on the wrong calendar day.
PACIFIC = ZoneInfo("America/Los_Angeles")


def today_pacific():
    return datetime.now(PACIFIC).date()


def _pacific_day_bounds_utc(local_day):
    """The UTC instants marking the start and end of a Pacific calendar day."""
    start = datetime.combine(local_day, time.min, tzinfo=PACIFIC).astimezone(timezone.utc)
    end = datetime.combine(local_day, time.max, tzinfo=PACIFIC).astimezone(timezone.utc)
    return start, end


# The MCP API rejects an "mvpa" request spanning more than this many days.
_MAX_RANGE_DAYS = 14


def _fetch_mvpa_minutes_by_day(start_day, end_day):
    """{pacific_date: total_minutes} for [start_day, end_day] inclusive. Splits into
    <= _MAX_RANGE_DAYS-day spans (the API's per-request cap) but sends them as separate
    payloads in one get_phi call, since the rate limit is charged per call, not per payload."""
    payloads = []
    chunk_start = start_day
    while chunk_start <= end_day:
        chunk_end = min(chunk_start + timedelta(days=_MAX_RANGE_DAYS - 1), end_day)
        range_start, _ = _pacific_day_bounds_utc(chunk_start)
        _, range_end = _pacific_day_bounds_utc(chunk_end)
        payloads.append({
            "key": f"mvpa_{len(payloads)}", "type": "mvpa",
            "from": range_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": range_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        chunk_start = chunk_end + timedelta(days=1)

    raw = mcp_client.call_tool("get_phi", {"payloads": payloads})
    response = json.loads(raw)

    minutes_by_day = {}
    for payload in payloads:
        for rec in response.get(payload["key"], []):
            rec_day = date.fromisoformat(rec["date"])
            minutes_by_day[rec_day] = minutes_by_day.get(rec_day, 0) + int(rec.get("minutes", 0))

    # Logged either way: silence here would leave "the study has no data for this
    # participant" indistinguishable from "the sync never ran" when debugging live.
    if minutes_by_day:
        logger.info(
            "MVPA fetch %s..%s returned %d day(s), %d min total",
            start_day, end_day, len(minutes_by_day), sum(minutes_by_day.values()),
        )
    else:
        logger.info("MVPA fetch %s..%s returned no MVPA rows", start_day, end_day)
    return minutes_by_day


def sync_current_week(user_id, today=None):
    """Writes this week's (Monday..today, Pacific) daily minutes and the trailing
    7-day rolling total."""
    today = today or today_pacific()
    monday = today - timedelta(days=today.weekday())

    week_minutes = _fetch_mvpa_minutes_by_day(monday, today)
    for day, minutes in week_minutes.items():
        if monday <= day <= today:
            write_daily_mvpa(user_id, day, minutes)

    rolling_start = today - timedelta(days=6)
    rolling_minutes = _fetch_mvpa_minutes_by_day(rolling_start, today)
    set_rolling_7d_total(user_id, sum(rolling_minutes.values()))


def _lock_weeks_in_range(user_id, range_start, range_end_exclusive, today):
    """Locks every fully-completed week whose Monday falls in
    [range_start, range_end_exclusive), fetching the whole span in a single MCP
    call rather than one call per week."""
    # Never lock past the current Monday, whatever the caller computed.
    range_end_exclusive = min(range_end_exclusive, today - timedelta(days=today.weekday()))
    if range_start + timedelta(days=6) >= range_end_exclusive:
        return []

    last_complete_day = range_end_exclusive - timedelta(days=1)
    minutes_by_day = _fetch_mvpa_minutes_by_day(range_start, last_complete_day)
    for day, minutes in minutes_by_day.items():
        if day <= today:
            write_daily_mvpa(user_id, day, minutes)

    locked_week_starts = []
    week_start = range_start
    while week_start + timedelta(days=6) < range_end_exclusive:
        week_end = week_start + timedelta(days=6)
        total = sum(minutes_by_day.get(week_start + timedelta(days=i), 0) for i in range(7))
        lock_week_total(user_id, week_start.isoformat(), week_end.isoformat(), total, today)
        locked_week_starts.append(week_start.isoformat())
        week_start += timedelta(days=7)

    return locked_week_starts


def sync_completed_weeks(user_id, today=None):
    """Locks any fully-completed Pacific calendar week not yet in weekly_totals.
    Always keeps the trailing TREND_HISTORY_WEEKS populated: catches up any newly
    completed weeks going forward, and separately backfills older weeks if fewer
    than TREND_HISTORY_WEEKS are locked yet (e.g. an earlier sync got cut short by a
    rate limit and never reached the full window)."""
    today = today or today_pacific()
    this_monday = today - timedelta(days=today.weekday())
    earliest_needed = this_monday - timedelta(weeks=TREND_HISTORY_WEEKS)

    existing = get_weekly_totals(user_id)
    if not existing:
        return _lock_weeks_in_range(user_id, earliest_needed, this_monday, today)

    locked_week_starts = []

    forward_start = date.fromisoformat(existing[-1]["week_end"]) + timedelta(days=1)
    locked_week_starts += _lock_weeks_in_range(user_id, forward_start, this_monday, today)

    earliest_locked = date.fromisoformat(existing[0]["week_start"])
    if earliest_locked > earliest_needed:
        locked_week_starts += _lock_weeks_in_range(user_id, earliest_needed, earliest_locked, today)

    return locked_week_starts


def get_current_week_daily_mvpa(user_id, today=None):
    """{date_str: minutes} for Monday..today (Pacific) of the current week, for
    display in the coaching system prompt."""
    today = today or today_pacific()
    monday = today - timedelta(days=today.weekday())
    return get_daily_mvpa_range(user_id, monday, today)


def _zero_filled_range(user_id, start, end):
    """[{date, minutes}, ...] for every day in [start, end], zero-filled where no data exists."""
    minutes_by_day = get_daily_mvpa_range(user_id, start, end)
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return [{"date": d, "minutes": minutes_by_day.get(d, 0)} for d in days]


def get_current_week_full(user_id, today=None):
    """Monday..Sunday (Pacific) of the current week, zero-filled, for the self-monitoring tab."""
    today = today or today_pacific()
    monday = today - timedelta(days=today.weekday())
    return _zero_filled_range(user_id, monday, monday + timedelta(days=6))


def get_rolling_7d_daily(user_id, today=None):
    """Trailing 7 days ending today (Pacific), zero-filled, for the rolling-7-day tab."""
    today = today or today_pacific()
    return _zero_filled_range(user_id, today - timedelta(days=6), today)


def prune_history(user_id, today=None):
    """Deletes daily_mvpa and weekly_totals docs older than TREND_HISTORY_WEEKS, so storage
    stays bounded to a rolling window, plus any dated in the future — those stall the
    forward lock pass, which resumes from the newest week_end."""
    today = today or today_pacific()
    this_monday = today - timedelta(days=today.weekday())
    cutoff_week_start = this_monday - timedelta(weeks=TREND_HISTORY_WEEKS)
    prune_weekly_totals(user_id, cutoff_week_start)
    prune_daily_mvpa(user_id, cutoff_week_start)
    prune_future_daily_mvpa(user_id, today)
    return prune_future_weekly_totals(user_id, this_monday)


def sync_wearable_data(user_id, today=None):
    """Full sync: drops out-of-window history, locks any newly-completed weeks, and
    refreshes this week's progress."""
    today = today or today_pacific()
    if prune_history(user_id, today):
        calculate_and_update_trend(user_id)
    sync_completed_weeks(user_id, today)
    sync_current_week(user_id, today)
