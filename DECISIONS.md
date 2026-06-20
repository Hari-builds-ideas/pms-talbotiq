# DECISIONS.md — non-trivial choices in the build series

> Each entry: the decision · options considered · why · safe-default rationale ·
> the QUESTIONS.md item it resolves (if any).

---

### D1 (BUILD_1/1.2) — Where the N+1 fix lives, and the "bounded" threshold

**Decision.** Add `select_related`/`prefetch_related` at the point that owns the
queryset for each list path: in the **view** when the view builds it inline
(reviews, goals, org, feedback), in the **service** when a service function
returns it (jd `search_jds`, career `list_roadmaps`). The budget guard
(`ScalingResult.is_bounded`) treats an endpoint as bounded when extra rows add
`≤ max(2, extra_rows//4)` queries — i.e. a small constant, not one-per-row.

**Options considered.** (a) one central `.select_related` mixin on pagination —
rejected: the FK set differs per serializer and a blanket join risks pulling
unused tables; (b) `prefetch_related` everywhere — rejected: a forward FK is
cheaper as a JOIN (`select_related`); prefetch is reserved for the one reverse
relation (goals→kpis). (c) per-row caching — rejected: doesn't fix the query.

**Why safe.** Output bytes are identical (only query count changes); no scope,
tenant, or RBAC predicate is touched; the feedback fix select_relates only
`subject` (givers are never on that serializer), so anonymity is unaffected.
Verified by the 6 app suites (354) + the budget module.

### D2 (BUILD_1/1.3) — Two targeted indexes; aggregation left in Python (no-win)

**Indexes ADDED (each serves a real, identified hot query — not speculative):**
- `ix_review_tenant_recent` = `(tenant, -created_at)` on Review. Serves the
  default paginated list for the broad scopes (Manager/HRBP/Admin):
  `WHERE tenant=? ORDER BY -created_at LIMIT page` — eliminates a filesort over
  the full tenant set. Employee-scope filtering is already covered by the
  `(tenant, employee, cycle)` unique-constraint index.
- `ix_goal_emp_recent` = `(tenant, employee, -created_at)` on Goal. Serves the
  hottest Goal read — an employee's own goals / a manager's team goals
  (`WHERE tenant=? AND employee[_id in …] ORDER BY -created_at`). The only
  pre-existing index was `(tenant, cycle, employee)` (cycle-leading), which
  cannot serve an employee filter; this is the only employee-leading index.

Both migrations apply AND reverse cleanly; DDL verified (`… created_at DESC`).

**Considered and REJECTED (honesty — not every audit item yields a change):**
- `.only()`/`.defer()` on list serializers: reviews intentionally serialize
  `draft_body`/`final_body`; JD bodies live on `JDVersion`, not the list row;
  remaining text columns are small. No measurable win, real risk of breaking a
  serializer field. Left alone.
- Push analytics aggregation into the DB (`Avg`, `GROUP BY`): rejected as a
  net-negative. `department_analytics` and `calibration_grid` already
  materialise their result set exactly once (the individual rows are part of the
  output), and MySQL 8 has no clean median aggregate — a DB rollup would add a
  second query, not remove one. The Python aggregation runs over already-fetched
  rows, so it is the optimal shape.
- `person_card`: added `select_related("manager")` (saves one round-trip on a
  hot detail endpoint; covered by existing org tests).

### D3 (BUILD_1/1.4) — Pagination audit; dashboard counts moved server-side

**Audit result.** Every employee-/entity-scaling LIST already paginates
(`StandardResultsSetPagination`) AND the React client already consumes each as
`Paginated<T>` (reviews, goals, org positions, feedback cycles, jd library/
requests, career roadmaps, succession roles/bench/nine-box). The contract's
"some lists treated as arrays" worry was already resolved in the reskin — so the
"one frontend touch" was NOT a pagination-shape fix. The bare-array responses
that remain are per-parent bounded sub-lists (a goal's KPIs, a review's
timeline/assessments, a cycle's requests, a jd's versions, a roadmap's progress,
template/integration libraries) — not employee-scaling, so they stay bare.

