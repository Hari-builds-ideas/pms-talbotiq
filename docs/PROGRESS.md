# PROGRESS — OVERNIGHT_JULY3 run

Running log per `overnight/OVERNIGHT_JULY3_MASTER.md` (iron rule #7). Newest first.
Start state: `main` @ `74ea96b`, backend 1327 tests, smoke 48/48.

---

## AGENT_UX_V3 — make the agent FEEL like an agent ✅ core landed (demo-verified)

**Backend `main` (`0f4f030`, suite 1423):** §A `/api/ai/chat` → inert PLAN for writes (was a single
proposal), session-backed, nothing silently dropped. §B `artifact {type,id,title,state,deeplink}` on
every executed action (real SPA routes). Seed: Vera Lindqvist (Ada's report + DRAFT review) so the
demo story resolves. **Frontend `hari/agent-ui-v2` (`54d40b1`, vitest 114):** one send path, result
cards + Open→, live job tracking, Approve-all-&-run (RTL test), completion + suggestion chip, Ask-AI
top-bar button + subtitle fix.

**Live-verified** on gpt-4o-mini + **`demo_ready.sh` 57/57 ✓**: "start a 360 for Vera and draft her
review" → 2 confirm steps → approve each → feedback_cycle + review artifacts with Open→ links + draft
job; injection executes nothing (goal.approved 50→50). Deferred (flagged, ready-to-run):
`HARI_ATTENTION_NEEDED_agentux.md` — analytics history, GoalUpdate timeline, page-context, session
picker; + the frontend device/visual pass.

---

## File J — Branch tests + E2E smoke ✅ (J2/J3 on `main`; J1 on branches)

- **J2 — agent V2 E2E smoke (on `main`):** extended `scripts/smoke.py` with a
  provider-agnostic agent-V2 section — actions schema, plan create (all steps are
  registered actions, no fabrication), session memory + **session isolation**
  (emp→404), a real per-step approve when a confirm step exists, and the **refusal
  beat** (an injection plans only real actions and executes NOTHING — `goal.approved`
  audit unchanged). **Verified LIVE: 55/55** (was 48/48) against the running stack on
  real gpt-4o-mini.
- **J3 — demo-ready script (on `main`):** `scripts/demo_ready.sh` (recreate web+worker
  → `seed_demo_rich` → wait healthy → full smoke → green/red verdict) + `docs/DEMO_READY.md`.
  **Ran end-to-end: ✓ DEMO READY.**
- **J1 — per-branch composition tests:** `hari/agent-ui-v2` (`PlanChecklist.test.tsx`)
  and `hari/profile-signoff` (`ProfilePage.test.tsx`) already carry theirs; added a
  cockpit RTL test to each of `hari/dash-hrbp` / `dash-admin` / `dash-employee`.

No invariant weakened; the HITL refusal invariant is now proven live in the smoke.

---

## File I — Backend hardening E2/E3 ✅ LANDED on `main` (auto-merge, green)

The two items File E deferred, done as a dedicated pass.
- **E2 — controlled migration:** `manage.py deploy_migrate` — wraps `migrate` in a
  MySQL advisory lock (`GET_LOCK`); a concurrent racer exits 0 (no-op). Prod compose
  `migrate` service now runs it; web/workers boot without migrating. Tests (5):
  lock/skip/release control flow, real GET_LOCK round-trip, real idempotent double-run.
- **E3 — atomic budget:** the Lua reserve gained **EVALSHA + EVAL/NOSCRIPT recovery**
  (survives Redis restart / `SCRIPT FLUSH`), a **soft fail-open fallback** on Redis
  outage (no 500), and a `pms_ai_budget_total{outcome}` metric. Tests (+4): 100
  concurrent vs a 20-cap → exactly 20; EVALSHA recovery; redis-down soft-degrade +
  metric; over-cap metric.

`HARI_ATTENTION_NEEDED_hardening.md` marked RESOLVED;
`docs/SYSTEM_DESIGN_AND_READINESS.md` §3.1 + Deploys row updated to BUILT. No invariant
weakened (fail-open on Redis-down is documented soft behavior + an alert metric).

---

## File H — Reviews AI-body → section cards ✅ review branch `hari/reviews-sections`

The one blind-shippable Reviews sub-win (web↔mobile parity): the AI review body now
renders as designed **section cards** instead of raw markdown.
- `reviewBody.ts` — pure `parseReviewBody(md)` → typed `ReviewSection[]`
  (heading/kind/body/items; robust to `##`/`###`/`#` + whole-line `**bold**`; total,
  never throws).
- `ReviewBodySections.tsx` — a Card per section (green kicker + prose + list) + a
  "View raw" toggle (off by default); falls back to raw text on any parse error.
- `ReviewDetailPage.tsx` — one-line swap of the raw `<p>` for the sectioned render
  (AI-body only; state machine / HITL / layout untouched).
- Tests: `reviewBody.test.ts` (8) + `ReviewBodySections.test.tsx` (3).

Green: tsc, lint, **vitest 118**, build. Structurally testable → low-risk cherry-pick
after Hari's eyeball. The fuller recompose stays flagged
(`HARI_ATTENTION_NEEDED_screen_reviews.md`). Branch `REVIEW_NOTES.md` has before/after.

---

## File G — Mobile parity (no pixels) ⚠️ 2 review branches (green, DO NOT merge)

Both structurally testable (routing + API wiring, not visual composition), so shipped
green without a device pass:

- **`hari/mobile-tab-ia`** (G1) — tab IA recut to mirror the web sidebar: **Home ·
  Goals · Reviews · Recognition · You** (Reviews/Recognition promoted from More;
  Feedback/Career → "You" overflow; route paths unchanged → no deep-link breaks). Tab
  set is pure data in `shared/src/nav/mobileTabs.ts`, unit-tested by
  `frontend/src/test/mobileTabs.test.ts` (web vitest). Green: mobile tsc, expo lint,
  `expo export --platform ios`, vitest (4).
- **`hari/mobile-chat-agent-v2`** (G2) — mobile chat consumes the agent V2
  plan/step endpoints (Ask/Plan modes; inert checklist w/ Approve·Skip·Explain;
  session id in `expo-secure-store`). Added the shared ChatPlan types + aiApi.plan/
  approveStep/listSessions/getSession (same surface the web uses). Contract test
  `frontend/src/test/chatPlanApi.test.ts`. Green: mobile+web tsc, expo lint,
  `expo export` (iOS + web), vitest (3).

Overview + review order in `HARI_ATTENTION_NEEDED_mobile_no_pixel.md` (tab-IA first,
then agent-v2). No RBAC change, no new endpoint, no fabricated data; web invariants
transfer verbatim. Both DO NOT merge — the device/visual pass is Hari's.

---

## File F — Agent actions expansion ✅ LANDED on `main` (auto-merge, green)

**Shipped 5 of 7 new agent actions** (each reuses the SAME audited endpoint a human
uses; capability + scope re-checked at execute; params deterministic; no widened
permission; no new gate):
- `open_checkin` (Employee+, OWN, non-destructive — never clobbers an open week),
- `respond_to_checkin` (Manager+, subtree-scoped),
- `approve_goal` (Manager+, singular sibling of `approve_goals`),
- `schedule_review` (Manager+, navigate-and-prefill `/reviews`),
- `update_kpi_actual` (Owner, `record_actual` + suspicious-value warning; OWN-only).

Plus **`GET /api/ai/actions/schema`** (public per-action metadata; sensitive actions
hidden from callers who can't perform them) and planner integration (2 fake multi-step
plans + 1 live `gpt-4o-mini` plan over the new actions).

**Tests:** +28 (26 action/schema + 2 planner) → full suite **1406 passed, 7 deselected**
(+1 `live_ai`). `web` + `celery-worker` recreated.

**Flagged 2 (can't wire without widening perms / inventing an unaudited write):**
`request_feedback` (no Employee-scoped feedback-request endpoint — invitations are
Manager+) and `nudge_stale_goal` (stale goals are read-only advisory; no per-goal
nudge-send endpoint). Each has a `HARI_ATTENTION_NEEDED_action_*.md` with options.
Suite 1406 is just under the 1408 DoD target — a principled 5-of-7, documented in
`AGENT_ACTIONS_v2.md`. **Invariants (HITL / RBAC / real-data) intact.**

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
