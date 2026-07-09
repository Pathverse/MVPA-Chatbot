"""Tests for the string heuristics in agent/guardrails.py. These make no network calls;
they do import config, so a valid .env (and serviceAccountKey.json) must be present. Run
from the project root: `pytest`."""
from agent.guardrails import should_backstop_goal_save, enforce_verbatim_question
from study.onboarding import ONBOARDING_QUESTIONS


def test_backstop_fires_on_genuine_save_claim():
    assert should_backstop_goal_save("Your goal has been set!")
    assert should_backstop_goal_save("I've added your goal to your list.")


def test_backstop_skips_draft_awaiting_approval():
    # A claim alongside an approval-seeking phrase is a draft, not a save.
    assert not should_backstop_goal_save("Your goal has been saved. Does this feel right?")


def test_backstop_ignores_bare_infinitive():
    assert not should_backstop_goal_save("Let's set a goal together — what would you commit to?")


def test_verbatim_passes_clean_reply_through():
    reply = f"Nice. {ONBOARDING_QUESTIONS['age']}"
    assert enforce_verbatim_question(reply, "age", field_updated=False) == reply


def test_verbatim_rebuilds_paraphrased_question():
    result = enforce_verbatim_question(
        "Great! And what's your age, if you don't mind?", "age", field_updated=False
    )
    assert result == f"Great! {ONBOARDING_QUESTIONS['age']}"


def test_verbatim_leaves_multi_turn_goal_field_alone():
    reply = "Let's build your first goal — what activity would you like to commit to?"
    assert enforce_verbatim_question(reply, "smart_goal_1", field_updated=False) == reply
