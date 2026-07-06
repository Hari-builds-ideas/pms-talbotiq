# HARI_ATTENTION_NEEDED — AGENT_UX_V3 remaining items (ready-to-execute plans)

**AGENT_UX_V3 is substantially finished.** §A–§F + Part 2.1–2.4 shipped, tested green, and the
demo story is live-verified on gpt-4o-mini (`demo_ready.sh` 57/57). What's left is small and flagged.

## Shipped (this run)
- **§A one send path** (`/api/ai/chat` → inert plan for writes) — `main`.
- **§B artifact + deep links** on every executed action — `main`.
- **§C** live job tracking, **§D** Approve-all-&-run (+RTL), **§E** completion + suggestion chip,
  **§F** panel persistence, **Part 2.1** Ask-AI button + subtitle — `hari/agent-ui-v2`.
- **Part 2.2** analytics history: 3 prior CLOSED cycles with real T-scores (4-point trend +
  dept/calibration) — `main`. **Part 2.3** GoalUpdate model + Updates timeline + KPI-name/label
  relabels (actual→Progress, direction→Higher/Lower = better) — `main` (model/endpoint/tests/seed) +
  `hari/agent-ui-v2` (timeline UI). **Part 2.4** current-cycle actuals — already seeded.
- Seed: Vera Lindqvist (Ada's report + DRAFT review) so the demo story resolves.

Backend suite **1429 passed**; web **vitest 117**; `demo_ready.sh` **57/57**.

## Remaining (small; not blocked)
1. **§G — page-context awareness (STRETCH).** Frontend sends `page_context {route, entity_type,
   entity_id}` with each message; `resolve_person_reference` MAY use it as a hint — with the SAME
   `actor_can_access` re-check (never widens scope; out-of-scope context ignored → generic clarify).
   Tests: in-scope resolves "this person"; out-of-scope ignored. Do after everything else.
2. **§F — "recent chats" session picker.** The panel already PERSISTS in the shell + threads the
   session; remaining is a dropdown that lists `aiApi.listSessions()` and hydrates prior turns via
   `getSession()`. Frontend-only on `hari/agent-ui-v2`; ~1–2 hrs + one RTL test.
3. **Per-role KPI naming polish.** The seed KPI shells were renamed to concrete names
   (Features shipped / Release quality / Cross-team impact / Collaboration & mentoring); a further
   pass could vary them by department (PM vs Eng vs Design). Cosmetic seed data.

## Your device/visual pass on `hari/agent-ui-v2`
The whole V3 UX is green but **pixel-unverified** (the standing rule: the agent can't see pixels).
Run `./scripts/demo_ready.sh`, then walk the click-path in `REVIEW_NOTES.md` (Ask AI → "start a 360
for Vera and draft her review" → Approve all & run) and tune composition. Nothing here weakens
HITL/RBAC/real-data.
