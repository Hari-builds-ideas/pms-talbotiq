# RW_BUILD_5_REPORT — AI quick wins (the AI goal-writer)

The final re-weighting build. The outline offers five quick wins and says to "build whichever you value
most first; each small + self-contained." I shipped the highest-value one — the **AI goal-writer** — and
logged the rest as follow-ups (Q10). It turns a one-line intent into an editable SMART goal draft, runs
through the one `LLMGateway`, and is **HITL: it persists nothing** — the human edits the draft and
creates the goal through the existing scope-gated, audited create path.

Committed, pushed, green, deployed, live-verified.

## What shipped

- **Backend** — `apps/ai/agents/goal_writer.py`: `draft_goal(user, intent)` goes through the gateway
  (budget reserve → PII-scrub → provider call → schema-validate → meter → confidence), with a schema that
  requires a real title + objective and a KPI list. `POST /api/goals/ai-draft` (`GoalAIDraftView`,
  `MANAGE_REPORTS_GOALS`, AI-throttled) maps the gateway result to HTTP (200 draft / 503 no-provider /
  429 over-budget) and **returns a draft — it creates nothing**. A tailored `goal_draft` system prompt.
- **Frontend** — a "Draft with AI" field at the top of the New-Goal dialog: type an intent → it prefills
  the title, objective and KPI rows (weights evenly split to sum to 100, so the draft is immediately
  valid), all editable before the normal Create. `goalsApi.aiDraft` + `GoalDraft*` types in the shared
  layer.

## Why this is safe

- **HITL / persists nothing**: the endpoint returns a draft; the goal is only ever created by the human
  through the existing `MANAGE_REPORTS_GOALS` + scope-checked + audited create endpoint. Proven by a test
  asserting the goal count is unchanged after a draft.
- **Through the gateway**: metered to the TokenLedger, budget-bounded per tenant, and degrades to a clean
  503 with no provider — same guarantees as every other agent.
- **Gated to goal-creators**: `MANAGE_REPORTS_GOALS` (manager+); an employee gets 403.

## Verification

- **[test]** `apps/ai/tests/test_goal_writer.py` (3): a structured draft is returned and **nothing is
  persisted** (FakeLLMProvider); no provider → graceful `not_configured`; the endpoint drafts for a
  manager (200), refuses an employee (403), and 400s an empty prompt. Full backend suite green; frontend
  **93** passing, tsc/lint/build clean.
- **[live]** over HTTP: ada drafts *"improve our sales response time"* → 200 with a real SMART goal
  ("Enhance Sales Response Time" + objective + a KPI) from OpenAI (1 call); the Goal count is unchanged
  (nothing persisted); an employee's draft → 403.

## Decisions / follow-ups

- **D35**: gateway-routed, HITL draft; capability-gated (no new entitlement pack — gateway budget +
  capability cover it; pack mapping is a follow-up).
- **Q10**: shipped one quick win; the other four (1-on-1/meeting summary, review bias/quality flag,
  stale-goal nudge, NL search) are self-contained follow-ups — each via the LLMGateway, HITL, with
  FakeLLMProvider tests.

## Your device check

Hard-refresh http://localhost:8080, log in as **`ada@acme.test`** (Manager) → **Goals & KPIs** → **New
goal** → in **Draft with AI** type *"improve our sales response time"* → **Draft**. The title, objective
and KPIs prefill; edit and **Create**. As **`reza@acme.test`** (Employee) there's no New-goal entry
(goal creation is Manager+). Password `Passw0rd!demo`.

## Series status

This completes RW_BUILD_1 → 5 (navigation re-cut, recognition, check-ins, propose-and-confirm assistant,
AI goal-writer). See `RW_BUILD_1..5_REPORT.md`.
