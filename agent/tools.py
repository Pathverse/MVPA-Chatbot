import json
from goals.goal import save_goal, delete_goal, update_goal

LOCAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_goal",
            "description": "Save a finalized SMART goal that the user has approved.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The complete SMART goal text."}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_goal",
            "description": "Delete an existing goal by its id.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "The goal id to delete."}},
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal",
            "description": "Replace the text of an existing goal after the user approves a revised version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The goal id to update."},
                    "text": {"type": "string", "description": "The revised SMART goal text."},
                },
                "required": ["id", "text"],
            },
        },
    },
]

_LOCAL_HANDLERS = {
    "save_goal": lambda args: save_goal(args["text"]),
    "delete_goal": lambda args: delete_goal(args["id"]),
    "update_goal": lambda args: update_goal(args["id"], args["text"]),
}

LOCAL_TOOL_NAMES = set(_LOCAL_HANDLERS)


def call_local_tool(name: str, arguments: dict) -> str:
    result = _LOCAL_HANDLERS[name](arguments)
    return json.dumps(result)
