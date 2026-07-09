"""Post-hoc corrections that enforce prompt-only behaviours the agent's model doesn't always honour on its own (verbatim onboarding questions, answer plausibility, goal-save backstop)."""
import json
import logging
import re

import openai

from config import OPENAI_API_KEY, LLM_MODEL
from study.onboarding import ONBOARDING_FIELDS, ONBOARDING_QUESTIONS, MULTI_TURN_FIELDS

logger = logging.getLogger(__name__)

_client = openai.OpenAI(api_key=OPENAI_API_KEY)


# Genuine "new goal saved" claim tied to an auxiliary/perfect construction ("goal HAS BEEN
# set", "I'VE added your goal"). Excludes edit/remove verbs and bare infinitives ("help me
# set a goal") so the backstop can't create a duplicate or add an empty goal on turn one.
_GOAL_CLAIM_RE = re.compile(
    r"\bgoal\b[^.!?\n]{0,20}\b(has|have|'ve|'s|is|are|been|now)\b[^.!?\n]{0,15}"
    r"\b(set|saved|added|logged|created)\b"
    r"|\bI\s*('ve|'ll just|\s+have|\s+just)\s+"
    r"(set|saved|added|logged|created)\b[^.!?\n]{0,25}\bgoal\b"
    r"|\b(added (it |that )?to your goals|it's in your goals)\b",
    re.IGNORECASE,
)

# A goal claim alongside any of these approval-seeking phrases is a draft being presented,
# not a save, so we skip the backstop and never persist an unapproved goal.
_GOAL_PENDING_RE = re.compile(
    r"does this feel right|happy with this|keep tweaking|would you like to change|"
    r"want to change|want to keep|how does (that|this) (sound|look)|"
    r"(shall|should) i save|want me to save|ready to save",
    re.IGNORECASE,
)


def should_backstop_goal_save(content: str) -> bool:
    """True when the reply claims a new goal was saved and isn't merely presenting a draft;
    the caller then forces a single add_goal round so the claim becomes true."""
    return bool(_GOAL_CLAIM_RE.search(content) and not _GOAL_PENDING_RE.search(content))


# Leading "natural reaction" sentence (per onboarding_prompt.txt) preserved when we replace a
# paraphrased question; '?' is excluded because a reaction is never itself a question.
_REACTION_PREFIX_RE = re.compile(r"^\s*([^?\n]{1,120}?[.!])\s+")

# Model declaring onboarding done while the server says smart_goal_1 is still pending.
_ONBOARDING_COMPLETE_CLAIM_RE = re.compile(
    r"\bonboarding\b[^.!?\n]{0,20}\b(complete|completed|done|finished)\b", re.IGNORECASE
)


def enforce_verbatim_question(reply: str, next_field: str | None, field_updated: bool) -> str:
    """Force the canonical wording for simple onboarding fields (the model paraphrases,
    drops load-bearing text, or tacks on a tangential question). After a save this turn the
    target is the field *after* next_field, otherwise next_field itself. Multi-turn SMART
    goal collection is excluded — it has no single fixed question."""
    target_field = next_field
    if field_updated and next_field in ONBOARDING_FIELDS:
        idx = ONBOARDING_FIELDS.index(next_field) + 1
        target_field = ONBOARDING_FIELDS[idx] if idx < len(ONBOARDING_FIELDS) else None

    # A false completion claim is never part of the legitimate smart_goal_1 flow, so catch it
    # even though smart_goal_1 is otherwise exempt from enforcement.
    if target_field == "smart_goal_1" and _ONBOARDING_COMPLETE_CLAIM_RE.search(reply):
        logger.info("false onboarding-complete claim while smart_goal_1 still pending; rebuilding")
        expected = ONBOARDING_QUESTIONS["smart_goal_1"]
        m = _REACTION_PREFIX_RE.match(reply)
        return f"{m.group(1)} {expected}" if m else expected

    if target_field is None or target_field in MULTI_TURN_FIELDS:
        return reply
    expected = ONBOARDING_QUESTIONS.get(target_field)
    if not expected:
        return reply

    # Missing/paraphrased, or verbatim but with a stray '?' elsewhere (a tangential question
    # riding along) — either way rebuild from a clean reaction.
    pos = reply.find(expected)
    if pos == -1 or "?" in reply[:pos] + reply[pos + len(expected):]:
        logger.info("onboarding reply for %r not clean; rebuilding", target_field)
        m = _REACTION_PREFIX_RE.match(reply)
        return f"{m.group(1)} {expected}" if m else expected

    return reply


_VALIDATE_ANSWER_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "validate_answer",
            "description": "Judge whether a participant's answer plausibly answers the question they were asked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "valid": {"type": "boolean"},
                    "reason": {
                        "type": "string",
                        "description": (
                            "If invalid, one short, warm, participant-facing sentence explaining "
                            "why (e.g. \"That doesn't look like a job or activity.\"). Empty "
                            "string if valid."
                        ),
                    },
                },
                "required": ["valid", "reason"],
            },
        },
    }
]


def check_plausible_answer(question: str, answer: str) -> tuple[bool, str]:
    """Sanity-check that a free-text onboarding answer is on-topic (not a bare number or an
    answer to another question); numeric fields get a hard range check in agent/tools.py
    instead. Fails open, since a broken check should never block onboarding."""
    try:
        msg = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    f'A participant was asked: "{question}"\n'
                    f'They answered: "{answer}"\n'
                    "Judge only whether this is a plausible, on-topic answer (not whether it's "
                    "a good or complete one). Reject only clear nonsense, random characters, or "
                    "an answer to a completely different question (e.g. a bare number where a "
                    "description was asked). Be lenient with short, casual, one- or two-word "
                    "answers that do fit."
                ),
            }],
            tools=_VALIDATE_ANSWER_TOOL,
            tool_choice={"type": "function", "function": {"name": "validate_answer"}},
            temperature=0,
        ).choices[0].message
        args = json.loads(msg.tool_calls[0].function.arguments)
        return bool(args.get("valid", True)), (args.get("reason") or "").strip()
    except Exception:
        logger.exception("plausibility check failed; treating answer as valid")
        return True, ""
