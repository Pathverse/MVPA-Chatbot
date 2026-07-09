# SMARTBot

A conversational physical-activity coach that pairs an LLM with a participant's real
wearable data to help insufficiently active adults work toward the guideline of **150
minutes of moderate-to-vigorous physical activity (MVPA) per week**.

SMARTBot is the study system for a pre-deployment evaluation. Structured SMART goal
setting and wearable-enabled self-monitoring are among the most effective behaviour-change
techniques for increasing activity, but the personalised coaching that turns them into
sustained change is expensive and does not scale. This project tests whether an LLM coach
can deliver that personalisation at scale.

## Research questions this system is built to answer

1. **Personalised goal setting at scale** — Can a conversational agent walk a participant
   through building genuine SMART goals (Specific, Measurable, Achievable, Relevant,
   Time-bound) one dimension at a time, rather than handing them a generic template?
2. **Wearable-enabled self-monitoring** — Can objective activity data (Apple Health via the
   Pathverse wearable integration) be surfaced back to the participant, and used *by the
   coach itself* to ground its questions and suggestions in what the participant actually did?
3. **Evidence-based coaching at scale** — Can the agent apply Motivational Interviewing (MI)
   and the Theory of Planned Behaviour (TPB) — exploring motivation, ambivalence, and
   perceived control — in the flexible, non-scripted way a human coach would?

Each capability below maps to one of these questions.

## What the system does

**Onboarding (RQ1, RQ3).** A first-time participant is guided through a warm, one-question-
at-a-time intake: name, age, occupation, self-reported baseline activity, preferred
activities, resources, limitations, availability, primary barrier, hoped-for benefit, deeper
motivation, long-term vision, past successes, anything else they want remembered, and their
first SMART goal. Each answer is saved silently as it is given. The server tracks which field
is still outstanding and is authoritative, so the flow can never skip ahead or falsely declare
itself complete.

**SMART goal setting (RQ1).** Say *"help me set a new SMART goal"* and the coach collects
each dimension in turn, only asking for what the participant has not already volunteered,
then proposes a single combined goal and loops until they approve it. Up to 3 goals are held
at once; goals can be edited or deleted through the same conversational loop. Goals appear
live in the centre panel.

**Action planning (RQ1, RQ3).** Alongside the goals themselves the coach remembers how the
participant intends to act on them: an overall day-to-day schedule, a plan attached to each
numbered goal, and any other planning details worth recalling. These are folded back into the
coach's context each turn, so it can pick up where the last conversation left off.

**Coaching (RQ3).** Between structured tasks the coach uses MI and TPB — open questions,
genuine affirmation, rolling with resistance, and drawing out attitude, social norms, and
perceived control — while staying strictly within physical-activity scope and referring
medical or distress concerns to a professional.

**Self-monitoring (RQ2).** The right panel shows the participant's wearable MVPA three ways:
a **Trend** view of completed study weeks against the 150–300 min guideline band, a **Rolling
7-Day** progress ring, and a **This Week** ring with per-day breakdown. The same data is
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

**Persistence.** Each participant is a Firestore document keyed by their Pathverse token.
Subjective profile/goal data, objective wearable data, and the full chat transcript live in
separate subcollections so they evolve independently. Daily MVPA is stored one document per
day; completed weeks are locked into weekly totals, from which the improving/stable/declining
trend is derived. The transcript subcollection is the source of truth for conversation
history, so the browser never needs to hold or resend it.

**Wearable sync.** On each session start or refresh, `sync_wearable_data` locks any newly
completed weeks, refreshes the current week and rolling 7-day total, and prunes history
older than 16 weeks. All day boundaries are computed in Pacific time so a late workout lands
on the right calendar day. MCP requests are batched to stay within the API's per-call rate
limit, and the short-lived JWT is re-minted proactively before it expires.

**Prompt construction.** Every turn rebuilds the system prompt from the participant's current
Firestore state — profile, recent activity, rolling total, trend, and active goals — as a
single context paragraph. See `prompts/variables.md` for the full placeholder reference.

**Deployment model.** SMARTBot runs one isolated instance per participant: their Pathverse
token is injected as `MCP_PARTICIPANT_TOKEN` at deploy time and identifies them everywhere. A
single process only ever serves that one participant — the identity and minted-JWT caches are
module-level and assume this isolation, so the app must not be run as a shared multi-tenant
server.

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

## Using it

On first load the coach starts **onboarding** automatically. After that, everything happens
in the chat, plus the **Refresh** button in the right panel to sync and view wearable data
(Trend / Rolling 7-Day / This Week).

### Command phrases

A few phrases are intercepted by the server and always do exactly the same thing, so they
work no matter where the conversation is:

| Type this | What it does | Matching |
|---|---|---|
| `Hard-reset-123456789` | Clears the participant's profile, goals, and onboarding, then restarts onboarding | Exact, case-sensitive |
| `please help me onboard to the smartbot study` | Begins (or confirms) onboarding to the study | Case-insensitive |
| `help me smartbot` | Shows a short summary of what SMARTBot can do | Case-insensitive |

### Talking to the coach

Everything else is ordinary conversation the coach interprets — you don't need exact
wording. For example:

- **Set a goal** — *"help me set a new SMART goal"*
- **Edit a goal** — *"I'd like to change my walking goal"*
- **Delete a goal** — *"delete my running goal"*
- **Review activity** — *"how did my week look?"* or *"am I on track for my goal?"*

Goals appear live in the centre panel as they're saved; up to 3 can be active at once.

## Structure

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