**The real large-tenant smell + fix.** Two screens fetched a whole collection
just to derive a few numbers: the admin dashboard tiles pulled the FULL user
list to compute active-count + role distribution (O(users) download to show ~5
numbers). Fixed with a DB-aggregated `GET /api/admin/users/stats` (one GROUP BY)
and rewired the two tiles to it — this IS the one frontend touch. Same class of
fix as the directory: don't ship N rows to the client to count them.

**Considered and chosen NOT to change in BUILD_1 (logged as Q1):**
- `GET /api/admin/users` (the admin user TABLE) stays unpaginated: its remaining
  consumer is the admin table itself, and paginating it needs page controls +
  server-side search to stay usable — a UI change that belongs in BUILD_5, not
  an ORM build. Its dashboard-aggregate consumer is already removed (above).
- `GET /api/cycles/<id>/scores` (team scores) stays unpaginated: consumers
  (`ReviewEvidence`, `useGoals`) fetch the cohort to pick ONE employee's score;
  the clean fix is a scoped single-score lookup, deferred. `/scores/me` already
  exists for the self case.
- Org CHART lazy-loading (expand-on-demand): the tree endpoint is already
  scope-bounded (an Employee gets only their line — now asserted by the
  large-tenant test), so non-admins are safe today. A full org CHART inherently
  needs its structure, so expand-on-demand is a viz/UX feature for BUILD_5, not
  an ORM concern. The directory's per-row name needs are already met by the
  `*_name` payload fields added in 1.2, making the tree a fallback resolver.

### D4 (BUILD_2/2.1) — The async AI job model + surfacing pattern

**Context.** All 5 AI seams are ALREADY `@shared_task` Celery tasks
(`draft_review_with_agent1`, `summarize_feedback`, `enrich_succession_with_agent4`,
`generate_jd`, `generate_roadmap`) that bind tenant context, set the artifact
PENDING via the audited state machine, meter through the gateway, and degrade
gracefully. The ONLY problem: the views call them SYNCHRONOUSLY (inline), so a
slow Groq call holds a gunicorn worker. BUILD_2 flips sync→`.delay()` and adds a
status record + poll surface — it does NOT rewrite the tasks.

**Decision — `AIJob` (tenant-scoped, in the new `apps/ai/models.py`):**
- Status: QUEUED → RUNNING → SUCCEEDED → FAILED | DEGRADED.
- **Target reference = loose `target_type` (CharField) + `target_id` (UUID), NOT
  a GenericForeignKey.** The AIJob is a correlation/status record; the artifact
  (Review / FeedbackSummary / SuccessionPlan / JobDescription / DevelopmentRoadmap)
  remains the tenant-scoped source of truth in its own table. A loose reference
  keeps AIJob decoupled, avoids the ContentType machinery, and sidesteps
  GenericFK's cross-tenant footguns. The PK (UUID) IS the correlation id.
- Fields: `requested_by` (FK User), `agent_code`, `target_type`+`target_id`,
  `status`, `started_at`, `finished_at`, `confidence` (nullable), `token_ledger`
  (nullable FK billing.TokenLedger — the usage ref, populated best-effort in 2.2),
  `error_code` (the structured GatewayResult status on DEGRADED/FAILED).
- INSERT + own/scope-bound reads only; cross-tenant → 404 (TenantScopedManager).

**Surfacing pattern.** The endpoint that used to run the work synchronously now:
(1) creates the PENDING placeholder if it makes one up front, (2) creates an
AIJob (QUEUED), (3) enqueues `run_agent_job.delay(job_id)`, (4) returns
`202 Accepted` with the job id (+ artifact id). The client POLLS
`GET /api/ai/jobs/<id>`. No websockets — the app polls everywhere else.

**Invariant (unchanged by async).** The result lands EXACTLY where the sync
result did: the artifact locked PENDING_HUMAN_REVIEW, metered in TokenLedger,
schema-validated, confidence/floor applied, anonymised (feedback) / name-free
(succession). Only WHEN/WHERE it runs changes, never WHAT it produces.

