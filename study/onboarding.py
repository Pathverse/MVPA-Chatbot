"""Single source of truth for the onboarding fields, their canonical verbatim questions, and the SMART-goal slot layout."""
ONBOARDING_FIELDS = [
    "name",
    "age",
    "occupation",
    "user_reported_mvpa_mins",
    "preferred_activities",
    "available_resources",
    "physical_limitations",
    "available_days_times",
    "primary_barrier",
    "personal_benefit",
    "why_active",
    "long_term_vision",
    "past_successes",
    "additional_info",
    "smart_goal_1",
]


# The three SMART-goal slots. Goals are stored positionally (smart_goal_1..3) and kept
# gap-free by agent/tools.py; this is the single source of truth for that layout.
GOAL_FIELDS = [f"smart_goal_{i}" for i in (1, 2, 3)]


# The SMART-goal fields are collected over several conversational turns (activity, duration,
# frequency, timeframe, confirmation) before a single save, unlike the one-question-one-answer
# simple fields. Callers use this to skip per-turn tool-call forcing and verbatim-question
# enforcement, both of which only make sense for the simple fields.
MULTI_TURN_FIELDS = {"smart_goal_1", "smart_goal_2", "smart_goal_3"}


def goal_slots(user_data):
    """The three goal slots as a positional list, empty string for any unset slot."""
    return [user_data.get(f, "") for f in GOAL_FIELDS]


def get_next_onboarding_field(user_data):
    for field in ONBOARDING_FIELDS:
        if not user_data.get(field):
            return field
    return None


def is_onboarding_complete(user_data):
    return get_next_onboarding_field(user_data) is None


def opening_question(user_data):
    """(next_field, canonical_question) for the field onboarding is currently waiting on,
    or (None, "") once onboarding is complete."""
    next_field = get_next_onboarding_field(user_data)
    return next_field, ONBOARDING_QUESTIONS.get(next_field, "")


# The deterministic bootstrap/resume question for each field, used instead of an LLM
# call whenever there's no real user answer yet (fresh user, post-reset, or resuming
# on a new browser). Keep in sync with the per-field questions in
# prompts/onboarding_prompt.txt, which the LLM uses for the rest of the conversation.
ONBOARDING_QUESTIONS = {
    "name": "Hi! I'm SMARTBot. What is your first name?",
    "age": "How old are you?",
    "occupation": (
        "What do you do these days, working, studying, retired, or something else? "
        "What does that involve day-to-day?"
    ),
    "user_reported_mvpa_mins": (
        "MVPA just means moderate to vigorous physical activity. Moderate is where you can talk "
        "but not sing, like brisk walking, cycling, or playing recreational sports. "
        "Vigorous is where you can only say a few words without pausing for breath, like "
        "running, swimming laps, or a hard workout. About how many minutes a week would "
        "you say you get of that? A rough guess is totally fine, no need to be precise."
    ),
    "preferred_activities": "What are some of your favourite ways to be active?",
    "available_resources": (
        "What do you have available to support being active? For example, a gym or "
        "community centre, fitness classes, a sports league or team, home equipment, or "
        "people to be active with."
    ),
    "physical_limitations": (
        "Do you have any injuries or physical limitations I should keep in mind? "
        "If none, just say none."
    ),
    "available_days_times": (
        "What does a normal week usually look like for you, and what days and times "
        "tend to work best for you to be active?"
    ),
    "primary_barrier": "What is the biggest thing that gets in the way of you being physically active?",
    "personal_benefit": (
        "What's one thing you're hoping to get out of being more active? For example, "
        "more energy, better sleep, or feeling less stressed."
    ),
    "why_active": (
        "And beyond that, what's the deeper reason it matters to you? Maybe it's your "
        "health, being there for people you care about, or how you want to feel day to day."
    ),
    "long_term_vision": (
        "When you imagine yourself six months from now, regularly getting your 150 "
        "minutes a week, what habits or routines would be part of your life at that point?"
    ),
    "past_successes": (
        "Has there been a time before when staying active felt easier for you? "
        "What was helping back then?"
    ),
    "additional_info": (
        "Is there anything else you think I should know that could help me on your "
        "physical activity journey? If nothing comes to mind, just say no. And any time "
        "something else comes up later that you'd like me to remember, just let me know."
    ),
    "smart_goal_1": (
        "A SMART goal is Specific, Measurable, Achievable, Relevant, and Time-bound. "
        "For example: \"I will walk briskly for 30 minutes, three days a week, for the "
        "next 4 weeks, to build a healthy exercise habit.\" Let's set your first goal "
        "together. What is one physical activity you would like to commit to, "
        "including what, how long, and how many days a week?"
    ),
}
