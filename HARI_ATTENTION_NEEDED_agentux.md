# HARI_ATTENTION_NEEDED — AGENT_UX_V3 remaining items (ready-to-execute plans)

The **demo-critical core of AGENT_UX_V3 shipped** and is live-verified:
- **Backend on `main`** (`0f4f030`): §A one-send-path (`/api/ai/chat` → inert plan for writes),
  §B artifact + deep-link contract on every executed action, the Vera seed. Full suite **1423 passed**;
  demo story live-verified on gpt-4o-mini (plan → approve both → artifacts + job).
- **Frontend on `hari/agent-ui-v2`** (`54d40b1`): §A one send button, §B result cards + Open→,
  §C live job tracking, §D Approve-all-&-run (+RTL test), §E completion + suggestion chip,
  Part 2.1 Ask-AI button + subtitle. Green (tsc/lint/build/vitest 114). **Needs your device/visual pass.**

These four items were NOT landed this session — each is bounded, backend-mostly, and has a plan below.
None is blocked; they were deferred to keep the suite green under one session's time.

## 1. Part 2.2 — Analytics history (3 prior scored cycles)
**Goal:** seed Q4 2025 / Q1 2026 / Q2 2026 (+ current H1) as real `PerformanceCycle` rows with real
recorded actuals + real T-scores via `compute_cycle_scores`, so the individual trend is a 4-point
curve, department aggregates populate, and the calibration grid has a real distribution.
**Plan:** in `seed_demo_rich._goals_and_scores`, loop the existing goal/KPI/measurement build over a
list of cycles (past ones `status="CLOSED"`, dated ranges), varying `ATTAINMENT` per person per cycle
(believable drift), and call `compute_cycle_scores(tenant.id, cycle.id)` per cycle. Reuse the existing
KPI structure. **Test:** extend `test_seed_demo_rich` to assert ≥4 cycles + a `CycleScore` per person
per closed cycle + monotonic-ish variety. ~1–2 hrs; backend-only; idempotent (guard on cycle name).

## 2. Part 2.3 — GoalUpdate model + Updates timeline + relabels
**Goal:** a lightweight "Updates" timeline under each goal + role-appropriate KPI names + plain-English
labels.
**Plan (backend):** add `GoalUpdate(TenantScopedModel)` — `goal FK, author FK, text, created_at`;
migration; an audited `create_goal_update` service (audit `goal.update.added`); `GET /goals/<id>/updates`
+ `POST` (scope = own goal or manager of the owner). **Tests (3):** create / tenant isolation / audit.
Seed 2–4 updates per active goal ("Shipped v2 of the pricing page — Vera, 3 days ago"). Rename the
seed's KPI shells (Throughput/Quality/Impact/Collaboration) to role-appropriate names (PM: "Ship 3
features by end of H1", "Feature adoption > 40%"; Eng: "Merge cycle time < 3 days", "Post-release
incidents 0"; Design: "Design reviews within SLA 95%+"). **Plan (frontend, hari/agent-ui-v2):** an
"Updates" list under each goal card (GET `/goals/:id/updates`); relabel UI jargon —
"actual"→"Progress", "Increasing is better"→"Higher = better ↑" (↓ variant), tooltips on Goal weight +
T-score. ~half-day; new model → migration + recreate.

## 3. §G — Page context awareness (STRETCH)
**Goal:** the panel sends `page_context {route, entity_type, entity_id}`; the backend MAY use it as a
resolution hint for "this person" — with the SAME live access re-check (never widens scope).
**Plan:** frontend passes `page_context` in the `/chat` body; `resolve_person_reference` accepts an
optional context id and, IF `actor_can_access` passes, uses it — else ignores it. **Tests:** in-scope
context resolves "this person"; out-of-scope context is ignored → generic clarify (no leak). Low
priority; only after 1–2 are solid.

## 4. §F — "Recent chats" session picker (partial)
The panel already **persists across nav** (mounted in the shell) and threads the session within an
open panel, and `aiApi.listSessions()/getSession()` exist. **Remaining:** a "recent chats" dropdown
that lists `listSessions()` and, on select, hydrates prior turns from `getSession()`. Frontend-only,
on `hari/agent-ui-v2`. ~1–2 hrs + one RTL test (reopen renders prior turns from a mocked session).

## Also: your visual/device pass on `hari/agent-ui-v2`
The whole V3 UX is green but **pixel-unverified** (the standing rule: the agent can't see pixels).
Run `./scripts/demo_ready.sh` (backend green), then walk the click-path in
`REVIEW_NOTES.md` (Ask AI → "start a 360 for Vera and draft her review" → Approve all & run) and tune
the composition. Nothing here weakens HITL/RBAC/real-data.