### D5 (BUILD_2/2.4) — `result_id` for create-new seams + frontend poll pattern

**Problem.** Two seams MUTATE the input artifact in place (review draft, JD
generate, feedback summary → `result_id == target_id`); two CREATE a new artifact
(succession enrich → a new source=AI plan; career enrich → a new AI roadmap), so
the job's `target_id` (the input) can't tell the client what was produced — the
new plan/roadmap would be unreachable in the UI.

**Decision.** Add `AIJob.result_id` (nullable UUID), populated on SUCCEEDED from
the seam's returned id (`review_id`/`summary_id`/`plan_id`/`jd_id`/`roadmap_id`).
The poll surface now reports both the input (`target_id`) and the produced
artifact (`result_id`). Succession's panel switches to `result_id` on SUCCEEDED;
career's list refreshes (the new roadmap appears). Mutate-in-place seams just
re-fetch `target_id`.

**Frontend pattern.** One shared `useAIJob` (polls every 1.5s until terminal) +
`useAIAction` (fire → poll → react) + `<AIJobBanner>` (working / DEGRADED-calm /
FAILED-recoverable; null on SUCCEEDED — the artifact refetch shows the result).
All five seam UIs use it; AI stays assistive (manual path always available).

**Note (dev stack).** Celery worker + gunicorn don't autoreload, so the running
dev stack needs `docker compose restart web celery-worker` to pick up new task
code — a deploy concern, not a code issue. Verified live after restart: a DRAFT
review fired → 202 QUEUED → worker → SUCCEEDED → review PENDING_HUMAN_REVIEW.

### D6 (BUILD_2/2.5) — AI chat stays SYNCHRONOUS

**Decision.** AI chat (`POST /api/ai/chat`) remains synchronous, the one
deliberate exception to the async move. It's short, interactive and 8B/low
latency, and an async "your answer is being prepared… poll" UX is strictly worse
for a conversation. It keeps the gateway's own graceful degradation
(NOT_CONFIGURED → 503, over-budget → 429) and stays read-only, RBAC-bound
(`USE_CHAT` + chat entitlement) and write-blocked. The heavy, retrying agent
seams (review/feedback/succession/JD/career) are exactly the ones that justified
moving off the request thread; chat does not.

**Cleanup.** No endpoint still runs the gateway in-request except chat — proven
by `test_async_sweep.py` (with `CELERY_TASK_ALWAYS_EAGER=False` the seam returns
202 with the artifact untouched + nothing metered). The stale "called
SYNCHRONOUSLY" docstrings on the JD and succession views were updated. The
deterministic paths (`regenerate_roadmap`, the baseline plan/roadmap) are
untouched and remain the always-available manual fallback.

### D7 (BUILD_3/3.1) — Atomic budget reserve (Lua) + refund-on-failure

