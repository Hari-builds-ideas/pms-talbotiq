# PROGRESS.md — production-hardening build series (BUILD_1…9)

> Append-only log. Verification honesty: **[test]** asserted by a test ·
> **[live]** exercised over real HTTP · **[build]** build/typecheck/lint only.

## Current: OVERNIGHT — AI quick wins (Q9/Q10), backend-only + additive (D36)

Unattended overnight: the remaining AI quick wins, each a backend-only additive feature in `apps/ai`
(new agent + endpoint + tests via the LLMGateway; existing models read-only; existing capabilities
reused — no matrix change; FakeLLMProvider, ZERO live OpenAI). UI wiring deferred to per-feature
`docs/AI_QUICKWIN_*.md` specs (shared layer + nav are do-not-touch). Full suite + frontend gates after
each; green→commit+push, red→BLOCKER+skip.

- **(1) 1-on-1/meeting summary DONE** — `agents/meeting_summary.py` + `POST /api/ai/meeting-summary`
  (USE_CHAT + chat entitlement). Stateless notes→{summary, action_items}, persists nothing. **[test]**
  `test_meeting_summary.py` (3). Frontend untouched/green. `docs/AI_QUICKWIN_1_MEETING_SUMMARY.md`.

## RW_BUILD_5 (DONE) — AI quick wins (the AI goal-writer)

The final re-weighting build. Shipped the highest-value quick win — an AI goal-writer — via the one
LLMGateway, HITL (a draft, never auto-saved).

- **DONE** — `apps/ai/agents/goal_writer.py` (`draft_goal` through the gateway: budget→scrub→validate→
  meter→confidence; schema = title+objective+kpis). `POST /api/goals/ai-draft` (`GoalAIDraftView`,
  MANAGE_REPORTS_GOALS, AI-throttled) returns an editable draft and persists NOTHING — the human edits +
  creates via the normal scope-gated/audited path. Frontend: a "Draft with AI" field in the New-Goal
  dialog prefills title+objective+KPIs (weights split to sum 100). `goalsApi.aiDraft` + types in the
  shared layer; tailored `goal_draft` system prompt. **[test]** `test_goal_writer.py` (3): structured
  draft + nothing persisted (FakeLLMProvider), no-provider→503, endpoint manager-200/employee-403/empty-400.
  Frontend 93 green. **[live]** ada drafts "Enhance Sales Response Time" (1 OpenAI call), nothing
  persisted, employee→403. D35, Q10. The other four quick wins (1-on-1 summary, bias flag, stale-goal
  nudge, NL search) are logged follow-ups.

## RW_BUILD_4 (DONE) — AI assistant: read-only → propose-and-confirm (HITL)

The headline AI upgrade. The chat may now PROPOSE a supported action (an inert Approve/Cancel card);
nothing executes until the human taps Approve → `POST /api/ai/actions/execute`, which re-checks
capability + scope on the real targets (= the human path) and audits each effect.

- **DONE** — `apps/ai/actions.py` registry + `approve_goals` (mirrors `GoalApproveView` exactly:
  APPROVE_GOALS + `actor_can_access(employee)` + `goal.approved` audit + stamp). chat.py write-intent →
  proposal (deterministic action match; LLM only decides it's a write); `ChatActionExecuteView`
  (`/api/ai/actions/execute`, USE_CHAT + chat entitlement, AI-throttled). Frontend: the chat renders the
  proposal as an Approve/Cancel card → `aiApi.executeAction` → invalidates goals. **[test]**
  `test_actions.py` (6): proposal-writes-nothing, execute approves+audits-once + idempotent, out-of-scope
  refused at execution, employee gets no proposal + 403 on execute, HTTP endpoint. Frontend 93 green.
  **[live]** ada chat→proposal (1 OpenAI call), Approve→execute 200/approved 1, 1 audit row, employee→403.
  D34, Q9. No new capabilities (reuses USE_CHAT + APPROVE_GOALS) so no matrix change.

## RW_BUILD_3 (DONE) — Weekly Check-ins

New `apps/checkins` (backend-first). The core engagement loop: an employee writes a weekly check-in
(mood/wins/blockers/learning/priorities), their manager reads + responds; scope enforced server-side.

- **3.1–3.3 (backend + UI + seed) DONE** — `CheckIn` + `CheckInPriority` + `ManagerResponse`
  (TenantScopedModel), migration 0001. Services own the scope: own writes/reads; a manager reads/responds
  within their subtree (cross-manager/peer → 404; cross-tenant impossible). One check-in per (author,
  week); priorities replace on re-submit; goal progress is a **read-only pull** from the goals engine (no
  duplication). Endpoints `/api/checkins/` (mine/upsert), `/team`, `/<id>` (+goal_progress), `/<id>/respond`.
  Caps MANAGE_OWN_CHECKIN (_EVERYONE), VIEW_TEAM_CHECKINS/RESPOND_CHECKIN (_MANAGER_UP). Frontend:
  CheckInsPage (weekly form + my history + a manager "My team" tab with inline respond), `/checkins` route,
  **Check-ins** nav item (Workspace, all roles). Seed: 1 check-in (+2 priorities +manager response)/tenant,
  idempotent. **[test]** `test_checkins.py` (9: scope, cross-manager 404, tenant isolation, one-per-week,
  priorities-replace, manager-response rules, read-only goal pull) + frontend (role-aware tabs). **[live]**
  ada sees reza's check-in / lin (other mgr) gets empty feed + 404. D33, Q8. AI summary deferred to RW_4/5.

## RW_BUILD_2 (DONE) — Recognition (kudos card + feed)

New `apps/recognition` (backend-first). The load-bearing property is **server-enforced visibility** — a
card reaches exactly its permitted audience and no one else.

- **2.1 (model + visibility-enforced API) DONE** — `Recognition` + `RecognitionReaction`
  (TenantScopedModel), migration 0001 applied. Services own the security: `recognition_feed` builds the
  visibility predicate as one Q-object (PRIVATE=parties only — even from Admin; MANAGER_ONLY=+recipient's
  manager; TEAM=+immediate team of either party; COMPANY=tenant). React only to a card you can see (else
  404). Sender-only soft delete, no self-recognition, fixed company-values list. Endpoints under
  `/api/recognition/` (feed/create, react, delete, meta). Caps added: GIVE_RECOGNITION/VIEW_RECOGNITION
  (_EVERYONE), VIEW_RECOGNITION_ANALYTICS (_MANAGER_UP). **[test]** `test_recognition.py` (9) incl. the
  8×4 **visibility matrix** + tenant isolation (cross-tenant recipient/feed) + reactions + delete. D32, Q7.
- **2.2 (light analytics) DONE** — `recognition_analytics` aggregate-only (total, top values, visibility
  breakdown, caller's own given/received) — no per-person leaderboard (privacy). **[test]** covered.
- **2.3 (UI: card + feed) DONE** — `features/recognition/` (RecognitionPage feed + give dialog + reaction
  toggles + sender-only delete), `useRecognition` hooks, `recognitionApi` + types in the shared layer,
  route `/recognition`, and the deferred **Recognition** nav item added to the Workspace set (EMPLOYEE+).
  **[test]+[build]** RecognitionPage.test.tsx (feed render + per-card visibility label + empty-state) +
  nav.test.ts updated; frontend 88→**91**, tsc/lint/build clean.
- **2.4 (seed) DONE** — `seed_demo._recognitions`: 4 cards/tenant across PRIVATE/MANAGER_ONLY/TEAM/COMPANY,
  idempotent (keyed on sender+recipient+message; verified 4 after two runs). **[live]**.

## RW_BUILD_1 (DONE) — Navigation re-cut + RBAC visibility (per role)

Re-weighting series (UI/permissions only, no new backend): each role's sidebar + dashboard show ONLY
what it can use; enterprise screens demoted to an HR/Admin "Advanced" area; server-side gating unchanged
(defense in depth). Grounded in `apps/rbac/matrix.py` — every capability is granted to an upward-closed
role slice, so a per-item `minRole` is exactly a capability check.

- **1.1 (audit map) DONE** — wrote `docs/NAV_RBAC_MAP.md`: every route → primary-landing capability →
  section → who-sees, with current mismatches flagged. Key finding: the EmployeeCockpit tiles link to
  `/goals`,`/reviews`,`/feedback` but the sidebar hides them AND the router over-gates them at `MANAGER`,
  though the backend grants own-scoped access (`VIEW_OWN_GOALS`/`VIEW_OWN_REVIEW`/`GIVE_FEEDBACK`) — the
  "dashboard then no access" complaint. See **D31**; Q3–Q5 logged. **[doc]** (commit `38e4354`).
- **1.2 + 1.3 (gate + demote) DONE** — `navForRole(role)` in `nav.ts` (pure, the source the sidebar
  renders + tests assert): Workspace(EMPLOYEE) Home/Goals/Feedback/Reviews/Career · Team(MANAGER)
  Approvals/Team-Analytics · Advanced(HRBP) Succession/Org/JD/Audit · Administration(ADMIN). Dropped the
  over-strict `RoleGate min=MANAGER` on /goals,/reviews,/feedback (backend already own-scopes — not a
  weakening). Intra-screen gates: Goals New/Recompute, Feedback Cycles tab, Reviews New review → Manager+.
  ManagerCockpit succession entry point removed (demoted; backend unchanged; Q6). **[test]+[build]** +5
  vitest (`nav.test.ts`); frontend 83→**88**, tsc/lint/build clean. (commit `9a6e546`).
- **1.4 (defense in depth) DONE** — `apps/rbac/tests/test_recut_surface_gating.py` (+9) over the REAL
  endpoints: employee→succession 404, employee→dept-analytics 403, manager→audit/calibration 403,
  HRBP→admin-users/integrations 403; employee→own goals/reviews/feedback-requests 200 (no dead links).
  Backend 1213→**1222**, 2 deselected. **[test]** (commit pending). RW_BUILD_1_REPORT.md written.

## (prev) PRODUCT-VALIDATION BUGFIX SWEEP (web only) — ALL 4 blocking bugs FIXED ✓ (root-cause + test + live, committed/pushed each) + BUGFIX_REPORT.md

4 HIGH bugs fixed 1→4: (1) Goals Approve stale row = frontend invalidation-key
mismatch (prefix fix; also fixes recompute/record-actual "did anything happen?"); (2)
Request-AI-Draft unreachable = seed had no DRAFT review for the demo manager + `_ensure`
never reset drift (seed fix); (3) employee roadmap dead link = frontend over-gate
(read-only own roadmap, D28); (4) AI assistant dumped metrics for everything = binary
intent (now write/performance/capability/general, D29). backend 1194→**1201**, frontend
74→**76**, tsc/lint/build clean. Each [test]+[live]. See ordinals 44–47. BUGFIX_REPORT.md
written.

## (prior) WEB_COE build · W1 SSO ✓ · W2 WCAG 2.1 AA ✓ · W3 functional matrix ✓ — ALL THREE DONE + WEB_COE_REPORT.md · (mobile mock-adaptation PAUSED)

W3 done: mapped the brief's testing row (review transitions, KPI=100, escalations,
notifications) to the existing suite, filled the genuine gaps (+8 tests): review
route_rejected APPROVED→EDITING (+illegal guard), PARALLEL-step escalation, notification
DELIVERY (signal→receiver→notifier for approval-assign/escalate + feedback-invite), KPI=100
on PATCH. Full backend 1193 (was 1185). [live] on running stack: KPI 99.99/100.01→400,
100.00→201; real escalate_overdue_routes sweep escalated MANAGER→HRBP (scanned1/escalated1/
errors0), notifier path fired (Slack no-op). docs/FUNCTIONAL_TEST_MATRIX.md written. See
ordinal 43. NEXT: WEB_COE_REPORT.md.

W2 done: axe-core guard renders 14 Admin-Hub screens + the ⌘K palette in the real
shell w/ MSW data → 0 WCAG A/AA violations (was 7); a token-contrast guard parses
globals.css → all 14 text pairs ≥4.5:1 (fixed 7 failing: 6 badge tones + muted-fg by
darkening the tone tokens). Fixes: select/input aria-labels, skip-link + main target +
nav label, Topbar icon-button labels, nine-box drag KEYBOARD ALT (move-to-box menu),
command-palette dialog title, global visible focus outline, reduced-motion CSS. frontend
72 vitest (43+15 a11y+14 contrast), tsc/lint/build clean. docs/ACCESSIBILITY.md (honest:
automated-AA clean + listed manual/AT items, no full-conformance claim). DECISIONS D26.
See ordinal 42.

COE web/back-end gap-closing per WEB_BUILD_COE.md (read in full w/ COE_REQUIREMENTS_MAP.md
+ BUILD_0). W1 done: OIDC verified end-to-end + a real SAML 2.0 SP added (python3-saml,
per-tenant config, signed-assertion validation, tenant isolation, attribute→role JIT
sync+audit, replay/expiry guards) — proven by 12 mock-IdP tests + a live signed
round-trip, full suite 1185 green. docs/SSO.md written, DECISIONS D25. See ordinal 41.
NEXT: W2 (WCAG 2.1 AA axe pass + fixes + a11y guard), W3 (functional test matrix), then
WEB_COE_REPORT.md. 🔑 honestly flagged as NOT code: a real prod IdP (Okta/Azure), TLS/
AES-at-rest, pen-test, the prod LLM key, user manuals.

## (prior) FINAL PUSH · BUILD_6+7 COMPLETE · BUILD_8 mobile IN PROGRESS (8.1 shared extraction ✓ web green; 8.2 Expo scaffold ✓ bundles — AWAITING Hari's device run)

BUILD_6 + BUILD_7 complete/pushed/green. The earlier BUILD_8/9 block is LIFTED —
Hari confirmed an Expo runtime (Expo Go iPhone + iOS simulator). Now executing the
mobile series for real, phase by phase, stopping after each screen for Hari to run
it on the phone. 8.1 (shared-layer extraction) done + web green. See ordinal 39.

BUILD_6 (stabilize) + BUILD_7 (Tier-3) fully delivered, pushed, green (backend
1171, frontend 43 vitest). BUILD_8/9 are the mobile (Expo) series — every phase's
acceptance is a device/simulator run, which this headless terminal can't provide
(no simulator/emulator/device/Expo Go/browser). Per the blocker rule: did NOT
risk the green web app on an unvalidatable core-infra refactor; wrote
BLOCKER_8_mobile_runtime.md (a decision-complete, ready-to-execute plan) + BUILD_8_REPORT.md
+ FINAL_PUSH_COMPLETE_REPORT.md. See ordinal 38.

BUILDs 1–5 COMPLETE/pushed/green (web UX concrete work done; backend 1144 passing).
Final push started: BUILD_6 (stabilize: org-chart crash + not-iterable sweep + the
3 Q1 large-tenant items) → BUILD_7 (Tier-3: review comments + nine-box reposition,
backend-first) → BUILD_8 (mobile foundation) → BUILD_9 (mobile screens). BUILD_6 COMPLETE: 6.1 (org crash), 6.2 (admin pagination+search), 6.3 (scoped
single score), 6.4 (org lazy-load), 6.5 (stabilization sweep — found+fixed a
malformed-UUID-param 500 class via a custom exception handler). BUILD_6_REPORT.md
written. Next: BUILD_7 (Tier-3: review comments + nine-box reposition). BUILD_5
recap below.

### BUILD_5 recap
BUILD_5 delivered: 5.1, 5.2, 5.4a, 5.4b, 5.5 (+5.5b), 5.6, 5.7. The concrete,
functionally-verifiable UX that needs neither new backend scope nor the design
skills is done. Remaining (A) subjective VISUAL pass; (B) the two Tier-3 features
— now being built in BUILD_7. See SERIES_COMPLETE_REPORT.md.

BUILDs 1–4 complete/pushed/green (backend 1123 passed, 2 deselected). BUILD_5:
delivered 5.1 (actionable command center), 5.6 (AI-job UI tests, frontend 30
passed), 5.7 (mobile readiness gate = GO). The deep subjective UX redesign
(5.2–5.5) is flagged for Hari's eye + a pass with the design skills (which were
NOT available in this env — `frontend-design`/`web-design-guidelines`/
`theme-factory` all returned Unknown skill). See BUILD_5_REPORT.md +
SERIES_COMPLETE_REPORT.md.

