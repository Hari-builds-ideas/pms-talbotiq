# AI quick win 1 — 1-on-1 / meeting summary (report + UI follow-up spec)

Built overnight, **backend-only + additive** (see DECISIONS D36): a stateless AI summary of meeting /
1-on-1 notes. HITL — it drafts, never decides, and **persists nothing**.

## What shipped (backend)

- **Agent** `apps/ai/agents/meeting_summary.py::summarize_meeting(user, notes)` — through the one
  `LLMGateway` (budget → PII-scrub → schema-validate → meter → confidence). Schema = `{summary:
  non-empty, action_items: list}`. Returns a status dict (ok / not_configured / budget / error).
- **Endpoint** `POST /api/ai/meeting-summary` (`MeetingSummaryView`) — body `{"notes": str}` → `{status:
  "ok", summary: {summary, action_items}, confidence}`. Gated by `USE_CHAT` + the chat entitlement,
  AI-throttled. Maps the gateway result to HTTP: 200 / 503 (no provider) / 429 (over budget); 400 on
  empty notes. **Creates nothing.**
- **Prompt** `agent_config.py::_MEETING_SUMMARY` (tunable via `settings.LLM_SYSTEM_PROMPTS`).
- **No** change to auth/SSO/shared/deploy/nav/RBAC-matrix; reuses `USE_CHAT`.

## Verification

- **[test]** `apps/ai/tests/test_meeting_summary.py` (3): structured summary + action_items
  (FakeLLMProvider); no provider → `not_configured`; endpoint 200 + empty-notes 400. Full backend suite
  green; frontend build/tsc/lint untouched + green. **No live OpenAI calls.**

## UI follow-up (for review — NOT built overnight; would touch shared layer + a screen)

When you want it surfaced, the smallest safe wiring:
1. `shared/src/api/endpoints.ts`: `aiApi.meetingSummary = (notes) => unwrap<{summary:{summary:string;
   action_items:string[]}}>(api.post("/ai/meeting-summary", { notes }))` + a `MeetingSummary` type.
2. A "Summarise with AI" button on a notes textarea — natural home is the **manager's check-in response**
   (RW_BUILD_3 `CheckInsPage` "My team" tab) or a future 1-on-1 notes screen: paste/echo notes → call →
   show the summary + action items as an editable draft the manager keeps.
3. No new nav item needed (it lives inside an existing screen).
