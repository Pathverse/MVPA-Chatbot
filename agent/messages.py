import json
from datetime import date
from pathlib import Path

import openai

from config import OPENAI_API_KEY, LLM_MODEL, LLM_TEMPERATURE, LLM_TOP_P, MAX_HISTORY_TURNS
from mcp import mcp_client
from agent.tools import LOCAL_TOOLS, LOCAL_TOOL_NAMES, call_local_tool
from goals.goal import list_goals

_client = openai.OpenAI(api_key=OPENAI_API_KEY)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SYSTEM_TEMPLATE = (_PROMPTS_DIR / "system_prompt.txt").read_text()
_GOAL_INSTRUCTIONS = (_PROMPTS_DIR / "goal_instructions.txt").read_text()

_ALL_TOOLS = mcp_client.list_tools() + LOCAL_TOOLS


def _build_system() -> str:
    today = date.today().isoformat()
    goals = list_goals()
    if goals:
        goals_block = "\n".join(f"  - id:{g.id} | {g.text}" for g in goals)
        goals_context = f"\nCURRENT SAVED GOALS (use these ids for delete_goal/update_goal):\n{goals_block}"
    else:
        goals_context = "\nCURRENT SAVED GOALS: none"
    return (
        _SYSTEM_TEMPLATE
        .replace("{DATE_STRING}", today)
        .replace("{GOAL_INSTRUCTIONS}", _GOAL_INSTRUCTIONS)
        + goals_context
    )


def process_message(user_input: str, history: list) -> tuple[str, bool]:
    """Return (reply_text, goal_mutated) where goal_mutated signals the frontend to refresh goals."""
    system = {"role": "system", "content": _build_system()}
    messages = [system] + history[-(MAX_HISTORY_TURNS * 2):] + [{"role": "user", "content": user_input}]
    goal_mutated = False

    try:
        for _ in range(10):
            msg = _client.chat.completions.create(
                model=LLM_MODEL, messages=messages, tools=_ALL_TOOLS, tool_choice="auto",
                temperature=LLM_TEMPERATURE, top_p=LLM_TOP_P,
            ).choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                break

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                    if tc.function.name in LOCAL_TOOL_NAMES:
                        content = call_local_tool(tc.function.name, args)
                        goal_mutated = True
                    else:
                        content = mcp_client.call_tool(tc.function.name, args)
                except Exception as e:
                    content = json.dumps({"error": str(e)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
    except openai.APIError as e:
        return f"Sorry, I had trouble connecting ({e}). Try again.", False

    return msg.content or "I wasn't able to generate a response. Please try again.", goal_mutated