**Decision.** The per-tenant budget reserve is now a Redis Lua step
(`apps/billing/atomic.py::reserve`) doing GET + compare + INCR + PEXPIRE in one
atomic server-side call. The old check-then-incr (two round trips) let two
replicas both read `current < limit` and both increment, overshooting at the cap
edge; the Lua step makes "exactly M succeed at cap M" hold under any concurrency
(proven by a 64-thread test). Keys are unchanged (tenant-namespaced, period-
stamped, via `cache.make_key` so they match django-redis's stored keys);
behaviour at the API surface is identical (over budget → BudgetExceeded → 429,
the gateway never raises). TokenLedger stays the source of truth for ACTUAL usage;
the Redis counter is the fast pre-check.

**Refund-on-failure (the contract's default).** A reserved call that does NOT
consume real usage is refunded via `release_budget` (atomic DECR, never below 0):
the gateway refunds on the two post-reserve provider-failure paths
(`NOT_CONFIGURED` raised at call time, `PROVIDER_ERROR`) — both BEFORE
`record_usage`. A SUCCESSFUL metered call KEEPS its reservation; `SCHEMA_INVALID`
also keeps it (the provider responded and was metered before the schema check —
real tokens were spent). So a failed call never permanently burns budget, and a
successful one is never double-counted.

### D8 (BUILD_3/3.2) — Atomic throttles + global ceiling; AIThrottle coverage

**Atomic mechanism.** The entitlement throttles (`TenantThrottle`/`UserThrottle`/
`AIThrottle`) and the global LLM ceiling (`groq._reserve_global`) now use the Lua
fixed-window counter (`atomic.incr_window` — INCR + PEXPIRE-on-first in one step)
instead of DRF's read-modify-write of a timestamp list / `cache.add`+`incr`. So
concurrent requests across replicas can't overshoot the window (proven: 40
concurrent attempts at a 5/min cap → exactly 5 pass; 16 concurrent at a global
ceiling of 3 → exactly 3). The per-request rate still resolves from
`rate_limits_for(tenant)`, so an entitlement upgrade still lifts limits
everywhere. Fixed window was already the documented choice; Retry-After is the
window length.

**AIThrottle coverage.** `AIThrottle` is per-view (not a default). Attached to
every AI-TRIGGERING route via the `AI_THROTTLES = [Tenant, User, AI]` bundle:
chat, review request-ai-draft, feedback re-summarize, succession plan enrich, JD
generate, career enrich (+ nudges, an /api/ai/ read). **Deliberately NOT on the
job poll/list (`GET /api/ai/jobs[...]`)** — the UI polls those every 1.5s and the
AI bucket would trip on normal polling; they keep the default tenant/user
throttles. `feedback close` is a lifecycle transition (once per cycle) and keeps
the defaults too. The login/auth surface now uses `AtomicAnonThrottle` (DRF's
`AnonRateThrottle` hardened to the same Lua counter) so a credential-stuffing
burst can't be edged across replicas either. A coverage test enumerates the AI
views and asserts the bucket is present.

### D9 (BUILD_3/3.3) — DATABASE_ROUTERS read/write split (replica-ready)

**Decision.** A `PrimaryReplicaRouter` (`apps/core/dbrouter.py`) routes reads →
`replica`, writes → `default`; `allow_migrate` only on `default`;
`allow_relation` always true (the replica is a copy). It is ACTIVE + tested now
against the single DB: the `replica` alias falls back to a second connection to
the primary when `DB_REPLICA_HOST` is unset, so provisioning a real replica later
is purely env config (RUNBOOK), never a code change. In tests the replica
`TEST: {"MIRROR": "default"}` so no second test DB is built.

**Read-after-write correctness.** A replica lags, so stale reads after a write
must be avoided. Two rules: (1) a per-thread "has written" flag set on the first
write and cleared at the start of each request (`DBRoutingResetMiddleware`) and
each Celery task (`task_prerun`); (2) any read while
`connections["default"].in_atomic_block` (every transaction, incl.
`select_for_update`) goes to the primary. The audit log (INSERT-only) and all
writes route to `default` via `db_for_write`. No `ATOMIC_REQUESTS`, so ordinary
GET reads genuinely reach the replica; write paths and transactional reads stay
on the primary. Proven by unit tests of the router (reads→replica, →default
after a write, →default inside a transaction, migrate default-only) + a queryset
asserting it resolves to the routed alias.

**Testing notes (learned the hard way).** (1) The Celery `task_postrun`
`close_old_connections` is SKIPPED in eager mode — otherwise it tears down the
test's own transaction (it caught 15 AI-seam tests). (2) A `transaction=True`
queryset test (TransactionTestCase + a mirrored replica alias) was dropped — it
flushes the DB mid-suite and was flaky under full-suite load; the router's
`db_for_read` decision is the routing authority and is unit-proven, so the
integration variant added risk without real coverage. (3) Test settings set
`CONN_MAX_AGE=0` so the second (replica) connection can't accumulate across a
long suite. Full suite green at 1100+ with the router active.

### D10 (BUILD_4/4.1) — Production posture: baked image + controlled migrations

**Decision.** `config/settings/prod.py` was already fail-closed (DEBUG off, HSTS,
secure cookies, no-default SECRET_KEY/ALLOWED_HOSTS, SECURE_PROXY_SSL_HEADER for a
TLS-terminating proxy). Added the missing `XFrameOptionsMiddleware` so the
`X_FRAME_OPTIONS=DENY` setting actually emits its header (`check --deploy`'s
`security.W002`) — `manage.py check --deploy` is now clean under prod settings
(the only residual, `W009` weak SECRET_KEY, clears with a real long/random key).

`docker-compose.prod.yml` (standalone, not an override — an override can't unset
the dev `.:/app` mount): runs `config.settings.prod`, a BAKED image
(`INSTALL_DEV=false`, no source mount), a SEPARATE cache Redis (allkeys-lru) from
the broker Redis (noeviction), required secrets via `${VAR:?...}` so compose
refuses to start without them (verified fail-closed).

**Controlled migrations.** Dev web auto-migrates on boot (an N-replica race in
prod). In prod a one-shot `migrate` service runs migrations ONCE; web/workers
wait on `service_completed_successfully` and never migrate themselves. Deploy
order (migrate → roll web) is in the RUNBOOK. Secrets stay env/vault-sourced (the
`secret_ref` seam), never committed.

### D11 (BUILD_4/4.2) — Custom /metrics exporter (no new dependency)

**Decision.** A small custom Prometheus-text exporter (`apps/core/metrics.py`)
rather than `django-prometheus` — adding a dep means an image rebuild + gunicorn
multiprocess wiring, and the contract allows a custom exporter. REQUEST counters
are incremented per request into the Redis CACHE (cross-worker — a per-process
counter undercounts behind N gunicorn workers), bucketed by a coarse route class
+ status class (no ids → tiny cardinality). The AI/usage/tenant figures are live
GAUGES queried at scrape time. Cross-tenant TOTALS use an explicitly unscoped
queryset (read-only, aggregate-only, NO per-tenant labels → no leak); the
endpoint is token-gated (`METRICS_TOKEN`) and **fail-closed** (unset → 404).
Request-latency histograms + live DB-conn gauges are left to a future
`prometheus_client` multiprocess setup (documented in OBSERVABILITY.md) — the
exporter stays dependency-free. `/readyz` gained a `DatabaseReplica` check; Sentry
already wired `CeleryIntegration`, so async AI-task failures are captured.

### D12 (BUILD_4/4.3) — Optimistic locking scope + the KPI weight critical section

**Versioned entities (justified subset, NOT everywhere):** `Goal` and
`TenantConfig` — the two clearest plain-field PATCH/PUT last-writer-wins cases
(a manager/HRBP editing a goal; two admins editing tenant settings). Each carries
a server-controlled `version`; a stale version on update → 409 STALE_VERSION
(`apps/core/concurrency.py`). `version` is read-only on the serializer (client
reads + echoes it; the server bumps via `serializer.save(version=+1)`); omitting
it is allowed (back-compat / non-form callers).

**Deliberately NOT versioned (justified):** review content is edited by a single
reviewer during EDITING and the state machine already 409s on a stale state; JD
body goes through the lifecycle's own legality/HITL gates on a single working
version; succession plan edits are low-frequency HRBP actions. These can adopt
the same `version` later if contention shows up.

**KPI weight-sum critical section.** The = 100.00 invariant is read-modify-write
across a goal's KPIs — two concurrent adds/edits could each read a valid sum and
both commit, corrupting the total. The three weight paths (KPI create / weight
PATCH / delete) now take a `SELECT ... FOR UPDATE` row lock on the goal
(`_lock_goal`, on the primary DB) inside their existing `transaction.atomic()`, so
the second writer waits and re-validates against the first's committed change.

**Frontend.** The 409 "conflict" message already reads "reload and try again";
the tenant-config form now SENDS the version it read (so the lock engages) and
keeps the user's unsaved JSON on a conflict. Goals are create/approve-only in the
UI (no edit form), so the Goal lock protects API/mobile clients (API-tested).
