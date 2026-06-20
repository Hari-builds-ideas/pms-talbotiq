# PROGRESS.md — production-hardening build series (BUILD_1…5)

> Append-only log. Verification honesty: **[test]** asserted by a test ·
> **[live]** exercised over real HTTP · **[build]** build/typecheck/lint only.

## Current: BUILD_5 — WEB_UX_COMPLETION · concrete UX work COMPLETE (ux-spec as design authority; design skills unavailable)

BUILDs 1–4 COMPLETE/pushed/green. BUILD_5 delivered: 5.1, 5.2, 5.4a, 5.4b, 5.5
(+5.5b), 5.6, 5.7. The concrete, functionally-verifiable UX that needs neither
new backend scope nor the design skills is now done. Remaining = (A) subjective
VISUAL pass — analytics recharts depth/login+shell polish — needs design skills +
Hari's eye; (B) two Tier-3 features needing new backend (review comments,
nine-box drag-reposition) — a product go/no-go for Hari. See SERIES_COMPLETE_REPORT.md.

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
