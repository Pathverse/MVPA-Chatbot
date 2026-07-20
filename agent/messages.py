"""Runs the per-turn OpenAI tool-calling loop that turns a participant's message into the coach's reply — the agent package's entry point."""
import json
import logging
from pathlib import Path

import openai

from config import OPENAI_API_KEY, LLM_MODEL, LLM_TEMPERATURE, LLM_TOP_P
from pathverse_mcp import mcp_client
from agent import guardrails
from agent.mcp_args import normalize_mcp_arguments
from agent.tools import LOCAL_TOOLS, LOCAL_TOOL_NAMES, NUMERIC_FIELDS, call_local_tool
from study.onboarding import ONBOARDING_QUESTIONS, MULTI_TURN_FIELDS
from study.context import build_user_context
from db.wearable_sync import today_pacific

logger = logging.getLogger(__name__)

_client = openai.OpenAI(api_key=OPENAI_API_KEY)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SYSTEM_TEMPLATE = (_PROMPTS_DIR / "system_prompt.txt").read_text()
_FIELD_INSTRUCTIONS = (_PROMPTS_DIR / "field_instructions.txt").read_text()
_ONBOARDING_TEMPLATE = (_PROMPTS_DIR / "onboarding_prompt.txt").read_text()

_all_tools_cache = None


def _all_tools() -> list:
    """Listing the MCP tools is a network call, so it happens on first use rather than at
    import — otherwise this module can't be imported without live Pathverse credentials.
    An unreachable MCP server must not kill the chat: degrade to the local tools for this
    turn and retry MCP on the next one (the failure is never cached)."""
    global _all_tools_cache
    if _all_tools_cache is None:
        try:
            mcp_tools = mcp_client.list_tools()
        except Exception:
            logger.exception("MCP tool listing failed; continuing with local tools only")
            return LOCAL_TOOLS
        # Goal writes go through the local add/edit/remove_goal tools (which write through
        # to the app themselves) — exposing the MCP write tools too would give the model a
        # second path that bypasses the coach's goal slots.
        mcp_tools = [t for t in mcp_tools if t["function"]["name"] not in {"create_goal", "update_goal"}]
        _all_tools_cache = mcp_tools + LOCAL_TOOLS
    return _all_tools_cache


def _build_system(user_data: dict, weekly_totals: list, daily_mvpa: dict, next_field: str | None) -> str:
    if not user_data.get("onboarding_complete"):
        return (
            _ONBOARDING_TEMPLATE
            .replace("{NEXT_FIELD}", next_field or "")
            .replace("{FIELD_INSTRUCTIONS}", _FIELD_INSTRUCTIONS)
        )
    return (
        _SYSTEM_TEMPLATE
        .replace("{DATE_STRING}", today_pacific().isoformat())
        .replace("{USER_CONTEXT}", build_user_context(user_data, weekly_totals, daily_mvpa))
        .replace("{FIELD_INSTRUCTIONS}", _FIELD_INSTRUCTIONS)
    )


def _run_tool_call(tc, this_call_forced: bool, next_field: str | None) -> tuple[str, bool, bool]:
    """Execute one tool call. Returns (content_json, saved, forced_update_rejected):
    `saved` is True when a local write succeeded; `forced_update_rejected` is True when a
    forced update_field was logically rejected (not malformed), signalling the caller to
    stop forcing."""
    try:
        args = json.loads(tc.function.arguments)
        if tc.function.name not in LOCAL_TOOL_NAMES:
            # The model writes dates like a person; the MCP schema wants strict UTC.
            args = normalize_mcp_arguments(tc.function.name, args)
            return mcp_client.call_tool(tc.function.name, args), False, False

        # tool_choice forces THAT update_field is called, not which field it targets; the
        # model sometimes picks a field other than next_field, so override to be certain.
        if this_call_forced and tc.function.name == "update_field" and args.get("field") != next_field:
            logger.info("onboarding field mismatch: model targeted %r, correcting to %r", args.get("field"), next_field)
            args["field"] = next_field

        content = call_local_tool(tc.function.name, args)
        if "error" not in json.loads(content):
            return content, True, False
        # Rejected, not malformed — retrying the same forced call won't help.
        return content, False, this_call_forced and tc.function.name == "update_field"
    except Exception as e:
        logger.exception("tool call failed: %s", tc.function.name)
        return json.dumps({"error": str(e)}), False, False