BUILD_3 COMPLETE: 3.1–3.4 + report committed/pushed/green (`784a69f`); backend
1107 passed, 2 deselected; atomic limits + DB router (replica-ready) live.

BUILD_2 COMPLETE: 2.1–2.5 + report committed/pushed/green (`a27f8d3`); backend
1092 passed, 2 deselected; frontend clean; all 5 AI seams async; chat stays sync.
Tests use REAL django-redis (scratch DBs 15/14) → Lua scripts testable.

BUILD_1 COMPLETE: 1.1–1.5 + report + specs committed/pushed/green (`5e9f9fb`);
backend 1073 passed, 2 deselected; frontend clean.

Key BUILD_2 finding: all 5 AI seams are ALREADY `@shared_task`s
(`draft_review_with_agent1`, `summarize_feedback`,
`enrich_succession_with_agent4`, `generate_jd`, `generate_roadmap`) that bind
tenant ctx, set artifact PENDING, meter via gateway, degrade gracefully — the
views just call them SYNC. BUILD_2 = add AIJob status record + flip to `.delay()`
+ poll API. Not a rewrite.

### BUILD_1 headline — query count per page, before → after (5→25 rows)

| endpoint | before | after |
|---|---|---|
| reviews | 18 → 78 (Δ60, N+1) | 3 → 3 (Δ0) |
| goals | 23 → 103 (Δ80, N+1) | 4 → 4 (Δ0) |
| org positions | 13 → 53 (Δ40, N+1) | 3 → 3 (Δ0) |
| feedback cycles | 8 → 28 (Δ20, N+1) | 3 → 3 (Δ0) |
| jd library | 8 → 28 (Δ20, N+1) | 3 → 3 (Δ0) |
| career roadmaps | 8 → 28 (Δ20, N+1) | 3 → 3 (Δ0) |
| succession bench | 3 → 3 (already bounded) | 3 → 3 (Δ0) |

Every paginated list is now O(1) in rows; worst offender (goals) 103 → 4.
Guard: `test_query_budgets.py` runs in the normal suite (`ENFORCE_BOUNDED=True`);
sanity-checked — removing a `select_related` turns it red. Full doc:
`docs/QUERY_BUDGETS.md`.

