# MORNING_HANDOFF — July 3 overnight run

Ran `overnight/OVERNIGHT_JULY3_MASTER.md`. **The demo-critical win landed: the chat is now a real
agent** (plan → grounded reason → per-step human approve, memory, 2 new actions) — backend live-
verified on `gpt-4o-mini`, and its safety surface is fully automated. Backend stayed **green
throughout** (1327 → **1378 passed**). No invariant weakened; nothing pushed red.

## TL;DR — what to do first
1. **Look at `hari/agent-ui-v2`** (the agent chat panel — the CEO-facing surface). Green build, NOT
   visually verified. Its `REVIEW_NOTES.md` has the exact login + click-path. Cherry-pick/merge after
   your eyes approve.
2. **File C shipped as 3 review branches** (`hari/dash-hrbp|dash-admin|dash-employee`) — dashboard KPI
   parity to the mockup; cherry-pick per `HARI_ATTENTION_NEEDED_dashboard_role_parity.md`.
3. **File D**: `hari/profile-signoff` shipped (Employee Profile test + reachability); the three visual
   recomposes (Reviews / Recognition / Feedback) are speced flags for your visual loop, not
   blind-shipped (see `HARI_ATTENTION_NEEDED_screen_*.md`).

> **Update:** an earlier draft of this handoff said C/D were "not started" (I'd mis-imposed a turn
> cap). Corrected — C is done (3 branches) and D is partial (1 branch + 3 speced flags). All five files
> are now addressed.

## Commits + branches

### `main` (auto-merge, all green, all tested) — 5 commits
| Commit | What changed |
|---|---|
| `25be24b` | **File A** backend: agentic chat V2 — ChatSession/Turn/Plan/Step models (+migration `ai/0004`), planner (LLM emits action names only; params resolved in Python), per-step approve (row-locked, idempotent, out-of-order), session memory + cross-turn refs, 2 new actions (record_actual, give_recognition). +24 tests. |
| `527d2db` | **File A** live: 4 `gpt-4o-mini` planner tests (`live_ai` marker, deselected by default). |
| `e43fc46` | **File A** docs: `AGENTIC_CHAT_V2_REPORT.md`, `docs/AGENT_ARCHITECTURE.md`, `docs/PROGRESS.md`. |
| `5c92401` | **File B**: automated safety matrix — `TestAgentSafetyMatrix` (24), audit-log assertions, cross-tenant fixture. `SAFETY_MATRIX_REPORT.md`. |
| `87f5f8c` | **File E** (partial): `seed_demo_rich` tests (3) + `PROD_READINESS_STATUS.md`. |

### `hari/agent-ui-v2` (review branch — DO NOT merge until you eyeball it) — 1 commit
| Commit | What changed |
|---|---|
| `21d7e84` | **File A** frontend: `PlanChecklist` (numbered checklist, Approve · Skip · Explain, live status), ChatPanel "Plan" button + session threading, shared types + `aiApi.plan/approveStep/listSessions/getSession`. Green: tsc, lint, build, vitest 112 (+5). Not visually verified. |

## `HARI_ATTENTION_NEEDED_*` (decisions/deferrals waiting)
- **`HARI_ATTENTION_NEEDED_hardening.md`** — File E's **E2 (controlled migration command)** and **E3
  (atomic Redis-Lua budget)** were not attempted (need a careful dedicated pass; not blocked).
- (Pre-existing, still open) `HARI_ATTENTION_NEEDED_LIVECHECK.md`, `..._redesign_dashboard_data.md`.
- No new *blocking* decisions surfaced — the agent design held without needing a ruling.

## `hari` branches ready for visual review
- **`hari/agent-ui-v2`** — the agent plan checklist. **Login `ada@acme.test` / `Passw0rd!demo`**, open
  the AI Assistant (top bar), type *"start a 360 for Akhil and draft his review"*, click the
  **checklist (Plan)** button → approve steps one at a time. Full click-path in the branch's
  `REVIEW_NOTES.md`. Compare: does it read like a plan the human drives (not an auto-runner)?

