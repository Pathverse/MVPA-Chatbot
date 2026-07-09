# Overview

A LLM chatbot scoped to help insufficiently active adults work toward the guideline of 150
minutes of moderate-to-vigorous physical activity (MVPA) per week. Focused on applying 
self-monitoring and SMART goal setting coaching principles. Tailored to user by (1) 
personal information such as time availability, barriers, motivators, (2) apple watch active
minutes and (3) recent messages (last 10 user-response pairs) all stored in firestore 
database linked to participant ID in pathverse app.  

# Thesis Study 2 (CH5)

## Objectives

To develop SMARTBot, an LLM-based PABCC chatbot and no tintegrated system for SMART goal setting
and self-monitoring targeting the CSEP 24-Hour Movement Guidelines on the 
pathverse mobile app, and evaluate its usability with target end users and inform areas for 
improvement and make subsequent refinements prior to real-world deployment

## Research Questions 

1.	How does the SMARTBot's usability as measured by BUS-11 overall and subscales scores
   compare to the Borsci and Schmettow (2024) chatbot	benchmark and comparable health coaching
   LLM-based chatbots?
2. How does SMARTBot's overall system usability, as measured by the SUS, compare to established
   benchmarks for physical activity applications?
3. What usability concerns, feature gaps, and design recommendations do participants identify
   through focus group discussion following the seven-day testing period?

## Contributions 

1. An LLM-based chatbot system for MVPA SMART goal setting and self-monitoring, targeting
   the CSEP 24-hour movement guideline  integrating persistent memory, wearable data via an
   MCP server pipeline, and conversational physical activity support providing a documented 
   architecture for LLM-based PABCC chatbot systems.
2. A pre-deployment mixed method LLM chatbot and surrounding mobile application system 
   using validated usability scales and a mini focus group interview.
3. Evidence of the usability and feasibility of deploying an LLM system for SMART 
   goal-based MVPA self-monitoring in adults, contributing to the emerging literature on 
   PABCC LLM chatbots.

## What the system does

Onboarding (RQ1, RQ3): A first-time participant is guided through a warm, one-question-
at-a-time intake: name, age, occupation, self-reported baseline activity, preferred
activities, resources, limitations, availability, primary barrier, hoped-for benefit, deeper
motivation, long-term vision, past successes, anything else they want remembered, and their
first SMART goal. Each answer is saved silently as it is given. The server tracks which field
is still outstanding and is authoritative, so the flow can never skip ahead or falsely declare
itself complete.

SMART goal setting (RQ1): Say "help me set a new SMART goal" and the coach collects
each dimension in turn, only asking for what the participant has not already volunteered,
then proposes a single combined goal and loops until they approve it. Up to 3 goals are held
at once; goals can be edited or deleted through the same conversational loop. Goals appear
live in the centre panel.

Action planning (RQ1, RQ3): Alongside the goals themselves the coach remembers how the
participant intends to act on them: an overall day-to-day schedule, a plan attached to each
numbered goal, and any other planning details worth recalling. These are folded back into the
coach's context each turn, so it can pick up where the last conversation left off.

Coaching (RQ3): Between structured tasks the coach uses MI and TPB open questions,
genuine affirmation, rolling with resistance, and drawing out attitude, social norms, and
perceived control while staying strictly within physical-activity scope and referring
medical or distress concerns to a professional.

Self-monitoring (RQ2): The right panel shows the participant's wearable MVPA three ways:
a (1) Trend view of completed study weeks against the 150–300 min guideline band, a (2) Rolling
7-Day progress ring, and a (3) This Week ring with per-day breakdown. The same data is
folded into the coach's context each turn, so it can reference recent activity and progress
toward a goal without the participant having to report anything.

## Architecture

```
Browser (3-panel UI)
   │  POST /session/start, /session/message, /api/wearable
   ▼
FastAPI (main.py)
   ├─ backend/session.py    Chat + onboarding endpoints, reset/help commands
   ├─ backend/wearable.py   Self-monitoring data endpoint
   ▼
agent/messages.py           LLM turn loop (OpenAI tool calling)
   ├─ agent/guardrails.py   Post-hoc corrections (verbatim question, answer plausibility,
   │                        goal-save backstop)
   ├─ agent/tools.py        update_field (profile + plans), add/edit/remove_goal
   ├─ study/                Onboarding fields/questions + system-prompt construction
   ├─ prompts/              System, onboarding, and field-instruction prompts
   ▼
db/ (Firestore)             Profile, goals, and wearable history per participant
   └─ db/wearable_sync.py   Pulls Apple Health MVPA via MCP, locks weekly totals,
                            computes trend, prunes to a rolling 16-week window
   ▼
pathverse_mcp/              Pathverse MCP client (get_phi, get_intent) + JWT token minting
```

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your values:

```
OPENAI_API_KEY=sk-...
GOOGLE_APPLICATION_CREDENTIALS=serviceAccountKey.json
MCP_PARTICIPANT_TOKEN=your-participant-token
MCP_PROGRAM_ID=your-program-id
MCP_TOKEN_MINT_URL=your-mcp-token-mint-url
MCP_URL=your-mcp-url
```

`GOOGLE_APPLICATION_CREDENTIALS` points at a Firebase service-account key JSON file for the
Firestore project.

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000`.

## First Use Notes

On first load the coach starts onboarding automatically. After that, everything happens
in the chat, plus the refresh button in the right panel to sync and view wearable data
(Trend / Rolling 7-Day / This Week).

### Key Command Phrases

A few phrases are intercepted by the server and always do exactly the same thing, so they
work no matter where the conversation is:

| Type this | What it does | Matching |
|---|---|---|
| `Hard-reset-123456789` | Clears the participant's profile, goals, and onboarding, then restarts onboarding | Exact, case-sensitive |
| `please help me onboard to the smartbot study` | Begins (or confirms) onboarding to the study | Case-insensitive |
| `help me smartbot` | Shows a short summary of what SMARTBot can do | Case-insensitive |

## File Structure

```
agent/          LLM turn loop, guardrails, and the profile/goal tools
backend/        FastAPI routers (session.py: chat/onboarding; wearable.py: data)
study/          Onboarding fields/questions and system-prompt construction
db/             Firestore access and wearable sync
pathverse_mcp/  Pathverse MCP client and token minting
frontend/       3-panel UI (HTML, CSS, JS)
prompts/        System, onboarding, and field-instruction prompts (+ variables.md)
tests/          Pytest suite (guardrails)
config.py       Environment variables and LLM settings
main.py         FastAPI entrypoint
```