Baseline (start of series): backend suite **1065 passing** (grew from the
contract's stated 1059 via the names + display work). Stack runs as one Docker
compose (`web`, `mysql`, `redis`, `celery-worker`, `celery-beat`, `flower`,
`frontend`).

---

## N+1 baseline (Phase 1.1, recorded run · query count at 5 vs 25 list rows)

| endpoint | path | 5 rows | 25 rows | Δ | verdict |
|---|---|---|---|---|---|
| reviews | `/api/reviews/` | 18 | 78 | 60 | N+1 (~3/row) |
| goals | `/api/goals/` | 23 | 103 | 80 | N+1 (~4/row) |
| org-positions | `/api/org/positions` | 13 | 53 | 40 | N+1 (~2/row) |
| feedback-cycles | `/api/feedback/cycles` | 8 | 28 | 20 | N+1 (~1/row) |
| jd-library | `/api/jd/` | 8 | 28 | 20 | N+1 (~1/row) |
| career-roadmaps | `/api/career/roadmaps` | 8 | 28 | 20 | N+1 (~1/row) |
| succession-bench | `/api/succession/critical-roles/{id}/bench` | 3 | 3 | 0 | already BOUNDED |

Cause: the `*_name`/`*_title` SerializerMethodFields added in the UUID→name fix
deref person/entity FKs per row on lists that lacked `select_related`. Phase 1.2
fixes each view's `get_queryset` and flips `ENFORCE_BOUNDED=True`.

---

## Log

(ordinal · build/phase · what · files · verification · commit)

48 · AI/provider · switch active LLM provider Groq → OpenAI (config + small provider class, NOT a rewrite; Groq kept by config) · DECISION D30. NEW `apps/ai/openai_provider.py::OpenAIProvider` mirrors `groq.py` — same gateway contract + OpenAI-compatible Chat Completions JSON-mode shape; diffs are base URL (`OPENAI_BASE_URL`), key (`OPENAI_API_KEY`, Bearer), model map, and a JSON-mode guard (OpenAI `json_object` needs "json" in the messages). settings: +`OPENAI_API_KEY`/`OPENAI_BASE_URL`, `LLM_MODEL_MAP` defaults → **gpt-4o** (review/feedback/succession/jd/career) + **gpt-4o-mini** (chat/default), `LLM_MAX_CALLS` default 0→**60** (OpenAI is PAID — global ceiling now ON). docker-compose: `LLM_PROVIDER` default → OpenAI provider, +OPENAI_* env (Groq lines kept for switch-back). `.env.example` documents the OpenAI vars. `groq.py` untouched. Safety intact: no key→503, over-budget→429, HITL PENDING, TokenLedger metering, anonymised feedback, name-free succession, read-only/RBAC chat. Key read from env only (never hardcoded/printed/staged; staged diff scanned for `sk-`). · **[test]** `apps/ai/tests/test_openai_provider.py` (8, `requests` mocked — NO network: parses OpenAI shape, builds Bearer+json_object request, non-JSON→error, finish=length→0.6 confidence, 400 no-body-leak, json guard injects, global ceiling blocks, model map); FakeLLMProvider still covers agent graphs; FULL backend **1209**/2 deselected (+8) · **[live]** ⏳ ONE OpenAI smoke PENDING Hari confirming the key in `.env` (1 review-draft or chat → PENDING, metered, confidence) · commit `AI — add OpenAI provider, switch from Groq by config (Groq retained)`

47 · BUGFIX/BUG4 · AI assistant returned the same perf-metrics summary for EVERY query · ROOT CAUSE: `chat_answer` classified intent BINARY (write vs read); every non-write query (incl. "I feel lonely", "what day is today?", "what can you do?") fell through to the grounded goals+score answer → metrics dump for everything. FIX (`apps/ai/agents/chat.py`): 4-way intent `write | performance | capability | general` + routing — write→refusal (unchanged), performance→existing grounded RBAC-scoped goals+score (`read` kept as legacy alias), capability→assistant description, general→polite decline+redirect (NEVER metrics). Updated `_CHAT` LLM system prompt (`agent_config.py`) to the 4 intents; `_fake` FakeLLMProvider classifier mirrors deterministically (write→capability→performance→general, write first); frontend mock chat handler (`handlers.ts`) mirrors the same routing. RBAC-scoping + write-block UNCHANGED (every perf fetch still via `actor_can_access`). DECISION D29. · **[test]** `test_chat.py` +5 (capability not-metrics, 3 general params not-metrics, grounded-still-answers) — 14 pass; FULL backend **1201**/2 deselected (+5); frontend tsc/lint/build clean · **[live]** real chat_answer + gateway + FakeLLMProvider on the demo DB (no real LLM): perf "how am I doing this cycle?"→performance+data; "I feel lonely"/"what day is today?"→general, no data; "what can you do?"→capability; "approve review 123"→write/blocked · commit `BUGFIX BUG4 — chat honours intent (perf / capability / general / write-blocked)`

46 · BUGFIX/BUG3 · employee Career-Roadmap tile → "You do not have access" (dead link) · ROOT CAUSE (frontend over-gate): the dashboard's `MyRoadmapTile` (Panel `to="/career"`) is shown to employees, but `router.tsx` wrapped `career/*` in `RoleGate min="MANAGER"` (and `nav.ts` Career was MANAGER+) → employee click hit the gate → 403 page. The BACKEND already allows it (`VIEW_CAREER_ROADMAP` = `_EVERYONE`, OWN scope; live: employee GET /api/career/roadmap → 200, 1 own roadmap). DECISION D28: show employees their OWN roadmap READ-ONLY (don't hide — the tile advertises it + the server authorizes it). FIX (frontend only): removed the career RoleGate (route now just `<CareerPage/>` under AuthGuard); `nav.ts` Career `minRole: EMPLOYEE`; `CareerPage` gates the "My team" tab + ALL manage controls (choose/change target, refresh, AI-enrich, adopt, per-tier progress edit) behind `atLeast("MANAGER")` — employees see only "My development" with their roadmap read-only (tiers + progress badges + skill-gap + HITL context); empty-state copy points them to their manager. (`useGoals.ts` param renamed `_cycle` — tsc unused-param cleanup from BUG1's prefix-invalidation.) · **[test]** new `CareerPage.test.tsx` (2): employee → no team tab + no target picker + read-only empty copy; manager → team tab + picker present. frontend **76** vitest, tsc/lint/build clean · **[live]** employee reza@acme.test GET /api/career/roadmap → 200 (own roadmap, no dead link) · commit `BUGFIX BUG3 — employees get read-only own career roadmap (no dead link)`

45 · BUGFIX/BUG2 · "Request AI Draft" unreachable for the demo manager · INVESTIGATED all three candidates: RBAC fine (RUN_AI_REVIEW_DRAFT = Manager+), feature fine (acme=FULL_AI → `agent1` unlocked, confirmed live for ada+priya), UI fine (reviews list shows a Draft StatusBadge + every row navigates to detail where the button renders for state===DRAFT). ROOT CAUSE = the SEED: the only state where Request-AI-Draft appears is DRAFT, but (a) the seeded DRAFT review (employees[1]) is managed by `lin`, not the primary demo manager `ada` (managers[0]) → not in ada's scope, and (b) `_ensure` is get-or-create that NEVER resets state, so once a tester clicks "Start editing" (DRAFT→EDITING) the review is permanently non-DRAFT on re-seed → the action becomes unreachable forever (live: ada saw 0 DRAFT reviews; tenant-wide HRBP saw 8 reviews, 0 DRAFT). FIX (`seed_demo._reviews`): seed a dedicated DRAFT review for one of ada's reports NOT used by the spectrum specs, and FORCE-reset it to DRAFT (clear human_reviewer/approved_at/route/final_body) on every seed so it's reliably reachable. · **[test]** new `apps/core/tests/test_seed_demo.py` (2): demo manager reaches a DRAFT review + `request_ai_draft` fires (→AI_DRAFTING); a re-seed RESETS a drifted (EDITING) review back to DRAFT. Existing `test_agent1_seam` already proves the FakeLLMProvider path locks PENDING_HUMAN_REVIEW (HITL) + the no-provider loud no-op. FULL backend **1196**/2 deselected (+2) · **[live]** re-seeded → ada sees 1 DRAFT review (Ella Nyberg, her report); `POST /api/reviews/<id>/request-ai-draft` → **202** (action reachable + fires); with no LLM key Agent-1 logs-and-skips (stays DRAFT — documented), PENDING landing is the configured-fake-provider path; re-seeded to leave the demo with a reachable DRAFT · commit `BUGFIX BUG2 — seed a reachable Request-AI-Draft review for the demo manager`

44 · BUGFIX/BUG1 · Goals Approve success-toast but row stays "Awaiting approval" · ROOT CAUSE (frontend, not backend): `useGoals.ts` cached the list under `["goals","list", cycle ?? "all"]` but `refresh()` invalidated `["goals","list", cycle]` — with no cycle selected (the default view) the cached key is `…"all"` while the invalidation key is `…undefined`, which React Query never matches → the list never refetched after approve (and after create/recordActual/recompute — same latent staleness, the "did anything happen?" symptom). Backend was already correct (GoalApproveView stamps approved_by+approved_at and returns the updated goal; `test_manager_can_approve_report_goal_and_audit` already proves persistence). FIX: invalidate by the stable PREFIX `["goals","list"]` + `["cycles","scores"]` (prefix-matches every cached variant). · **[test]** new `frontend/src/features/goals/useGoals.test.tsx` (2): the default no-cycle list AND a cycle-specific list are both marked invalidated after approve (fails pre-fix); frontend 74 vitest · **[live]** running stack: created a goal (approved_by None) → POST approve → 200 with approved_by+approved_at set → GET list refetch shows approved_by populated (the row the UI now flips to "Approved") → cleaned up · commit `BUGFIX BUG1 — goals approve now refetches (invalidation key)`

43 · WEB_COE/W3 · functional test matrix (web) — map the brief's testing row + fill gaps · Inventoried existing coverage (review state machine, KPI weight validators, escalation engine/sweep, notification signals) via a sub-agent, then added the GENUINELY-missing tests: `apps/reviews/tests/test_state_machine.py` (+2: route_rejected APPROVED→EDITING + illegal-unless-APPROVED), `apps/approvals/tests/test_escalation.py` (+1: PARALLEL step escalates independently of its active sibling), `apps/approvals/tests/test_signals.py` (+2: route-start → receiver invokes notify_approval_assignment; escalation → notify_approval_escalation — notification GENERATION end-to-end, not just signal-fired), `apps/feedback/tests/test_services.py` (+1: send_feedback_request → notify_feedback_request), `apps/goals/tests/test_api.py` (+2: PATCH KPI weight breaking 100 → 400 rolled back; non-weight PATCH → 200). KPI=100 boundaries (99.99/100.01/exactly-100) were ALREADY covered by test_weights.py + test_api.py boundary tests (confirmed, cited in the matrix). · **[test]** the 5 touched suites 80 pass; FULL backend **1193 passed**/2 deselected (+8, no regression) · **[live]** running stack: `POST /api/goals` KPI 99.99→400 / 100.01→400 / 100.00→201 (cleaned up); seeded a real overdue route + ran the actual `escalate_overdue_routes()` task → `{scanned:1,escalated:1,errors:0}`, step reassigned MANAGER→HRBP, route IN_PROGRESS; the integrations receiver fired the notifier path live (Slack no-op, graceful) · **[doc]** docs/FUNCTIONAL_TEST_MATRIX.md (every brief behaviour → test(s) → status, honest notes) · commit `WEB_COE W3 — functional test matrix (web)`

42 · WEB_COE/W2 · WCAG 2.1 AA pass + automated a11y guard · DECISION D26: axe-core in vitest/jsdom (not Playwright — fits the existing vitest+MSW stack) + a token-contrast test (jsdom has no layout → axe can't do contrast). NEW: `frontend/src/mocks/server.ts` (MSW node server, reuses the 90 handlers), `src/test/a11y/harness.tsx` (renderInShell/renderBare + axeViolations over wcag2a/2aa/21a/21aa), `src/test/a11y/a11y.test.tsx` (14 screens + ⌘K palette → 0 A/AA violations), `src/test/a11y/contrast.test.ts` (parses globals.css tokens, 14 text pairs ≥4.5:1). FIXES: audit/analytics/reviews `SelectTrigger`+input `aria-label`s; AppLayout skip-to-content link + `<main id tabindex=-1>`; Sidebar `<nav aria-label>`; Topbar icon-button `aria-label`s (Ask AI / Preview role / account menu); NineBoxGrid **keyboard alternative to drag** (per-chip "Move to box" DropdownMenu — WCAG 2.1.1) + override marker aria-label; `command.tsx` CommandDialog visually-hidden DialogTitle+Description (4.1.2); globals.css `:focus-visible` → visible 2px outline (2.4.7), `@media (prefers-reduced-motion)` (2.3.3), and darkened `--success/warning/danger/info/ai/premium` + `--muted-foreground` to clear 4.5:1 (1.4.3); test setup ResizeObserver/scrollIntoView shims. axe before→after: 7→0; contrast 7 failing→0. · **[test]** frontend 72 vitest (43 prior + 15 a11y + 14 contrast) · **[build]** tsc CLEAN, eslint CLEAN, production build clean · **[doc]** docs/ACCESSIBILITY.md (honest manual/AT caveats — no full-conformance claim from automation) · commit `WEB_COE W2 — WCAG 2.1 AA pass + a11y guard`

41 · WEB_COE/W1 · SSO — SAML 2.0 SP + OAuth/OIDC proven against a mock IdP · DECISION D25: `python3-saml` (OneLogin SP toolkit, not djangosaml2 — it validates the assertion + hands back attributes while SSO terminates in OUR `issue_tokens_for_user`; djangosaml2 would drive Django login + fight the JWT model). NEW MODEL `SamlIdpConfig` (TenantScoped, 1/tenant) — public IdP entity-id/SSO-url/signing-cert + email/role attr names + `role_map` + `sp_private_key_secret_ref` (env-var NAME, key never in DB/git); migration `0003_samlidpconfig*`. NEW `apps/identity/saml/`: `settings.py` (per-request OneLogin settings from the live host; `strict`+`wantAssertionsSigned` forced on; SHA-256; `allowSingleLabelDomains` for dev hosts; secret_ref resolution), `service.py` (process_response → signature/expiry/audience/destination validation; Redis SET-NX replay guard per assertion-id; tenant-scoped user binding NO-JIT; attribute→role mapping that **JIT-syncs the DB role** [RBAC enforces DB role, not the token claim] + writes `identity.saml.role_synced` audit), `views.py` (SP metadata / SP-initiated login-redirect / ACS → mint JWT). `tokens.py` `issue_tokens_for_user(user, *, role=None)` (backward-compat role override). URLs `saml/<slug>/{metadata,login,acs}`. Dockerfile += libxml2/libxmlsec1/xmlsec1 (probed to install on slim first); requirements += python3-saml==1.16.0. OIDC: existing adapter+complete already minted JWT; added 2 tests (session-hint tenant resolution + role-claim==DB-role). · **[test]** `test_saml.py` 12 (real xmlsec-signed round-trip: happy/tamper/unsigned/expiry/replay/cross-tenant-isolation/role-sync+audit/fallback/metadata/login-302/not-configured-404) + `test_oidc.py` 9; FULL backend **1185 passed**/2 deselected (+14, no regression) · **[live]** on running gunicorn: metadata 200; signed ACS round-trip 200 (mapped role=ADMIN, correct tenant); `/me` w/ SSO JWT 200; replay → 401 saml_replay; throwaway tenant cleaned up · **[doc]** docs/SSO.md (per-tenant setup, the 3 isolation locks, proof, 🔑 real-IdP needs) · commit `WEB_COE W1 — SSO SAML + OAuth proven`

40 · BUILD_8/8.2 · Expo scaffold + shell + secure storage · `create-expo-app mobile/` (Expo SDK 56, RN 0.85, React 19, Expo Router) + React Query + RHF + zod + NativeWind v4 (web indigo tokens) + expo-secure-store + @hookform/resolvers + babel-plugin-module-resolver. Built: `src/lib/secureTokenStore.ts` (SecureStore-backed TokenStore — sync in-memory cache hydrated from Keychain at boot, write-through), `src/lib/api.ts` (configureMobileApi → shared configureApiClient; base URL derived from Expo hostUri → the Mac's LAN IP:8080 so the phone reaches the backend; EXPO_PUBLIC_API_BASE_URL override; forced-logout handler), `src/lib/auth.tsx` (AuthProvider mirroring the web state machine on the secure store), `src/lib/query.ts`; routing `src/app/_layout.tsx` (providers + auth-gated Stack + global.css), `index.tsx` (auth redirect), `login.tsx` (RHF+zod, password + MFA-challenge, shared authApi + mapApiError, all states), `(tabs)/_layout.tsx` (bottom tabs + auth guard, emoji icons since @expo/vector-icons absent) + 5 tab screens (Dashboard welcome, Goals/Feedback/Career placeholders, More = identity + features + sign-out). Config: babel (nativewind + @shared→pmsshared), metro (watchFolders=repoRoot + nodeModulesPaths + symlink), tailwind tokens, global.css, declarations.d.ts, tsconfig @shared/axios paths; removed the template demo files. DECISION D23 (Metro shared-resolution via node_modules symlink + babel alias + postinstall; device base URL). · **[build]** `expo export -p ios` bundles clean; mobile tsc CLEAN · **[live]** ⏳ AWAITING Hari's device run · commit `BUILD_8 8.2`

40b · BUILD_8/8.2-fix · downgrade to Expo SDK 54 + robust Metro shared-resolver + secure-store web guard (Hari's Expo Go maxes at SDK 54; + 2 device blockers) · DOWNGRADE: `expo@54`, clean reinstall (rm node_modules+lock — the stale SDK-56 react-server-dom-webpack@19.2.7 was blocking `expo install --fix`), `expo install --fix` aligned all deps (react 19.1.0, react-native 0.81.5, expo-router 6.0.24, expo-secure-store 15.0.8), re-added babel-preset-expo (clean install dropped it). RESOLUTION (replaces the fragile symlink): `metro.config.js` `resolver.resolveRequest` maps `@shared[/sub]` → `<repo>/shared/src` and returns the source file directly (no symlink, no babel alias, no postinstall — all removed); watchFolders=repoRoot + nodeModulesPaths=mobile/node_modules (axios); tsconfig `@shared/*` path for TS. WEB GUARD: `secureTokenStore.ts` — expo-secure-store is native-only (crashed web with "getValueWithKeyAsync is not a function"); now `Platform.OS`-guarded (native→SecureStore, web→localStorage fallback). DECISION D24. · **[build]** expo-doctor 18/18 ✓, mobile tsc CLEAN, `expo export -p ios` bundles (1616 modules) ✓; web untouched/green · **[live]** ⏳ re-scan on iPhone (SDK 54) — Login should load · commit `BUILD_8 8.2-fix`

39 · BUILD_8/8.1 · extract the shared layer (web stays green) · DECISION D22: a `shared/src/` source dir consumed via a `@shared/*` path alias (NOT npm workspaces — protects the frontend's install), with re-export SHIMS at the old `@/lib/*` paths so all 122 web imports are untouched. MOVED (git mv, history preserved): `lib/{enums(incl. ROLE_RANK),types,errors}.ts` + `lib/api/{client,endpoints}.ts` → `shared/src/`. The AI hooks were intentionally KEPT in frontend (they pull react/react-query — deferred to BUILD_9 9.6 when mobile needs the poll pattern; keeps shared axios-only, zero duplicate-react risk). `shared/api/client.ts` refactored to inject the token store + base URL + forced-logout via `configureApiClient({baseURL,tokenStore,onForcedLogout})` (TokenStore interface; refresh-interceptor logic verbatim); web wires its localStorage store + import.meta.env via `lib/api/configure.ts` called in `main.tsx` + `test/setup.ts`. Tooling: frontend `vite.config.ts` (+`@shared` alias, +`axios` alias to the frontend copy since shared is out-of-root, +`server.fs.allow:['..']`), `tsconfig.json` (+`@shared/*` + `axios` paths, +`../shared/src` in include); `shared/{package.json (@pms/shared, axios peer),tsconfig.json,src/index.ts barrel}`. · **[build]** web tsc CLEAN, lint CLEAN, **43 vitest pass**, production build clean — proven NO web regression after the extraction · **[live]** rebuilt+redeployed the frontend container; SPA serves (200), bundle resolves (200), login returns a token (the injected-store client authenticates) · commit `BUILD_8 8.1`

38 · BUILD_8/9 · mobile series — (superseded — block lifted; see 39) — earlier-run BLOCKER when no Expo runtime · The mobile app (React Native + Expo) is accepted, per MOBILE_BUILD_PLAN.md §5 + the BUILD_8 spec, by RUNNING in the Expo simulator / Expo Go against the live backend ("the real bar is runs in Expo, not compiles"). This headless terminal has no iOS simulator / Android emulator / device / Expo Go / browser, and no Metro/Expo consumer to cross-platform-validate a shared extraction. DECISION D21: did NOT speculatively refactor the web's core api-client/auth infra for Phase 8.1 (web-verifiable in isolation, but its mobile correctness — Metro resolution, SecureStore token store, NativeWind — is unvalidatable here; risking the green verified web app for unconfirmable benefit is the wrong unattended trade; the extraction belongs in the session that also scaffolds+runs Expo, per Phase 0's own framing). Per BUILD_0's blocker rule: prior work left green/pushed; wrote BLOCKER_8_mobile_runtime.md (decision-complete, ready-to-execute plan: 8.1 shared extraction + injectable-client diff, 8.2 create-expo-app scaffold, 8.3 auth+MFA, 8.4 dashboard, BUILD_9 screens; demo creds; what's already mobile-ready) + BUILD_8_REPORT.md. No code changed → web + backend remain green (frontend 43 vitest, backend 1171). · **[doc]** blocker + reports · commit `BUILD_8 — mobile blocked on Expo runtime + handoff`

37 · BUILD_7/7.B.2 · nine-box drag-reposition UI · DECISION D20: native HTML5 drag-and-drop (NOT react-dnd — the spec assumed it but it's not installed; for a 3×3 grid drop, native DnD needs no new dependency). `lib/types.ts` (NineBoxPlacement += override_box/override_by/override_at/override_rationale/effective_box/is_overridden), `lib/api/endpoints.ts` (successionApi.setNineBoxOverride/clearNineBoxOverride), `features/succession/useSuccession.ts` (set/clear override mutations), `lib/nineBox.ts` (new generic `bucketByEffectiveBox` — buckets by override-or-computed cell) + `lib/nineBox.test.ts` (3), `components/NineBoxGrid.tsx` (reworked to a loose `NineBoxCell` contract + id-based callbacks so it serves BOTH the interactive succession grid AND the read-only analytics calibration grid; draggable chips + cell drop targets when `canOverride`; override marker ● + reset button; per-chip pending state), `features/succession/SuccessionPage.tsx` (NineBoxTab: canOverride=atLeast HRBP; wired reposition/clear + pendingId; non-HRBP read-only), `mocks/{data,handlers}.ts` (nineBox data + PUT/DELETE override mock, HRBP-gated). · **[test]** frontend tsc+lint clean, 43 vitest (+3 nineBox), build clean · **[live]** restarted web (load 7.B.1) + redeployed frontend; HRBP set box=1 → override_box=1, computed box=7 PRESERVED, effective_box=1, is_overridden=true; Manager→403; employee→404; clear→effective_box back to 7, is_overridden=false · commit `BUILD_7 7.B.2` + BUILD_7_REPORT.md

36 · BUILD_7/7.B.1 · nine-box override endpoint (backend-first) · `apps/succession/models.py` (NineBoxPlacement += override_box/override_by/override_at/override_rationale — the computed `box` is NEVER rewritten; override sits alongside, display-only), migration `0002_nineboxplacement_override_*` (apply+reverse clean), `apps/rbac/matrix.py` (+OVERRIDE_NINE_BOX capability = HRBP/Admin, tighter than Manager+ ASSESS) + `apps/rbac/tests/test_matrix.py` (EXPECTED table entry), `apps/succession/services.py` (set_nine_box_override [validates box 1–9] / clear_nine_box_override — audited), `apps/succession/serializers.py` (NineBoxSerializer += override_* + effective_box + is_overridden), `apps/succession/views.py` (NineBoxOverrideView PUT set / DELETE clear; OVERRIDE_NINE_BOX-gated; placement via tenant-scoped manager → cross-tenant 404), `apps/succession/urls.py` (/nine-box/<id>/override). DECISION D19 (display-only — does NOT alter deterministic readiness; HRBP/Admin-only; computed box preserved + reversible). Invariants: employee→404 (participant gate) untouched; Manager→403; cross-tenant→404. · **[test]** `test_ninebox_override.py` 6 pass (set+clear / computed-box-preserved / manager-403 / employee-404 / cross-tenant-404 / invalid-box-400 / audit rows); rbac 297; FULL backend 1171 passed/2 deselected (+10, no regression) · commit `BUILD_7 7.B.1`

35 · BUILD_7/7.A.2 · review comments UI · frontend `lib/types.ts` (+ReviewComment + ReviewCommentSection), `lib/api/endpoints.ts` (reviewsApi.comments/createComment/editComment/deleteComment), `features/reviews/useReviews.ts` (useReviewComments + useReviewCommentMutations), `lib/reviewComments.ts` (new pure `threadComments` — one-level grouping, orphan-safe) + `lib/reviewComments.test.ts` (3), new `features/reviews/CommentsPanel.tsx` (threaded list, section tag, new-comment form w/ section select, inline reply, author-only edit/delete, all states, kind-aware errors via notifyError), wired into `ReviewDetailPage.tsx` sidebar after Assessments; `mocks/handlers.ts` (+mutable comment store + GET/POST/PATCH/DELETE so dev exercises it). · **[test]** frontend tsc+lint clean, 40 vitest (+3), build clean · **[live]** restarted web (load 7.A.1) + redeployed frontend; e2e on the running stack: create(SUMMARY)→reply(201,one-level)→list(count 2, author_name "Ada Lovelace", parent set)→edit(edited_at set)→out-of-scope employee 403→author delete 204→only the reply remains · commit `BUILD_7 7.A.2`

34 · BUILD_7/7.A.1 · ReviewComment model + API (backend-first) · `apps/reviews/models.py` (new `ReviewComment(TenantScopedModel)`: review FK, author FK, self `parent` FK for one-level replies, nullable `section` choice [SUMMARY/STRENGTHS/DEVELOPMENT/GOALS/RECOMMENDATIONS; null=general], `body`, `edited_at`; `employee` property → review.employee for RBAC; ix on (tenant,review,created_at)), migration `0004_reviewcomment` (apply+reverse clean), `apps/reviews/services.py` (create_comment/edit_comment/delete_comment — audited via `record`; one-level threading enforced; delete = soft-delete), `apps/reviews/exceptions.py` (+CommentThreadingError 422), `apps/reviews/serializers.py` (ReviewCommentSerializer — body/section writable; author/parent/timestamps read-only; parent resolved scope-safely in the view), `apps/reviews/views.py` (ReviewCommentListCreateView + ReviewCommentDetailView — `VIEW_OWN_REVIEW` + `check_object_scope` so comments inherit the review's visibility EXACTLY; author-only edit/delete), `apps/reviews/urls.py` (/comments + /comments/<id>). DECISION D18 (one-level threading; reuse VIEW_OWN_REVIEW not a new capability; 422 for threading violation). Invariants: never broadens review visibility; cross-tenant→404; out-of-scope→403; author-only mutate. · **[test]** `apps/reviews/tests/test_comments.py` 11 pass (create/list, employee-own, edit/delete-soft, author-only-403, out-of-scope-403, cross-tenant-404, one-level-reply-422, foreign-parent-404, 401); FULL backend 1161 passed/2 deselected (+11, no regression) · commit `BUILD_7 7.A.1`

33 · BUILD_6/6.5 · stabilization sweep · ran `scripts/smoke.py` (47/47 — every surface × every role; RBAC boundaries hold: admin/audit DENIED for manager, succession 404 for employee, analytics-dept DENIED for employee; AI alive; no 500s) + an extended sweep of complex/detail endpoints. FOUND a bug class: a malformed UUID in a query param filtering a `UUIDField` → ORM raises Django `ValidationError` → 500 (default DRF handler doesn't catch it). 6 endpoints affected: `/api/ai/jobs?target=`, `/api/reviews?cycle=`, `/api/goals?cycle=`, `/api/audit/logs?actor=`, `/api/analytics/{calibration,department}?cycle=`, `/api/succession/nine-box?cycle=`. FIX: `apps/core/exception_handler.py` (new — maps DRF-UNHANDLED Django ValidationError → 400 `INVALID_INPUT`; genuine server bugs raise other types and still 500, so no masking; domain validators that convert upstream never reach it), wired via `config/settings/base.py` REST_FRAMEWORK.EXCEPTION_HANDLER; plus a targeted empty-list guard on `apps/ai/views.py` AIJobListView (a non-uuid target can't match an artifact → `[]`, better UX for the poll-reattach). Tests: `apps/core/tests/test_exception_handler.py` (4 endpoints → 400 + a well-formed-uuid-still-200 control), `apps/ai/tests/test_jobs_api.py` (+malformed-target→[]). DECISION D17. Frontend: 6.1 already swept the iteration-crash class; no nested-array iterations exist → no frontend change. · **[test]** handler 5 + ai-jobs 6; FULL backend 1150 passed/2 deselected (+6, no regression — the global handler changed no domain status) · **[live]** the 6 endpoints now 400 not 500; smoke 47/47 · commit `BUILD_6 6.5` + BUILD_6_REPORT.md

32 · BUILD_6/6.4 · org-chart expand-on-demand / lazy-load (Q1 item 3) · backend `apps/org/services.py` (build_org_tree gains `root`/`depth`; new `_bounded_subtree` — BFS from a visible root, or the actor's visible roots, down `depth` levels, all intersected with the visible set so scope/tenant isolation is identical; out-of-scope/cross-tenant root → 404 NotFound, mirrors person_card's no-leak rule; default path byte-identical), `apps/org/views.py` (OrgTreeView parses `?root`/`?depth`; bad depth ignored), `apps/org/tests/test_api.py` (+5: depth=1 top-levels-only-with-direct_report_ids-preserved; root=subtree-only; root-out-of-scope-404; root-cross-tenant-404; lazy-params-don't-widen-employee-scope) · frontend `lib/types.ts` (OrgNode += direct_report_ids — the has-children signal), `lib/org.ts` (+childrenOf/allChildrenLoaded pure helpers), `lib/org.test.ts` (+2), `lib/api/endpoints.ts` (orgApi.tree(params)), new `features/org/LazyOrgTreeView.tsx` (initial `?depth=1`, expand fetches `?root=<id>&depth=1`, per-node spinner, merge), `features/org/OrgPage.tsx` (TreeTab → LazyOrgTreeView for HRBP/Admin, existing whole-tree FullTree for Manager/Employee). ALSO fixed a 6.1-introduced MOCK regression: `mocks/data.ts orgTree()` still returned the normalized map shape → normalizeOrgTree would iterate a non-array and crash in dev/mock mode (live was fine, real backend = raw); now returns RawOrgTree (array nodes + direct_report_ids + {from,to}); `mocks/handlers.ts` honors `?root`/`?depth`. DECISION D16. · **[test]** org 50 pass (+5); FULL backend 1144 passed/2 deselected (no regression); frontend tsc+lint clean, 37 vitest (+2), build clean · **[live]** restarted web + recreated frontend; default tree 31 nodes (display + direct_report_ids present); `?depth=1`→5 nodes (roots+children, ≪ full); `?root=<root>&depth=1`→4 (root+3 children, roots=[root]); `?root=<bogus>`→404 · commit `BUILD_6 6.4`

31 · BUILD_6/6.3 · scoped single-employee score lookup (Q1 item 2) · backend `apps/cycles/views.py` (new `EmployeeCycleScoreView`: `GET /api/cycles/<cid>/scores/<employee_id>` — one CycleScore, scope-bound OWN-self/TEAM-subtree+self/TENANT-anyone; out-of-scope or cross-tenant → 404 (no existence leak); no-score-yet → 404; mirrors MyCycleScoreView + the cohort scope branch), `apps/cycles/urls.py` (route declared AFTER `scores/me` so the literal wins — "me" is not a uuid; before the cohort `scores`), `apps/cycles/tests/test_api.py` (+6: own-200, peer-denied-404-with-score-present, manager-subtree-200-vs-peer-404, hrbp-any-200, cross-tenant-404, no-score-404) · frontend `lib/api/endpoints.ts` (+`cyclesApi.score(cid,eid)`), `features/reviews/ReviewEvidence.tsx` (EvidencePanel fetched the WHOLE cohort just to `.find` one employee → now the scoped single lookup with `retry:false`; a 404 leaves the score block hidden, exactly as the old `.find`→undefined did). KEPT the cohort `cyclesApi.scores` for the genuine multi-row consumers: the GoalsPage per-employee grid + calibration (both Manager+ in nav, so no 403). · **[test]** cycles 22 pass (+6); FULL backend 1139 passed/2 deselected (no regression); frontend tsc+lint clean, 35 vitest, build clean · **[live]** restarted web + recreated frontend; `/scores/<emp>` in-scope→200 (employee matches, has t_score), bogus uuid→404, `scores/me` still resolves (literal wins over the uuid route) · commit `BUILD_6 6.3`

30 · BUILD_6/6.2 · admin users pagination + search (Q1 item 1) · backend `apps/administration/services.py` (list_users gains an optional `search` → server-side `Q(email|display_name|role icontains)`, still tenant-scoped + materialized in-context so the non-request test caller keeps working), `apps/administration/views.py` (UserListCreateView.get paginates via StandardResultsSetPagination + reads `?search=`), `apps/administration/tests/test_api.py` (updated the list test to the paginated shape; +test_users_list_is_paginated, +test_users_search_filters_server_side, +test_users_search_does_not_leak_other_tenants) · frontend `lib/api/endpoints.ts` (`adminApi.users(params)`→`Paginated<AdminUser>` + `AdminUserParams`), `features/admin/useAdmin.ts` (useUsers(params)), `lib/hooks/useDebouncedValue.ts` (new), `features/admin/UsersPage.tsx` (debounced search box + page controls + distinct no-users vs no-matches empty states; the manager column + manager dropdowns now read the tenant-wide `useDirectory` instead of the full user array — the two consumers that relied on the un-paginated list), `mocks/handlers.ts` (users mock → paginate + search). DECISION D15: paginate a materialized scoped list (sanctioned by pagination.py) rather than a lazy queryset, to preserve list_users' self-contained tenant-scoping that a non-request test relies on. · **[test]** admin 36 pass (+3); FULL backend 1133 passed/2 deselected (no regression); frontend tsc+lint clean, 35 vitest, build clean · **[live]** restarted web + recreated frontend; `/api/admin/users?page_size=2`→{count:31,next,2 rows}; `?search=ada@acme`→1; `?search=HRBP`(caps)→2 HRBP; `?search=zzzznope`→count 0 empty (no error) · commit `BUILD_6 6.2`

29 · BUILD_6/6.1 · org-chart crash (".for is not iterable") root-cause + not-iterable sweep · ROOT CAUSE: a type-lie — `OrgTree` type/`OrgTreeView` assumed `nodes: Record<id,node>` + `edges: [id,id][]`, but `GET /api/org/tree` returns `nodes` as a LIST and `edges` as `{from,to}` objects, so `for (const [parent,child] of tree.edges)` array-destructured objects → "not iterable" (and `tree.nodes[id]` on an array → undefined). The node also lacked the `display` field the client type requires. FIX: backend `apps/org/services.py` (_compute_full_tree adds `display`=display_name||email to each node; +`display_name` in the values()); frontend `lib/org.ts` (new pure `normalizeOrgTree`: list→id-map, {from,to}→[from,to] tuples, defensive on null/missing/id-less/null-endpoint) wired at the boundary in `features/org/useOrg.ts` AND `lib/hooks/useDirectory.ts` (the latter ALSO consumed the raw tree + indexed an array by uuid → silently always "Unknown"; now normalized + `nodes` annotated `Record<string,OrgNode>` so the `{}` default doesn't poison the type — that was the SuccessionPage `unknown` tsc errors), `OrgTreeView.tsx` render tolerant (`display||email`), `lib/types.ts` (+`RawOrgTree`). SWEEP: audited every `for...of`/destructure + `.data.map` + all 16 bare-array endpoints (live-probed → all real arrays); the OrgTree type-lie was the ONLY crash (errors.ts uses Object.entries=tuples; CONFIG_FIELDS[kind] TS-guaranteed; NineBoxGrid/CoverageHeatmap call-site-guarded; mocks dev-only). Tests: backend `apps/org/tests/test_services.py` (+test_tree_nodes_carry_display, +test_tree_wire_shape_list_nodes_and_from_to_edges — locks the wire contract); frontend `lib/org.test.ts` (5 normalizer tests incl. the crash-repro destructure + defensive nulls). · **[test]** org 45 pass; FULL backend 1130 passed/2 deselected (+2, no regression); frontend tsc+lint clean, 35 vitest (+5), build clean · **[live]** busted org cache (22 tenants) + restarted web + rebuilt frontend; per-role `/api/org/tree` normalized + walked the exact frontend tree-logic: ADMIN/HRBP 31 nodes (full), MANAGER 8, EMPLOYEE 4 — 0 missing display, WALK_OK all roles (no crash, scope correct); `?person=<id>`: in-scope→200, missing/garbage/non-uuid→404 (PersonSheet error state) · commit `BUILD_6 6.1`

28 · BUILD_5/5.5 · ⌘K palette → open the person you picked · `frontend/src/features/command/CommandPalette.tsx` (people results navigated to the generic `/org` — now deep-link `/org?person=<id>`), `frontend/src/features/org/OrgPage.tsx` (consume `?person=<id>` via `useSearchParams` → open that PersonSheet, then strip the param with `{replace:true}` so a refresh/close doesn't re-open) · the palette was otherwise already real-data (role-filtered nav, scoped people search, AI-assistant action); PersonSheet already degrades to loading/error, and search-scope == person-detail-scope so a deep-link is always viewable-or-graceful · **[test]** frontend 30 pass; tsc+lint+build clean (frontend-only, backend untouched) · commit `BUILD_5 5.5b`

27 · BUILD_5/5.5 · audit console: date-range filter + action-contains fix · backend `apps/audit/views.py` (action filter `=`→`__icontains` — the console's "Action contains" box + "e.g. approved" placeholder promised a substring search but did an exact match, so typing `approved` matched nothing; docstring updated), `apps/audit/tests/test_console.py` (+3: case-insensitive substring match; `date_to` past-bound → empty; [past,future] range brackets the rows — `date_to` had no test before) · frontend `features/audit/AuditPage.tsx` (From/To `type=date` inputs wired to the already-typed `date_from`/`date_to` params; min/max cross-bound the pickers; whole-local-day inclusive boundaries via `dayStartISO`/`dayEndISO` so "To = today" keeps today's rows; folded into hasFilters+clearFilters) · note: `AuditFilters`/`auditApi.logs` already forwarded the params + backend already range-filtered — only the UI inputs and the action semantics were missing. · **[test]** audit console 11→14 pass; FULL backend suite 1128 passed, 2 deselected (no regression); tsc+lint+build clean · commit `BUILD_5 5.5`

26 · BUILD_5/5.4b · succession coverage heatmap · `frontend/src/components/CoverageHeatmap.tsx` (new — proportional RED/AMBER/GREEN band + counts across critical roles) wired atop the SuccessionPage coverage tab. Note: the per-role coverage grid, NineBoxGrid (read), and plan-detail RoleSheet were ALREADY built; nine-box DRAG-reposition is deferred (needs a persisted-override backend endpoint — no dead UI). · **[build]** tsc+lint+build clean · commit `BUILD_5 5.4b`. Verified non-redundant scope: 5.3 has no draft-vs-final diff (finalize copies draft→final; identical) + comments need a backend (Tier 3); 5.4c suppression already visually explicit; 5.5 error-boundary/tenant-config-lock already built.

25 · BUILD_5/5.4a · career: adopt AI roadmap (accept→ACTIVE) · backend `apps/career/services.py` (adopt_roadmap: AI-DRAFT→ACTIVE, supersede prior ACTIVE to DRAFT, advisory preserved, audited, scoped), `apps/career/views.py` (RoadmapAdoptView) + `urls.py` (/adopt), `apps/career/tests/test_api.py` (adopt promotes+supersedes; non-AI-draft→422); frontend `endpoints.ts`+`useCareer.ts` (adopt mutation) + `CareerPage.tsx` ("Adopt as active" button on AI-draft card) · resolves the 5.4 flagged decision (DECISIONS D14) · **[test]** career 48 pass; no drift; tsc+lint+build clean · commit `BUILD_5 5.4a`

24 · BUILD_5/5.2 · goal wizard + live weight bar + attainment viz · `frontend/src/components/WeightBar.tsx` (new — live KPI-weight bar, green=100/amber-under/red-over), `AttainmentBar.tsx` (new — direction-aware actual-vs-target gauge, "not recorded" when null), `features/goals/GoalsPage.tsx` (NewGoalDialog → 2-step wizard: details → KPIs+WeightBar with stepper + Next/Back; KpiRow shows AttainmentBar) · weight-sum logic already covered by `lib/weights.test.ts` · **[build]** tsc+lint+build clean · commit `BUILD_5 5.2`

23 · BUILD_5/5.1 · command-center: actionable needs-you cards · `frontend/src/components/StatCard.tsx` (optional `to` → whole card navigates, hover affordance, a11y label), `features/dashboard/DashboardPage.tsx` (Manager+HRBP needs-you StatCards link straight to the action: approvals→/approvals, reviews→/reviews, coverage→/succession, summaries→/feedback) · note: dashboards were ALREADY insight-first (real-count StatCards + tiles + recharts SuccessionRiskTile); §8.3's gap was "link straight to the action" → done · **[build]** tsc+lint+build clean · commit `BUILD_5 5.1`

22 · BUILD_4/4.4 · hot-read caching: degrade-not-error + verify/document · `config/settings/base.py` (default cache IGNORE_EXCEPTIONS=True + DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS — cache outage → recompute, never 500), `apps/billing/tests/test_caching.py` (4), `docs/CACHING.md` (new — every cached read + TTL + invalidation triggers + rules) · audit: entitlement/rate-limits/feature-flags (300s), org tree (600s), analytics dept aggregate — all already tenant-keyed + invalidated; the gap was degradation posture · **[test]** cache-hit 0 queries; upgrade invalidates; tenant-isolated keys; dead-Redis degrades to DB (no error); 4 pass · DECISIONS D13 · commit `BUILD_4 4.4`

21 · BUILD_4/4.3 · optimistic locking + KPI weight critical section · `apps/core/concurrency.py` (new — StaleVersion 409 + check_version), `apps/goals/models.py`+`administration/models.py` (+version, migrations), serializers expose version read-only, `apps/goals/views.py` (GoalDetailView.patch check+bump; `_lock_goal` select_for_update in 3 KPI weight paths), `apps/administration/{views,services}.py` (TenantConfig check+bump), frontend (Goal/TenantConfig types +version; saveTenantConfig sends version; mock fix), `apps/core/tests/test_optimistic_locking.py` (3) · **[test]** Goal+TenantConfig stale→409 STALE_VERSION (no-version still works); KPI add issues SELECT…FOR UPDATE on the goal; 133 affected pass; frontend tsc+lint+build clean · DECISIONS D12 · commit `BUILD_4 4.3`

20 · BUILD_4/4.2 · metrics + readiness + observability · `apps/core/metrics.py` (new — Prometheus exporter: cross-worker request counters in cache + live AIJob/token/queue/tenant aggregates, no per-tenant labels), `apps/core/views.py` (MetricsView token-gated/fail-closed) + `urls.py` (/metrics), `apps/core/middleware.py` (MetricsMiddleware), `config/settings/base.py` (METRICS_TOKEN), `apps/core/health.py`+`apps.py` (ReplicaDatabaseHealthCheck → /readyz), `frontend/nginx.conf` (proxy /metrics), `docker-compose.yml` (METRICS_TOKEN dev default), `docs/OBSERVABILITY.md` (new — probes, metrics, SLIs+thresholds), tests `test_metrics.py`(4)+`test_readyz.py`(+2) · **[test]** 9 pass; token gate 404/401/200; readyz 503-degraded + DatabaseReplica present · **[live]** /readyz 7/7 up incl DatabaseReplica; /metrics real series (request counts by route/status, queue depth, aijob-by-status, token-usage-by-agent, tenants=22). Sentry already wires CeleryIntegration (async failures captured) · commit `BUILD_4 4.2`

19 · BUILD_4/4.1 · prod settings + baked image + controlled migrations · `config/settings/base.py` (+XFrameOptionsMiddleware → check --deploy clean), `docker-compose.prod.yml` (new — baked image INSTALL_DEV=false, no source mount, settings.prod, split cache/broker Redis, one-shot migrate service + web waits on it / never auto-migrates, `${VAR:?}` fail-closed secrets), `docs/RUNBOOK.md` (deploy order: migrate once → roll web), `apps/core/tests/test_prod_settings.py` (3 — fail-closed w/o SECRET_KEY + ALLOWED_HOSTS, loads secure with env) · **[build]** prod image builds (next); prod compose valid + fail-closed verified · **[test]** check --deploy clean under prod; 3 prod-settings tests pass · DECISIONS D10 · commit `BUILD_4 4.1`

18 · BUILD_3/3.3+3.4 · DATABASE_ROUTERS read/write split + connection sizing/resilience · `apps/core/dbrouter.py` (new — PrimaryReplicaRouter reads→replica/writes→default, read-after-write via per-thread flag + in_atomic_block, allow_migrate default-only; DBRoutingResetMiddleware), `config/settings/base.py` (DATABASES[replica] env-DSN-or-fallback + TEST MIRROR; DATABASE_ROUTERS; middleware; sizing comment), `config/celery.py` (task_prerun reset_write_state + task_postrun close_old_connections, EAGER-guarded so it never tears down a test transaction), `apps/core/tests/test_dbrouter.py` (4), `docs/RUNBOOK.md` (replica provisioning + max_connections sizing for both aliases) · **[test]** router: reads→replica then→default after write, txn reads→default, migrate default-only; both aliases load + inherit CONN settings; **caught + fixed**: eager `close_old_connections` was tearing down 15 AI-seam test transactions → guarded on `CELERY_TASK_ALWAYS_EAGER`; dropped a flaky `transaction=True` queryset test (mirrored-replica DB-flush mid-suite) for a unit assert; `config/settings/test.py` CONN_MAX_AGE=0 so the replica connection can't accumulate · DECISIONS D9 · commit `BUILD_3 3.3+3.4`

17 · BUILD_3/3.2 · atomic throttles + global ceiling + AIThrottle coverage · `apps/core/throttling.py` (_EntitlementThrottle.allow_request → atomic.incr_window fixed-window; +AI_THROTTLES bundle; +AtomicAnonThrottle), `apps/ai/groq.py` (_reserve_global → atomic.incr_window), `apps/ai/views.py`+5 seam views (throttle_classes=AI_THROTTLES on chat/nudges/review-draft/summarize/plan-enrich/jd-generate/career-enrich), `apps/identity/views.py` (login/MFA → AtomicAnonThrottle), `apps/core/tests/test_atomic_throttle.py` (6) · **[test]** 40 concurrent @5/min→exactly 5; global ceiling 3→exactly 3; anon per-IP limit; AI-route coverage; 453 affected pass · DECISIONS D8 · commit `BUILD_3 3.2`

16 · BUILD_3/3.1 · atomic per-tenant budget reserve (Lua) · `apps/billing/atomic.py` (new — reserve/release/incr_window Lua via get_redis_connection + cache.make_key), `apps/billing/services.py` (check_and_reserve_budget → atomic.reserve; +release_budget refund), `apps/ai/gateway.py` (refund on NOT_CONFIGURED/PROVIDER_ERROR post-reserve, keep on OK/SCHEMA_INVALID), `apps/billing/tests/test_atomic_budget.py` (5) · **[test]** 64 threads @ cap 10 → exactly 10 reserve (1..10, none reused); refund frees a slot; release≥0; gateway refunds on provider error; billing+ai 133 pass · DECISIONS D7 · commit `BUILD_3 3.1`

15 · BUILD_2/2.5 · chat decision + sync-path cleanup · `apps/ai/tests/test_async_sweep.py` (new — review seam: EAGER=False + spy on run_agent_job.delay → 202, review stays DRAFT, 0 metered, job QUEUED; feedback close: sync CLOSED but summary deferred), `apps/jd/views.py`+`apps/succession/views.py` (stale "SYNCHRONOUSLY" docstrings → async), `DECISIONS.md` D6 (chat stays sync — the deliberate exception, RBAC-bound/write-blocked/503-429-graceful) · **[test]** 2 sweep tests pass; no seam runs the gateway in-request · commit `BUILD_2 2.5`

14 · BUILD_2/2.4b · AI job result_id + frontend polling UX · backend: `apps/ai/models.py`+migration 0003 (result_id UUID), `apps/ai/tasks.py` (populate result_id from seam id on success), `apps/ai/serializers.py` (+result_id), `apps/ai/tests/test_run_agent_job.py` (assert result_id). frontend: `lib/types.ts` (AIJob + result_id), `lib/api/endpoints.ts` (aiJobsApi + 6 action methods → AIJob/{cycle,job}), `lib/hooks/useAIJob.ts`+`useAIAction.ts` (poll-to-terminal + fire/react), `components/AIJobBanner.tsx` (working/DEGRADED-calm/FAILED), wired all 5 UIs (ReviewDetailPage, CareerPage, RoleSheet[result_id nav], CycleSheet[close+resummarize], JdDetailPage[save-inputs→generate]) · **[test]** ai 67 pass; tsc+lint+build clean · **[live]** DRAFT review → fire → 202 QUEUED (async) → worker → SUCCEEDED → review PENDING_HUMAN_REVIEW (HITL intact), after `restart web celery-worker` · commit `BUILD_2 2.4b`

13 · BUILD_2/2.4a · AI job-status API (backend) · `apps/ai/views.py` (AIJobDetailView GET /api/ai/jobs/<id> own+tenant-scoped; AIJobListView GET /api/ai/jobs?target=<id>), `apps/ai/urls.py`, `apps/ai/tests/test_jobs_api.py` (5: own 200, cross-user 404, cross-tenant 404, ?target filter own-only, unauth 401) · **[test]** full suite 1090 passed, 2 deselected · commit `BUILD_2 2.4a`

12 · BUILD_2/2.3e · career enrich async · `apps/career/views.py` (RoadmapEnrichView: scope-load roadmap + resolve target → enqueue career_roadmap with target_ref in params → 202; dropped unused task import), `apps/career/tests/test_api.py` · **[test]** advisory-only invariant preserved (worker); 202+job DEGRADED, deterministic roadmap INTACT, no AI roadmap; career+ai 108 pass · commit `BUILD_2 2.3e`. ALL 5 seams now async.

11 · BUILD_2/2.3d · jd generate async · `apps/jd/views.py` (JDGenerateView: sync 404-scope + validate_generation_inputs 422, then enqueue jd_generator → 202; dropped unused task import), `apps/ai/tasks.py` (run_agent_job: defensive try/except around dispatch → uncaught seam exception lands FAILED, never stuck RUNNING), `apps/jd/tests/test_api.py` · **[test]** no-inputs→422 preserved (sync), no-provider→202+job DEGRADED, JD untouched; jd+ai 112 pass · commit `BUILD_2 2.3d`

10 · BUILD_2/2.3c · succession enrich async · `apps/succession/views.py` (PlanEnrichView: scope-load plan via get_plan_in_scope → enqueue agent4 → 202; dropped now-unused task import), `apps/succession/tests/test_api.py` (202+job DEGRADED; deterministic plan COMPLETELY INTACT, no AI plan created) · **[test]** name-free evidence + PENDING gate run in worker; succession 56 pass · commit `BUILD_2 2.3c`

9 · BUILD_2/2.3b · feedback summary async · `apps/feedback/services.py` (close_cycle: sync audited COLLECTING→CLOSED, then enqueue agent3 → returns (cycle, job)), `apps/feedback/views.py` (CycleCloseView → {cycle, job}; CycleSummarizeView keeps sync CLOSED-409 then enqueue → 202), `apps/feedback/tests/{test_api,test_services}.py` · **[test]** anonymised payload + breach guard + HRBP_HOLD + PENDING all still run in the worker; no-provider→DEGRADED(NOT_CONFIGURED) via DB poll; feedback 52 pass · note: frontend close consumer (`summary` key→`job`) rewired in 2.4 · commit `BUILD_2 2.3b`

8 · BUILD_2/2.3a · reviews AI draft async · `apps/ai/serializers.py` (new — AIJobSerializer poll shape), `apps/ai/services.py` (new — enqueue_agent_job: create QUEUED AIJob + run_agent_job.delay, tenant from actor), `apps/reviews/views.py` (ReviewRequestAIDraftView: scope-check then enqueue → 202 + job; was sync 503/409/200), `apps/reviews/tests/test_api.py` (202+job: DEGRADED w/o provider review-stays-DRAFT; WIRED→SUCCEEDED→review PENDING) · **[test]** reviews 67 + ai 62 pass · commit `BUILD_2 2.3a`

7 · BUILD_2/2.2 · run_agent_job Celery task · `apps/ai/tasks.py` (new — dispatcher: binds tenant, idempotent terminal-guard, RUNNING→dispatch by agent_code→classify result; SUCCEEDED/DEGRADED/FAILED + error_code + token_ledger link), `apps/ai/exceptions.py` (+AgentUnavailable carrying gateway_status), 5 agents (`raise AgentUnavailable(status)` not bare RuntimeError), 5 seam tasks (generic except maps BUDGET_EXCEEDED→budget_exceeded else provider_error), `apps/ai/models.py`+migration 0002 (params JSONField for career target_ref), `apps/ai/tests/test_run_agent_job.py` (6 tests) · **[test]** SUCCEEDED(artifact PENDING, metered once), provider_error→FAILED(artifact unpublished), NOT_CONFIGURED→DEGRADED(review stays DRAFT, 0 metered), over-budget→DEGRADED(0 metered), cross-tenant→no-op, idempotent 2nd run no double-meter; 332 affected-suite pass; no drift · commit `BUILD_2 2.2`

6 · BUILD_2/2.1 · AIJob model + async design · `apps/ai/models.py` (new — AIJob: status QUEUED→RUNNING→SUCCEEDED|DEGRADED|FAILED, loose target_type+target_id, requested_by, agent_code, confidence, token_ledger FK, error_code, 2 tenant-leading indexes), `apps/ai/migrations/0001_initial.py`, `apps/ai/tests/test_aijob_model.py` (5 scoping tests), `DECISIONS.md` D4 · **[test]** migration apply+reverse clean; no drift; 5 scoping tests + 56 ai-suite pass · commit `BUILD_2 2.1`

1 · BUILD_1/1.1 · query-count harness + N+1 baseline · `apps/testsupport/query_budget.py` (count_queries/ScalingResult/measure_scaling, additive seeding), `apps/core/tests/test_query_budgets.py` (7 endpoint budget tests, recording mode) · **[test]** 7 passed; baseline table above · commit `BUILD_1 1.1`

5 · BUILD_1/1.5 · regression guard + QUERY_BUDGETS.md · `docs/QUERY_BUDGETS.md` (the rule, the guard, per-endpoint before→after, how to add a list), `PROGRESS.md` (headline before/after table) · **[test]** budget guard runs in the normal suite (7 collected, not gated); sanity-check: removing reviews `select_related` → `test_reviews_list_bounded` FAILS (Δ=60), restored → 7 passed · commit `BUILD_1 1.5`

4 · BUILD_1/1.4 · pagination + large-tenant correctness · `apps/core/tests/test_large_tenant.py` (gated `large_tenant` marker; ~1.2k employees; reviews/goals page-bounded + ≤15 queries in HRBP & Manager scope; org tree scope-bounded), `pytest.ini` (register marker, deselect by default), `apps/administration/{services,views,urls}.py` (+`user_stats` DB GROUP-BY aggregate + `GET /api/admin/users/stats`), `apps/administration/tests/test_api.py` (stats counts/deactivation/403/single-GROUP-BY), frontend `lib/types.ts`+`lib/api/endpoints.ts` (`AdminUserStats`/`userStats`), `features/dashboard/{cockpit,DashboardPage}.tsx` (tiles read the aggregate, no full-user-list download) · **[test]** large-tenant 2/2 pass (5s); admin suite 33 pass; frontend tsc+lint+build clean · **[live]** stats `{total:31,active:31,roles sum 31}` 70ms, org tree 31 nodes 68ms, reviews `{count,next,previous,results}` 39ms · audit: all entity LISTs already paginate + client reads `Paginated<T>` correctly (the reskin fixed the array-mishandling); bare sub-lists are per-parent bounded · commit `BUILD_1 1.4`

3 · BUILD_1/1.3 · ORM optimization + targeted indexes · `apps/reviews/models.py` (+ix_review_tenant_recent `(tenant,-created_at)`), `apps/goals/models.py` (+ix_goal_emp_recent `(tenant,employee,-created_at)`), 2 migrations (`reviews/0003`, `goals/0002`), `apps/org/services.py` (person_card select_related manager) · **[test]** migrations apply+reverse clean, DDL verified (`created_at DESC`); 239 affected-suite tests pass; full suite (see next) · aggregation audit: analytics/calibration left in Python (no-win, documented D2) · commit `BUILD_1 1.3`

2 · BUILD_1/1.2 · eliminate the name/title N+1 at the queryset level · `apps/reviews/views.py` (list + calibration: select_related employee/reviewer/human_reviewer/cycle), `apps/goals/views.py` (select_related employee/created_by/approved_by + prefetch kpis), `apps/org/views.py` (select_related filled_by/reports_to/published_jd), `apps/feedback/views.py` (select_related subject only — givers never serialized), `apps/jd/services.py` (search_jds → select_related created_by), `apps/career/services.py` (list_roadmaps → select_related employee/target_jd/target_position), `apps/core/tests/test_query_budgets.py` (ENFORCE_BOUNDED=True) · **[test]** budget Δ→0 on all 7 (reviews 78→3, goals 103→4, positions 53→3, feedback/jd/career 28→3); 6 affected app suites 354 passed; giver-anonymity unchanged (cycle serializer carries no giver field; existing `test_api.py:116/130/135` still green) · commit `BUILD_1 1.2`