## Live-verified vs green-tests-only
- **Live-verified (real `gpt-4o-mini`):** the planner — multi-step plan in order, ambiguity→clarify,
  injection executes nothing, out-of-scope name never resolves (`test_planner_live.py`, 4 passed).
- **Green tests only (no live check):** the plan/approve/session HTTP endpoints + the 2 new actions
  (unit-tested with FakeLLMProvider + audit-log assertions; not yet clicked through live). The
  **frontend agent panel** is green (tsc/lint/build/vitest) but **NOT visually verified** — your eyes.
- Recreated `web` + `celery-worker` after the backend change (migration applied to the running DB).

## Live AI spend
- ~**8 `gpt-4o-mini` calls** total (4 File-A live planner tests, run twice during iteration). Fractions
  of a cent. No `gpt-4o` (expensive tier) calls. The `live_ai` tests are deselected by default so the
  normal suite never spends.

## Test counts
- **Backend: 1378 passed, 6 deselected** (start 1327 → +51: A +24, B +24, E +3). 6 deselected =
  2 `large_tenant` + 4 `live_ai`.
- **Frontend (on `hari/agent-ui-v2`): 112 vitest passed** (+5 PlanChecklist), tsc + lint + build green.
- Backend `main` build: `python manage.py check` clean.

## `hari` branches created this run (all green, NOT visually verified)
| Branch | File | What |
|---|---|---|
| `hari/agent-ui-v2` | A | agent plan checklist in chat |
| `hari/dash-hrbp` | C | HRBP dashboard KPI parity |
| `hari/dash-admin` | C | Admin dashboard KPI parity |
| `hari/dash-employee` | C | Employee dashboard KPI parity |
| `hari/profile-signoff` | D | Employee Profile RTL test + reachability |

Each has its own `REVIEW_NOTES.md` (login + click-path + deviations).

## What did NOT get done (honest)
- **File D — Reviews / Recognition / Feedback recompose**: not blind-shipped. A deep visual recompose
  of three working, shipped screens needs your eyes in the loop (standing rule: the agent can't see
  pixels; blind-shipping risks an invisible regression on demo screens). Each has an executable plan:
  `HARI_ATTENTION_NEEDED_screen_reviews.md`, `..._recognition.md`, `..._feedback.md` (target
  composition + the one testable sub-win each + files to touch).
- **File E — E2/E3** (controlled migration command, atomic Redis-Lua budget) deferred — see
  `HARI_ATTENTION_NEEDED_hardening.md` (need a careful backend pass; not blocked).

## Suggested next session order
1. Eyeball + merge `hari/agent-ui-v2` (the CEO-facing win), then the 3 `hari/dash-*` branches
   (cherry-pick order in `HARI_ATTENTION_NEEDED_dashboard_role_parity.md`) + `hari/profile-signoff`.
2. Reviews / Recognition / Feedback recompose — one screen at a time with your visual approval (the
   three `HARI_ATTENTION_NEEDED_screen_*.md` files are ready-to-execute). `hari/reviews-sections`
   already does the biggest Reviews sub-win (markdown→section cards) — cherry-pick it first.
3. Device pass on the two mobile branches (`hari/mobile-tab-ia`, then `hari/mobile-chat-agent-v2`).

---

# ADDENDUM — Files F–J (same night, later runs)

Ran `OVERNIGHT_F/G/H/I/J`. **Before any demo, run `./scripts/demo_ready.sh`** — it
recreates the stack, seeds the rich demo, and runs the E2E smoke (now **55/55**,
incl. the agent plan→approve flow + the refusal beat). It went green tonight.

