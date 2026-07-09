# Prompt Variable Reference

Reference for the placeholders in [system_prompt.txt](system_prompt.txt) and [onboarding_prompt.txt](onboarding_prompt.txt). All four are filled in with plain `str.replace()` calls in `_build_system()` in [agent/messages.py:37-49](../agent/messages.py#L37-L49) — no templating engine, so the literal substring `{PLACEHOLDER}` must appear in the `.txt` file exactly as written for it to be replaced.

`system_prompt.txt` gets `{DATE_STRING}`, `{USER_CONTEXT}`, `{FIELD_INSTRUCTIONS}`.
`onboarding_prompt.txt` gets `{NEXT_FIELD}`, `{FIELD_INSTRUCTIONS}` only — no `{DATE_STRING}` (nothing in the onboarding flow references the date) and no `{USER_CONTEXT}` (there's no profile yet during onboarding).

## `{DATE_STRING}`

```python
today_pacific().isoformat()   # agent/messages.py, system_prompt branch only
```

`system_prompt.txt`-only. Exact format: ISO date, e.g. `2026-07-07`. Goes in inline, at the one place it's actually load-bearing: `Never call get_phi with a to_date beyond today (2026-07-07).`

There used to be *two* other renderings of the date floating around with no instruction attached to them — a standalone `"Today's date is {DATE_STRING}."` line, and a differently-formatted `"Today is July 07, 2026."` sentence baked into `{USER_CONTEXT}`. Both were removed: a variable should sit inside the instruction that needs it, not get appended as inert context nobody's told to act on.

## `{USER_CONTEXT}`

Read-only prose paragraph built by `build_user_context()` in [study/context.py](../study/context.py). Rebuilt fresh every turn from Firestore/session data, then dropped in as one `" ".join(parts)` string — a single space-separated paragraph, no line breaks, no markdown. Only used in `system_prompt.txt` (not present during onboarding).

Preceded by a `PARTICIPANT CONTEXT` header in the template, matching the ALL-CAPS section convention used everywhere else in the file (`COACHING APPROACH`, `TONE`, `SCOPE`, `GUIDELINES`). Without it the paragraph would drop in as unlabeled prose right after a bulleted instruction list — `{FIELD_INSTRUCTIONS}` doesn't need this treatment since it self-labels internally (`STYLE`, `FIELD UPDATE RULES`, ...), but `{USER_CONTEXT}` has no internal structure of its own.

The wearable/intent-data GUIDELINES bullet also names this block explicitly ("already summarized for you below in PARTICIPANT CONTEXT, no tool call needed for any of that"). It draws a real distinction between the two MCP tools that could otherwise both be treated as optional: `get_phi` genuinely is conditional, since the numbers it would return (rolling total, trend, this week's minutes) are already in the summary — only call it for something outside that, like a specific past date. `get_intent` (the raw Pathverse stated intent) is different: nothing anywhere syncs that into `PARTICIPANT CONTEXT` — `smart_goal_*` are the chatbot's own SMART goals, not the Pathverse intent — so it stays mandatory, called at the start of every conversation, or that data source is silently unused for the whole session.

Sentences are appended unconditionally unless noted "only if" below — an unset field renders as an empty/zero value in its sentence (e.g. `"John is a 0-year-old ."` if age/occupation are blank), it does not get skipped.

| Source field(s) | Rendered sentence | Included when |
|---|---|---|
| `name`, `age`, `occupation` | `{name} is a {age}-year-old {occupation}.` | always, first sentence |
| `user_reported_mvpa_mins` | `At baseline they accumulated approximately {n} min/week of MVPA.` | only if truthy (nonzero) |
| `daily_mvpa` (per-day dict) | `This week's MVPA: Monday: 20 min, Wednesday: 35 min.` | only for days with `minutes > 0`; whole sentence omitted if none |
| `mvpa_rolling_7d_total` | `Rolling 7-day total: {n} min.` | only if truthy |
| `weekly_totals` (`locked: true` entries) | `Study week totals: Week of 2026-06-01: 140 min.` | only if ≥1 locked week |
| `mvpa_trend` | `Across completed study weeks, {name}'s MVPA trend is {trend}.` | only if set and not `"insufficient_data"` |
| `preferred_activities`, `available_resources`, `available_days_times` | `They enjoy {x}, have access to {y}, and are available on {z}.` | always (blank fields render empty) |
| `physical_limitations` | `They report {limitations} relevant to exercise planning.` | only if set and not `"none"` |
| `primary_barrier`, `personal_benefit` | `Their biggest barrier is {x} and their primary hoped benefit is {y}.` | always |
| `why_active`, `long_term_vision` | `Their core reason for wanting to be active is {x} and their long-term vision is {y}.` | always |
| `past_successes` | `In the past, {x} has worked well for them.` | always |
| `additional_info` | `Additional info they shared: {x}.` | only if set and not `"no"` |
| `smart_goal_1`, `smart_goal_2`, `smart_goal_3` | `Active SMART goals: (1) ..., (2) ....` | only for non-empty slots; whole sentence omitted if all 3 empty |
| `plan_daily` | `Their day-to-day plan: {x}` | only if set |
| `plan_goal_1`, `plan_goal_2`, `plan_goal_3` | `Goal-specific plans: (for goal 1) ..., (for goal 2) ....` | only for non-empty slots; whole sentence omitted if all 3 empty |
| `plan_notes` | `Plan notes: {x}` | only if set |

**Usage:** background knowledge for the model to draw on silently. Never announce or cite this data unless the user asks.

## `{FIELD_INSTRUCTIONS}`

```python
_FIELD_INSTRUCTIONS = (_PROMPTS_DIR / "field_instructions.txt").read_text()  # agent/messages.py:22
```

Exact format: the entire contents of `field_instructions.txt` dropped in **verbatim, unmodified** (no substitutions happen inside it — it has no `{...}` placeholders of its own). Identical in both `system_prompt.txt` and `onboarding_prompt.txt`. Governs the `update_field(field, value)` tool.

**Updatable fields** (`_UPDATABLE_FIELDS` in [agent/tools.py](../agent/tools.py)):

```
name, age, occupation, user_reported_mvpa_mins, available_days_times,
available_resources, physical_limitations, preferred_activities,
primary_barrier, personal_benefit, why_active, long_term_vision,
past_successes, additional_info, smart_goal_1, smart_goal_2, smart_goal_3,
plan_daily, plan_goal_1, plan_goal_2, plan_goal_3, plan_notes
```

- **Locked once onboarding is complete:** `name`, `user_reported_mvpa_mins`
- **Never settable via chat** (wearable-synced or system-managed): `mvpa_rolling_7d_total`, `mvpa_trend`, `onboarding_complete`, `last_updated`

**Usage:** tells the model when/how to call `update_field` (one fact per call, immediately, no batching, never announce the save) plus the full SMART-goal collection/edit/delete workflow.

## `{NEXT_FIELD}`

```python
next_field or ""   # agent/messages.py:41
```

Onboarding only, computed by `get_next_onboarding_field()` in [study/onboarding.py:38-42](../study/onboarding.py#L38-L42) — the first field in the fixed `ONBOARDING_FIELDS` order that is still falsy on `user_data`.

Exact format: the **raw field key string**, e.g. `age`, `smart_goal_2` — not a question, not a label. Renders as `The next field to collect is: age.` Goes in as `""` (empty string, not the word "None") once every required field is set, which is the signal in `onboarding_prompt.txt` to deliver the completion message instead of asking another question.

---

## Example: the fully rendered `system_prompt.txt` sent to the model

Say Firestore holds this `user_data` (onboarding already complete):

```
name: Sam, age: 34, occupation: teacher
user_reported_mvpa_mins: 90
preferred_activities: hiking and swimming
available_resources: a home gym and a nearby trail
available_days_times: weekday evenings and Saturday mornings
physical_limitations: a mild knee issue
primary_barrier: lack of time
personal_benefit: more energy
why_active: wanting to keep up with my kids
long_term_vision: hiking a mountain trail without stopping
past_successes: a running club
smart_goal_1: I will hike for 45 minutes, twice a week, for the next 4 weeks, to build endurance for family trips.
mvpa_rolling_7d_total: 85
mvpa_trend: increasing
daily_mvpa: {Mon: 20, Tue: 35}
weekly_totals: [{week_start: 2026-06-01, total_minutes: 140, locked: true}]
```

`{USER_CONTEXT}` renders as this single paragraph (no line breaks — shown wrapped here only for readability):

> Sam is a 34-year-old teacher. At baseline they accumulated approximately 90 min/week of MVPA. This week's MVPA: Monday: 20 min, Tuesday: 35 min. Rolling 7-day total: 85 min. Study week totals: Week of 2026-06-01: 140 min. Across completed study weeks, Sam's MVPA trend is increasing. They enjoy hiking and swimming, have access to a home gym and a nearby trail, and are available on weekday evenings and Saturday mornings. They report a mild knee issue relevant to exercise planning. Their biggest barrier is lack of time and their primary hoped benefit is more energy. Their core reason for wanting to be active is wanting to keep up with my kids and their long-term vision is hiking a mountain trail without stopping. In the past, a running club has worked well for them. Active SMART goals: (1) I will hike for 45 minutes, twice a week, for the next 4 weeks, to build endurance for family trips.

That paragraph, plus `{FIELD_INSTRUCTIONS}` = the full text of `field_instructions.txt`, get dropped into the end of `system_prompt.txt`'s last lines (`{DATE_STRING}` was already substituted earlier, inline in the get_phi guideline):

```
PARTICIPANT CONTEXT
Sam is a 34-year-old teacher. At baseline they accumulated approximately 90 min/week of
MVPA. This week's MVPA: Monday: 20 min, Tuesday: 35 min. Rolling 7-day total: 85 min.
Study week totals: Week of 2026-06-01: 140 min. Across completed study weeks, Sam's
MVPA trend is increasing. They enjoy hiking and swimming, have access to a home gym
and a nearby trail, and are available on weekday evenings and Saturday mornings. They
report a mild knee issue relevant to exercise planning. Their biggest barrier is lack
of time and their primary hoped benefit is more energy. Their core reason for wanting
to be active is wanting to keep up with my kids and their long-term vision is hiking
a mountain trail without stopping. In the past, a running club has worked well for
them. Active SMART goals: (1) I will hike for 45 minutes, twice a week, for the next
4 weeks, to build endurance for family trips.

STYLE

Never use em dashes in your responses. Use commas, periods, or parentheses instead.
Use Canadian/British spelling throughout ...
[rest of field_instructions.txt, verbatim]
```

Everything above GUIDELINES (coaching approach, tone, scope) is fully static; within GUIDELINES only the `{DATE_STRING}` substring inline in the get_phi bullet changes per turn, plus the trailing `{USER_CONTEXT}` and `{FIELD_INSTRUCTIONS}` blocks.

**Why `{USER_CONTEXT}`/`{FIELD_INSTRUCTIONS}` sit at the very end rather than being woven inline like `{DATE_STRING}` was:** this is deliberate, not the same "appended with no owner" problem the date sentence had. Everything from COACHING APPROACH through GUIDELINES is byte-identical across every user and every turn, so putting the two per-turn-dynamic blocks last keeps that entire prefix a stable, cacheable string — only the tail changes. It also plays to models' recency bias for exactly the two things that are most relevant to *this* turn (who the user is right now, what fields are writable right now). Moving them earlier would break that shared prefix for no benefit, so this one stays as-is.

## Example: the fully rendered `onboarding_prompt.txt` mid-flow

Say `name` and `age` are already saved but nothing else is, so `get_next_onboarding_field()` returns `"occupation"`. The tail of the rendered prompt reads:

```
The next field to collect is: occupation. This is authoritative, not a suggestion: it is
computed from what has actually been saved, not from what you've said in the conversation.

- If occupation is non-empty, you MUST ask about that exact field next. ...
- Only when occupation is empty are all required fields actually saved: deliver the
  completion message instead of asking another question.

STYLE
... [same field_instructions.txt content as above]
```

Note the raw literal `{NEXT_FIELD}` substring is replaced everywhere it appears in the template, including inside the bullet prose itself (`"If {NEXT_FIELD} is non-empty..."` → `"If occupation is non-empty..."`) — it's a dumb string substitution, not just filled into one slot.

When every field is saved, `next_field` is `None` → substituted as `""`, so that line reads `The next field to collect is: .` and the two bullets below it read `If  is non-empty...` / `Only when  is empty...` — grammatically odd, but functions as the "onboarding is done" signal the model is told to watch for.

---

**Rule of thumb:** `USER_CONTEXT` = what the model knows about the user. `FIELD_INSTRUCTIONS` = what it's allowed to write and how. `NEXT_FIELD` = what's authoritative during onboarding.