def process_message(
    user_input: str, history: list, user_data: dict, weekly_totals: list, daily_mvpa: dict, next_field: str | None
) -> tuple[str, bool]:
    """Return (reply_text, field_updated) where field_updated signals a Firestore write happened."""
    system = {"role": "system", "content": _build_system(user_data, weekly_totals, daily_mvpa, next_field)}
    messages = [system] + history + [{"role": "user", "content": user_input}]
    field_updated = False

    # Force update_field when the user's message is almost certainly answering a specific
    # pending simple field. Empty history means the very first onboarding turn (nothing to
    # save yet), so only force on later turns.
    force_update_field = (
        not user_data.get("onboarding_complete")
        and next_field is not None
        and next_field not in MULTI_TURN_FIELDS
        and len(history) > 0
    )

    # Sanity-check free-text answers before spending a full model turn (numeric fields get a
    # hard range check in agent/tools.py); short-circuit the turn entirely on rejection.
    if force_update_field and next_field not in NUMERIC_FIELDS:
        valid, reason = guardrails.check_plausible_answer(ONBOARDING_QUESTIONS.get(next_field, ""), user_input)
        if not valid:
            logger.info("onboarding answer for %r rejected as implausible: %s", next_field, reason)
            question = ONBOARDING_QUESTIONS.get(next_field, "")
            return f"{reason} {question}".strip(), False

    try:
        for i in range(10):
            # Keep forcing until the save lands: a forced call can still supply bad args and
            # raise before field_updated is set, silently dropping the user's answer.
            this_call_forced = force_update_field and not field_updated
            tool_choice = {"type": "function", "function": {"name": "update_field"}} if this_call_forced else "auto"
            msg = _client.chat.completions.create(
                model=LLM_MODEL, messages=messages, tools=_all_tools(), tool_choice=tool_choice,
                temperature=LLM_TEMPERATURE, top_p=LLM_TOP_P,
            ).choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                break

            for tc in msg.tool_calls:
                content, saved, forced_rejected = _run_tool_call(tc, this_call_forced, next_field)
                if saved:
                    field_updated = True
                elif forced_rejected:
                    force_update_field = False
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

        if not msg.content and not msg.tool_calls:
            # Empty completion (no text, no tool call) is an occasional model quirk; one retry
            # with the same messages almost always succeeds.
            logger.info("empty completion with no tool calls; retrying once")
            msg = _client.chat.completions.create(
                model=LLM_MODEL, messages=messages, tools=_all_tools(), tool_choice="auto",
                temperature=LLM_TEMPERATURE, top_p=LLM_TOP_P,
            ).choices[0].message
            messages.append(msg)
        reply = msg.content or "I wasn't able to generate a response. Please try again."

        if not user_data.get("onboarding_complete"):
            reply = guardrails.enforce_verbatim_question(reply, next_field, field_updated)

        # The model announced a new goal but never wrote it — force one add_goal round so it
        # actually lands. add_goal only appends to the next open slot (and refuses past 3), so
        # even a spurious match can't overwrite an existing goal. Keep the reply the user sees.
        if not field_updated and msg.content and guardrails.should_backstop_goal_save(msg.content):
            logger.info("goal-claim without add_goal; forcing a save round")
            forced = _client.chat.completions.create(
                model=LLM_MODEL, messages=messages, tools=_all_tools(),
                tool_choice={"type": "function", "function": {"name": "add_goal"}},
                temperature=LLM_TEMPERATURE, top_p=LLM_TOP_P,
            ).choices[0].message
            for tc in forced.tool_calls or []:
                if tc.function.name != "add_goal":
                    continue
                try:
                    call_local_tool(tc.function.name, json.loads(tc.function.arguments))
                    field_updated = True
                except Exception:
                    logger.exception("forced add_goal failed")
    except openai.APIError as e:
        logger.exception("OpenAI API error")
        return f"Sorry, I had trouble connecting ({e}). Try again.", False

    return reply, field_updated
