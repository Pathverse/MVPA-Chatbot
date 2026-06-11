# MVPA Coach

Web chatbot that uses wearable data to help self-monitor and plan physical activity aimed at achieving 150 minutes of MVPA per week. 3-panel interface: chat on the left, saved goals in the centre, self-monitoring data on the right.

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your values:
```
OPENAI_API_KEY=sk-...
MCP_TOKEN=your-mcp-token
MCP_URL=https://mcp-appbuilder.pathverse.ca/api/mcp
```

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000`.

## Features

**Goal setting** : say `"help me set a new SMART goal"` and the coach walks you through one dimension at a time (Specific → Measurable → Achievable → Relevant → Time-bound), proposes the full goal, then loops until you approve. Up to 3 goals saved at once.

**Edit a goal** : say `"I want to edit my walking goal"` and the coach opens the same revision loop, then saves the updated version.

**Delete a goal** : say `"delete my running goal"` and the coach confirms and removes it from the panel.

**Self-monitoring** : click **Refresh** in the right panel to load the past 7 days of wearable data: MVPA minutes, step counts, heart rate & HRV, and wellbeing survey scores.

## Structure

```
agent/      Conversation loop and tool routing
backend/    FastAPI routers (chat WebSocket, goals, wearable)
frontend/   HTML, CSS, JS
mcp/        MCP client (wearable data integration)
goals/      Goal schema and in-memory store
prompts/    System prompt and goal-setting instructions
config.py   Environment variables and LLM settings
main.py     FastAPI entrypoint
```