## `main` — auto-merged, all green (backend 1327 → **1415 passed**, 7 deselected)
| Commit | File | What |
|---|---|---|
| `a0ccf8e` | **F** | Agent actions expansion: 5 new actions (`open_checkin`, `respond_to_checkin`, `approve_goal`, `schedule_review`, `update_kpi_actual`) reusing existing audited endpoints + `GET /api/ai/actions/schema` + planner integration + 1 live gpt-4o-mini test. Flagged 2 (see below). +28 tests. |
| `b41f959` | **I** | Backend hardening: `deploy_migrate` (advisory-locked migrations, E2) + atomic budget resilience (EVALSHA/NOSCRIPT recovery, Redis-down soft fallback + metric, E3). +9 tests. `HARI_ATTENTION_NEEDED_hardening.md` → RESOLVED. |
| `68be96e` | **J2/J3** | Agent-V2 E2E in `scripts/smoke.py` (48→**55/55**, live-verified) + `scripts/demo_ready.sh` + `docs/DEMO_READY.md`. |
| `f41df02`, `6413cd5` | G, H | Progress/handoff docs for the branch work below. |

## `hari` review branches created this run (green, DO NOT merge — your eyes/device)
| Branch | File | What | Gate |
|---|---|---|---|
| `hari/reviews-sections` | **H** | Reviews AI body → **section cards** (+ "View raw"); parser + render + tests | tsc/lint/vitest 118/build |
| `hari/mobile-tab-ia` | **G1** | Mobile tab IA recut → Home·Goals·Reviews·Recognition·You | tsc/expo lint/expo export/vitest |
| `hari/mobile-chat-agent-v2` | **G2** | Mobile chat consumes agent V2 (plan/step) + session in secure store | tsc(×2)/expo lint/expo export(iOS+web)/vitest |
| `hari/dash-hrbp` · `dash-admin` · `dash-employee` | **J1** | Added a cockpit RTL test locking each role's KPI hero row | tsc/lint/vitest |

`hari/agent-ui-v2` (`PlanChecklist.test`) and `hari/profile-signoff` (`ProfilePage.test`)
already carried their composition tests — both **re-verified green** this run.

## New `HARI_ATTENTION_NEEDED_*` (decisions waiting)
- **`_action_request_feedback.md`** — File F: no Employee-scoped feedback-request endpoint
  exists (invitations are Manager+); wiring it Employee+ would widen permissions. Options inside.
- **`_action_nudge_stale_goal.md`** — File F: stale goals are read-only advisory; no audited
  per-goal nudge-send endpoint to reuse. Options inside.
- **`_mobile_no_pixel.md`** — review order for the two mobile branches (tab-IA first).
- (`_hardening.md` now marked ✅ RESOLVED — E2/E3 shipped.)

## Live-verified vs green-tests-only
- **Live-verified (real gpt-4o-mini):** the File F planner over the new actions
  (`test_planner_live.py`), and the **full E2E smoke 55/55** — the agent plans, remembers
  (session), isolates (emp→404), and REFUSES (an injection plans only registered actions and
  executes nothing — `goal.approved` audit unchanged, proven live).
- **Green tests only:** the 5 File F actions' unit/HTTP tests (FakeLLMProvider); every `hari`
  branch (tsc/lint/build/expo — NOT visually/device verified).

## Live AI spend (this run)
~**6 gpt-4o-mini calls** total (1 File-F live planner test + ~4 across two smoke runs).
Fractions of a cent. No `gpt-4o` (expensive tier). `live_ai` tests stay deselected by default.

## Test counts (end of night)
- **Backend: 1415 passed, 7 deselected** (start-of-run 1378 → +37: F +28, I +9; 7 deselected =
  2 `large_tenant` + 5 `live_ai`).
- **E2E smoke: 55/55** against the live stack.
- Frontend: web suite 118 (on `hari/reviews-sections`); each `hari` branch green on its own gate.

## What did NOT get done (honest)
- **File F**: `request_feedback` + `nudge_stale_goal` — flagged, not shipped (no clean/Employee-scoped
  audited endpoint; wiring them would widen permissions or invent an unaudited write). Shipped 5 of 7.
- The Reviews/Recognition/Feedback **full visual recompose** still needs your eyes (unchanged from the
  first run; `hari/reviews-sections` does the one mechanical Reviews sub-win).
