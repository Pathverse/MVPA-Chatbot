"""Builds the participant-context paragraph (injected as {USER_CONTEXT} in system_prompt.txt) from a participant's current profile, activity, and goals."""
from datetime import date

from study.onboarding import goal_slots


def build_user_context(user_data, weekly_totals, daily_mvpa):
    parts = []

    name = user_data.get("name", "")
    age = user_data.get("age", 0)
    occupation = user_data.get("occupation", "")
    parts.append(f"{name} is a {age}-year-old {occupation}.")

    baseline = user_data.get("user_reported_mvpa_mins", 0)
    if baseline:
        parts.append(f"At baseline they accumulated approximately {baseline} min/week of MVPA.")

    day_frags = [
        f"{date.fromisoformat(day_str).strftime('%A')}: {minutes} min"
        for day_str, minutes in sorted(daily_mvpa.items())
        if minutes > 0
    ]
    if day_frags:
        parts.append(f"This week's MVPA: {', '.join(day_frags)}.")

    rolling = user_data.get("mvpa_rolling_7d_total", 0)
    if rolling:
        parts.append(f"Rolling 7-day total: {rolling} min.")

    locked_weeks = [w for w in weekly_totals if w.get("locked")]
    if locked_weeks:
        week_frags = [f"Week of {w['week_start']}: {w['total_minutes']} min" for w in locked_weeks]
        parts.append(f"Study week totals: {', '.join(week_frags)}.")

    trend = user_data.get("mvpa_trend", "")
    if trend and trend != "insufficient_data":
        parts.append(f"Across completed study weeks, {name}'s MVPA trend is {trend}.")

    parts.append(
        f"They enjoy {user_data.get('preferred_activities', '')}, "
        f"have access to {user_data.get('available_resources', '')}, "
        f"and are available on {user_data.get('available_days_times', '')}."
    )

    limitations = user_data.get("physical_limitations", "none")
    if limitations and limitations != "none":
        parts.append(f"They report {limitations} relevant to exercise planning.")

    parts.append(
        f"Their biggest barrier is {user_data.get('primary_barrier', '')} "
        f"and their primary hoped benefit is {user_data.get('personal_benefit', '')}."
    )
    parts.append(
        f"Their core reason for wanting to be active is {user_data.get('why_active', '')} "
        f"and their long-term vision is {user_data.get('long_term_vision', '')}."
    )
    parts.append(f"In the past, {user_data.get('past_successes', '')} has worked well for them.")

    additional_info = user_data.get("additional_info", "")
    if additional_info and additional_info.strip().lower() != "no":
        parts.append(f"Additional info they shared: {additional_info}.")

    goal_frags = [g for g in goal_slots(user_data) if g]
    if goal_frags:
        numbered = ", ".join(f"({i + 1}) {g}" for i, g in enumerate(goal_frags))
        parts.append(f"Active SMART goals: {numbered}.")

    plan_daily = user_data.get("plan_daily", "")
    if plan_daily:
        parts.append(f"Their day-to-day plan: {plan_daily}")

    goal_plan_frags = [
        f"(for goal {i + 1}) {p}"
        for i, f in enumerate(("plan_goal_1", "plan_goal_2", "plan_goal_3"))
        if (p := user_data.get(f, ""))
    ]
    if goal_plan_frags:
        parts.append(f"Goal-specific plans: {', '.join(goal_plan_frags)}.")

    plan_notes = user_data.get("plan_notes", "")
    if plan_notes:
        parts.append(f"Plan notes: {plan_notes}")

    return " ".join(parts)
