# PROGRESS — OVERNIGHT_JULY3 run

Running log per `overnight/OVERNIGHT_JULY3_MASTER.md` (iron rule #7). Newest first.
Start state: `main` @ `74ea96b`, backend 1327 tests, smoke 48/48.

---

## File D — High-impact screens ⚠️ PARTIAL (1 branch + 3 speced flags)

- **`hari/profile-signoff`** ✅ — added `ProfilePage.test.tsx` (3 RTL): section order locked, honest
  empty states / no fabricated numbers, real goals+reviews in-section. No component change (already
  composed from existing endpoints); reachability from the team table verified. Green, vitest 110.
- **Reviews / Recognition / Feedback recompose** — NOT blind-shipped. A deep visual recompose of three
  working, shipped screens needs Hari's eyes in the loop (standing rule: the agent can't see pixels).
  Each has a concrete, executable plan: `HARI_ATTENTION_NEEDED_screen_{reviews,recognition,feedback}.md`
  (target composition from the spec + the one testable sub-win each + files to touch). Do them as
  one-screen-with-approval passes.

## File C — Dashboard role parity ✅ 3 review branches (green)

- **`hari/dash-hrbp`**, **`hari/dash-admin`**, **`hari/dash-employee`** — each swaps the role's
  `StatCard` grid for the mockup's `DashboardKpiCard` hero row (real data, honest empties, no new
  endpoints), killing the StatCard cliff. Each green (tsc/lint/build/vitest 107) + `REVIEW_NOTES.md`.
  Cherry-pick order in `HARI_ATTENTION_NEEDED_dashboard_role_parity.md`. Not visually verified.

---

## File E — Backend hardening + tests ⚠️ PARTIAL on `main` (auto-merge, green)

**Done:** E4 (tests for flagged-untested code) — `apps/core/tests/test_seed_demo_rich.py` (3):
idempotent (2 runs, stable counts), ACTIVE goal weights sum to 100 for every person, Akhil On Track,
ACME-only. E5 — `PROD_READINESS_STATUS.md` grounded in code.

**Found already in place:** E1 (N+1) — list views use select_related and are regression-guarded by the
existing `[query-budget] … [BOUNDED]` tests (Δ=0 across 5→25 rows). Marked DONE with reference rather
than re-done. Chat-session TTL/isolation tests (E4 item) already landed in File A.

**Not attempted (flagged, need a careful dedicated pass — see HARI_ATTENTION_NEEDED_hardening.md):**
E2 controlled migration command; E3 atomic Redis-Lua budget counters. Deferred to protect
"never push red" under the run's time cap — both backend-only + testable, not blocked.

---

## File B — Chat safety matrix ✅ LANDED on `main` (auto-merge, green)

**Shipped:** `apps/ai/tests/test_agent_safety_matrix.py` — `TestAgentSafetyMatrix`, **24 tests**:
capability refusals (7), scope refusals (5), injection resistance (5), plan-level safety (5), session
isolation (2). Every write row asserts on the audit log; a distinct-tenant fixture covers cross-tenant
isolation; a `_planner_returns` helper forces malicious raw plans to prove `build_plan` sanitizes them
(unknown action dropped, LLM-supplied params ignored, >5 truncated).

**Result:** all green — **no row surfaced a real agent bug** (nothing xfail'd, no
`HARI_ATTENTION_NEEDED_safety_*`). Full suite **1375 passed, 6 deselected**. `SAFETY_MATRIX_REPORT.md`
lists each row + assertion. Live rows = `test_planner_live.py` (4 passed, ≤ cap).

---

## File A — Agentic chat V2 ✅ backend LANDED on `main` (auto-merge, green)

**Commits:** `25be24b` (backend + unit tests), `527d2db` (live gpt-4o-mini tests + `live_ai` marker).

**Shipped:**
- Session memory + plan/per-step-approve models (`ChatSession/ChatTurn/ChatPlan/ChatPlanStep`,
  migration `ai/0004`), all `TenantScopedModel`, owner-bound, 24h TTL.
- `planner.py` (build_plan reuses existing propose_*; cap 5; drops unknown/forbidden; clarify;
  grounded reason; generic omission — no leak) + `approve_step` (row-locked, idempotent,
  out-of-order aware, re-checks cap+scope).
- `sessions.py` (recent-turn memory + cross-turn reference resolution that re-checks live access).
- Two new actions: `record_actual` (OWN-only) + `give_recognition` (tenant-wide) — 4 invariant tests
  each.
- 4 endpoints under `/api/ai/chat/` (plan, approve-step, sessions list/detail), same USE_CHAT +
  entitlement + throttle gating as chat.

**Tests:** +24 unit → **full suite 1351 passed, 2 deselected**. Live: **4 gpt-4o-mini tests passed**
(multi-step order, ambiguity→clarify, injection executes nothing, out-of-scope never resolves).

**Decisions:** reason composed in Python (not trusted from LLM); recognition scope is tenant-wide by
design. Both documented in `AGENTIC_CHAT_V2_REPORT.md`.

**Invariants:** HITL gate, RBAC, real-data — all intact. `web` + `celery-worker` recreated.

**Remaining for A:** frontend agent panel on `hari/agent-ui-v2` (green build; not visually verified).
Docs written: `AGENTIC_CHAT_V2_REPORT.md`, `docs/AGENT_ARCHITECTURE.md`.

**Live AI spend so far:** ~4 gpt-4o-mini calls (fractions of a cent).
