# PROGRESS.md — production-hardening build series (BUILD_1…5)

> Append-only log. Verification honesty: **[test]** asserted by a test ·
> **[live]** exercised over real HTTP · **[build]** build/typecheck/lint only.

## Current: BUILD_4 — PROD_OPS_CONCURRENCY_CACHE · Phase 4.1 (prod settings + baked image + controlled migrations)

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