- Nothing pushed to origin (outward-facing; left for your review).

---

# ADDENDUM 2 — AGENT_UX_V3 (make the agent FEEL like an agent)

**The write is real but the experience said "nothing happened."** Fixed the experience without
touching the gate. **`./scripts/demo_ready.sh` → 57/57 ✓ DEMO READY.**

## `main` — auto-merged, green (backend suite **1423 passed**)
| Commit | What |
|---|---|
| `0f4f030` | **§A** `/api/ai/chat` returns an inert PLAN for a write (was a single proposal); session-backed; nothing silently dropped. **§B** every executed action returns an `artifact {type,id,title,state,deeplink}` on REAL SPA routes (result cards + Open→). **Seed:** Vera Lindqvist (Ada's report + DRAFT review) so the demo story resolves. +7 artifact tests + chat write→plan contract; smoke → plan flow. |

## `hari/agent-ui-v2` — extended (green: tsc/lint/build/**vitest 114**; DO NOT merge — device pass)
| Commit | What |
|---|---|
| `54d40b1` | **§A** one Send (no separate Plan button). **§B** ResultCard + Open→. **§C** live job tracking (reuses `useAIJob`). **§D** Approve-all-&-run (sequential; stops on failure; RTL test). **§E** completion summary + suggestion chip. **Part 2.1** sparkle "Ask AI" top-bar button + corrected panel subtitle. |

## Live-verified — the target demo story, end to end on gpt-4o-mini
```
Ada: "start a 360 for Vera and draft her review"  → POST /api/ai/chat → status=plan (2 steps)
  step 1: initiate_360 [confirm]  "Vera Lindqvist is in your team, so you can open a 360…"
  step 2: draft_review [confirm]  "Vera Lindqvist's review is in DRAFT and within your scope…"
Approve step 1 → done · artifact feedback_cycle "360 — Vera Lindqvist" DRAFT · Open → /feedback
Approve step 2 → done · job_id=… (async draft) · artifact review "Review — Vera Lindqvist"
                 AI_DRAFTING · Open → /reviews/{id}
session detail → 2 turns (memory)
```
`demo_ready.sh` also asserts it live: write→plan (one send path), 2 registered-action steps,
approve → artifact + `/feedback` deep link, session isolation (emp→404), and the refusal beat
(injection plans only registered actions, `goal.approved` audit unchanged 50→50).

## Live AI spend (this run)
~**8 gpt-4o-mini calls** (the demo-story verify + demo_ready's smoke). Under the ≤10 cap. No gpt-4o.

## Follow-up pass (later same run) — Part 2.2 + 2.3 landed
- **Part 2.3 — GoalUpdate** (`main` `73e8cb3`): a `TenantScopedModel` progress-note timeline under
  each goal (migration 0004) + audited endpoint `GET/POST /api/goals/:id/updates` + 5 tests + seeded
  updates; KPI shells renamed to concrete names; "actual"→"Progress", direction→"Higher/Lower =
  better". UI timeline + relabels on `hari/agent-ui-v2` (`e2919d5`, +3 RTL). (Weight/T-score tooltips
  already existed.)
- **Part 2.2 — analytics history** (`main` `73e8cb3`): 3 prior CLOSED cycles (Q1/Q2/H2 2025) with
  real recorded actuals + real T-scores via the scoring engine → a 4-point individual trend +
  dept/calibration history. Goals built ACTIVE→scored→ARCHIVED so the ACTIVE-weight=100 invariant
  still holds; idempotent. +1 test. Backend suite **1429 passed**.
- **Part 2.4** current-cycle actuals were already seeded.

## Still flagged — `HARI_ATTENTION_NEEDED_agentux.md` (small, ready-to-run)
§G (page-context, stretch), §F recent-chats session picker (the panel already persists; the picker
is the bit left), per-role KPI-naming polish — plus your **device/visual pass** on `hari/agent-ui-v2`
(the standing "agent can't see pixels" rule). None blocked.
