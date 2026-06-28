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

### D13 (BUILD_4/4.4) — Hot-read caching: degrade-not-error; cache where it exists

**Audit.** The genuinely hot reads were ALREADY cached with tenant-embedded keys,
TTLs, and write-time invalidation: entitlement / rate-limit map / feature flags
(300s, busted on any entitlement write), the org tree (600s, busted on org
writes), the department analytics aggregate (300s, busted on a score recompute).
So 4.4 did NOT speculatively add caches (the contract: only cache where staleness
is acceptable and invalidation is clear) — the per-request lists are already O(1)
via BUILD_1's select_related/indexes and would need per-filter invalidation.

**The real gap: degradation posture.** `IGNORE_EXCEPTIONS` was unset, so a Redis
outage would 500 the cached reads instead of recomputing. Set
`IGNORE_EXCEPTIONS=True` (+ `DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS=True`) on the
application cache: a cache miss/outage now degrades to a live DB query, logged,
never an error. Sessions deliberately keep the default posture. Verified by a
dead-Redis test (recompute, no 500) plus cache-hit (0 queries) / invalidation /
tenant-isolation tests. Each cached read + TTL + invalidation trigger is in
`docs/CACHING.md`.

### D14 (BUILD_5/5.4) — Career: adopt an AI roadmap (accept→ACTIVE), not advisory-only

**Decision.** Resolve the flagged career gap by ADDING an accept→ACTIVE endpoint
(`POST /api/career/roadmaps/<id>/adopt`, MANAGE_CAREER_ROADMAP) rather than
leaving the AI-enriched roadmap as a dead-end advisory alternative. A human
adopts the AI-enriched **DRAFT** roadmap → it becomes the single **ACTIVE**
roadmap for its (employee, target); the previously-ACTIVE one is demoted to DRAFT
(superseded), preserving the "one ACTIVE per (employee, target)" invariant.

**Why adopt over advisory-only.** The AI enrich already produces a real,
grounded, tiered roadmap; with no adoption path it could only ever be looked at,
never acted on — a HITL dead-end. Adoption is the human acceptance step that
completes the loop, and it stays **advisory=True** (a coaching aid, never an
auto-promotion — the DB CHECK still holds). Only a `source=AI` `DRAFT` is
adoptable (else 422 NOT_ADOPTABLE); audited; scoped (out-of-scope → 404 via
`get_roadmap_in_scope`). Frontend: an "Adopt as active" button on the AI-draft
card (manager scope). Tested: adopt promotes the AI draft + supersedes the
deterministic; a non-AI-draft → 422.

---

### D15 (BUILD_6/6.2) — Paginate a materialized scoped list, not a lazy queryset

**Decision.** `GET /api/admin/users` now paginates (`StandardResultsSetPagination`)
with an optional server-side `?search=` (email / display_name / role, icontains).
The service `list_users(actor, search=None)` keeps its self-contained shape — it
opens its own `tenant_context`, applies the search filter in the DB, and returns a
**materialized list**; the view wraps that list with the paginator.

**Options considered.** (a) Return a LAZY queryset and let the paginator slice it
(DB-side LIMIT/OFFSET) — rejected: `list_users` is also called outside a request
(`test_list_users_is_tenant_scoped` calls it with no ambient tenant context and
iterates the result), so a lazy queryset evaluated after the service's
`tenant_context` exits would fail-closed to empty. (b) Move the context into the
view — rejected: spreads tenant-scoping responsibility out of the service (the
SOLE-scoping contract) into the view. (c) the chosen materialized-list + paginate,
which `apps/core/pagination.py` explicitly supports ("works on a QuerySet OR a
plain Python list").

**Why safe.** Scoping is unchanged (same `User.objects` manager, same
`tenant_context`); search is a pure additive `Q(...icontains)` filter; the response
is now a page (≤50 rows) so a large tenant never ships its whole user list (the Q1
item). The materialized fetch is one query of lightweight rows; the dashboard
counts already use the `/users/stats` aggregate (D from 1.4), so this path is only
the table itself. Frontend consumers that relied on the full array (the manager
column + the manager dropdowns) now read the tenant-wide `useDirectory` instead.
Resolves QUESTIONS Q1 item 1.

---

### D16 (BUILD_6/6.4) — Org-chart lazy-load: additive `?root`/`?depth`, scope-identical

**Decision.** The org tree endpoint gains optional `?root=<id>` (subtree under a
visible node) and `?depth=<n>` (only n levels below the root[s]) params for
expand-on-demand. The default (neither param) is byte-for-byte the full scoped
tree — unchanged. The frontend uses lazy mode ONLY for broad-scope roles
(HRBP/Admin) via `LazyOrgTreeView`; Manager/Employee keep the whole-tree
`OrgTreeView` (their line is small). Each node carries its full
`direct_report_ids`, which doubles as the "has children to expand" signal even
before the children are fetched.

**Options considered.** (a) Change the DEFAULT `/api/org/tree` to return only top
levels — REJECTED: `useDirectory` (app-wide name resolution) and the full-tree
render depend on the complete node set; truncating the default would break name
resolution everywhere. (b) `?parent=<id>` returning exactly one level — fine, but
`?root` + `?depth` is a strict superset (depth=1 == one level) and also supports
fetching a whole branch in one call. (c) Pure client-side virtualization with no
backend change — REJECTED: doesn't reduce the payload for a 2k-node tenant.

**Why safe.** `_bounded_subtree` BFS stays intersected with the SAME `_visible_ids`
set as the full tree, so scope/tenant isolation is identical — an Employee with
`?depth=` or `?root=` still only ever sees their own line; a cross-tenant/out-of-
scope `root` is a 404 (NotFound), never a 403 leak (mirrors `person_card`). Tests
assert all of this. The lazy frontend is gated to HRBP/Admin (no dead UI for
others). Resolves QUESTIONS Q1 item 3.

**Also fixed here (regression introduced in 6.1):** the MSW mock `orgTree()` still
returned the normalized map shape, so `normalizeOrgTree` (added in 6.1) would
iterate a non-array and crash the org chart in dev/mock mode (the live stack was
unaffected — the real backend already returns the raw array). The mock now returns
the RAW wire shape, and the handler honors `?root`/`?depth`.

---

### D17 (BUILD_6/6.5) — Malformed input → 400 via a custom DRF exception handler

**Decision.** Add `apps/core/exception_handler.py` and set it as the DRF
`EXCEPTION_HANDLER`. It defers to the default handler; only when DRF returns
nothing AND the exception is a Django (`django.core.exceptions`) `ValidationError`
does it return a 400 (`INVALID_INPUT`). Plus a targeted empty-list guard on the
AI-jobs poll for a non-uuid `target`.

**Why.** The 6.5 sweep found that a malformed UUID in a query param filtering a
`UUIDField` (e.g. `?cycle=notauuid`, `?actor=notauuid`) makes the ORM raise Django
`ValidationError` during queryset evaluation — which the default DRF handler
doesn't recognise, so it surfaced as a 500 on six endpoints (reviews, goals, audit,
analytics calibration + department, succession nine-box, ai jobs).

**Options considered.** (a) Validate the UUID per-view before filtering (~6+ edits,
each deciding empty-vs-400) — rejected: repetitive, easy to miss a future endpoint.
(b) The chosen single handler — fixes the whole class (and future cases) in one
place. (c) Broadly catch all exceptions → 400 — rejected: would mask genuine
server bugs.

**Why safe (no masking).** A Django `ValidationError` is BY DEFINITION an
input/validation failure → a client error (400); genuine server bugs raise other
exception types (AttributeError, KeyError, …) and still surface as 500. Domain
validators (cycles end_date, goals weight, feedback) already convert to a DRF error
upstream in serializers/services, so they never reach this fallback. The full suite
(1149→1150, all green incl. existing status-code assertions) confirms no domain
status changed. The AI-jobs poll keeps an empty-list guard (semantically better
than 400 for "find the job for this artifact").

---

### D18 (BUILD_7 Feature A) — Review comments: one-level threading, reuse VIEW_OWN_REVIEW

**Threading depth.** ONE level — a comment may have replies, but a reply may not
be replied to (a reply with a non-null parent is rejected 422
`COMMENT_THREADING_ERROR`). Options: (a) flat (no replies) — too limiting for a
back-and-forth; (b) one level — the chosen default (simple, shippable, covers the
review-discussion need); (c) arbitrary depth trees — rejected as over-built for an
internal review tool and a recursive-render/perf risk. A reply's parent must also
belong to the SAME review (the scoped same-review lookup 404s a foreign parent).

**Capability.** Reuse `VIEW_OWN_REVIEW` (everyone, scope-narrowed) for both
listing and creating a comment — NOT a new capability. Rationale: commenting is
intrinsic to being able to view+collaborate on a review you can ALREADY see; a
separate capability would imply a separate privilege and risk drifting from the
review's visibility. The view enforces `check_object_scope` (the SAME gate as the
review detail), so comments inherit the review's visibility EXACTLY — out-of-scope
→ 403, cross-tenant → 404, never broadening it. Edit/delete add an author-only
check (another user's comment → 403). Delete is the standard soft-delete.

**Status codes.** A one-level violation is a business-rule error → 422 (matching
the reviews app's 422 convention: HITLApprovalRequired, RejectionReasonRequired),
not a 400. A foreign/cross-tenant parent or review id → 404 (the scoped manager
hides it). This resolves the BUILD_7 Feature A go-ahead.

---

### D19 (BUILD_7 Feature B) — Nine-box override: display-only, HRBP/Admin-only, computed box preserved

**Override feeds readiness, or display-only?** DISPLAY-ONLY. The persisted human
override repositions a person's cell on the 9-box grid (a calibration judgement),
but does NOT alter the deterministic readiness/bench math, which stays grounded in
the computed performance/potential. Options: (a) feed readiness — rejected: it
would let a subjective drag silently change succession outcomes, eroding the
deterministic, auditable basis; (b) display-only (chosen) — safest + most
transparent; the grid shows the human cell, the math stays principled.

**Storage.** Override fields live ON `NineBoxPlacement` (`override_box`,
`override_by`, `override_at`, `override_rationale`) ALONGSIDE the computed `box`,
which is NEVER rewritten. The serializer exposes both plus `effective_box`
(override ?? computed) and `is_overridden`. Clearing (DELETE) nulls the override →
back to computed. Fully transparent + reversible. (A separate override table was
considered but rejected — one row per (emp,cycle) already exists and an extra
table adds join/consistency overhead for no gain.)

**Capability.** New `OVERRIDE_NINE_BOX` = HRBP/Admin only — tighter than the
Manager+ `ASSESS_NINE_BOX`. Rationale: overriding the COMPUTED placement is a
stronger, calibration-owner action than assigning potential, so it's restricted to
the succession owners (HRBP/Admin). A Manager (has VIEW/ASSESS) → 403; an employee
→ 404 at the succession participant gate (the employee-invisible invariant is
untouched). Cross-tenant placement → 404. This resolves the BUILD_7 Feature B
go-ahead.

---

### D20 (BUILD_7 7.B.2) — Native HTML5 drag-and-drop, not react-dnd

**Decision.** The nine-box drag-reposition UI uses the browser's native HTML5
drag-and-drop (`draggable` chips + `onDragOver`/`onDrop` cells), NOT a library.

**Why.** The BUILD_7 spec said "the design already has react-dnd available", but
react-dnd (and dnd-kit) are NOT in `package.json`. For a simple 3×3 grid drop,
native HTML5 DnD is fully sufficient and adds ZERO new dependency / bundle weight —
preferable to pulling in a drag library mid-series. The `NineBoxGrid` was also
reworked to a loose `NineBoxCell` contract with id-based callbacks so the SAME
component serves both the interactive succession grid (HRBP/Admin, full placements)
and the read-only analytics calibration grid (a reduced shape) without breaking
the latter. Repositioning is gated to HRBP/Admin (canOverride); for everyone else
the grid stays read-only (no dead UI) — and employees never reach succession at all.

---

### D21 (BUILD_8) — Mobile series blocked on the Expo runtime; no speculative web-infra refactor

**Decision.** Do NOT execute Phase 8.1's `shared/` extraction (or scaffold the
Expo app) in this headless run. Write a decision-complete BLOCKER + handoff
instead, leaving the green web app untouched.

**Why.** The mobile series' defining acceptance — per `MOBILE_BUILD_PLAN.md` §5 and
the BUILD_8 spec — is *"runs in the Expo simulator / on a device via Expo Go
against the live backend"* ("the real bar is runs in Expo, not compiles"). This
environment is a headless terminal: no iOS simulator, no Android emulator, no
device/Expo Go, no browser (so no `expo start --web` either), and no Metro/Expo
consumer to cross-platform-validate a shared-package extraction.

**Options considered.** (a) Do the web-verifiable slice of 8.1 anyway (refactor the
API client + auth into `shared/`, web stays green) — REJECTED for an unattended
run: it refactors the app's MOST critical infrastructure with no mobile consumer to
confirm the cross-platform seam (Metro resolution, SecureStore token store), i.e.
real regression risk to the green/verified web app for a benefit that can't be
validated here. (b) Write the React Native screens blind — REJECTED: no compile
against RN/Expo types, no run → "written, not verified", which the contract ranks
below "verified over written". (c) The chosen path: a decision-complete
`BLOCKER_8_mobile_runtime.md` (shared-extraction design incl. the injectable-client
diff, `create-expo-app` steps, screen list, demo creds, what's already mobile-ready)
so an Expo-capable session executes the whole foundation fast — and the extraction
lands in the SAME session that scaffolds + runs Expo, so both sides validate
together (exactly as Phase 0 frames it).

**Why safe.** No code changed → the web app + backend stay exactly as verified at
the end of BUILD_7 (frontend 43 vitest, backend 1171). The platform-agnostic layer
+ every endpoint mobile needs are already in place and verified (`MOBILE_READINESS.md`
+ the 47/47 smoke). This is the blocker rule applied honestly, not abandoned work.

---

### D22 (BUILD_8 8.1) — Monorepo layout: `shared/` source via path-alias, re-export shims for web

**Decision.** Create `shared/src/` holding the platform-agnostic modules, consumed
by BOTH apps via a `@shared/*` path alias (web: vite + tsconfig; mobile: metro
`watchFolders` + tsconfig) — NOT an npm workspace. The web's existing `@/lib/...`
imports are preserved by turning the old files into one-line re-export SHIMS
(`export * from "@shared/..."`), so no web feature code changes.

**Options considered.** (a) npm workspaces (`@pms/shared` package) — REJECTED for
this step: it re-hoists/reinstalls the frontend's node_modules and adds Metro
workspace config, risking the green, verified web app (the hard constraint). (b)
Re-point all 122 web imports from `@/lib/*` to `@pms/shared` — REJECTED: a large,
risky find-replace across the app. (c) the chosen path-alias + shims — the frontend
install is untouched; only an alias + 5 shim files change on the web side; the
shared code is plain TS source each bundler compiles (Vite/esbuild for web, Metro
for mobile), resolving `react`/`axios`/`react-query` from each consumer's
node_modules (single instance per app).

**Token store + base URL injection.** `shared/api/client.ts` exposes
`configureApiClient({ baseURL, tokenStore, onForcedLogout })` + a `TokenStore`
interface; the refresh-interceptor logic is shared verbatim. Web wires its
localStorage/memory store (`lib/auth/tokenStore`) + `import.meta.env` base URL at
bootstrap (`main.tsx`); mobile wires an `expo-secure-store` store + the Expo env
base URL. This is the one behaviour-bearing change — gated by the web staying green
(tsc + lint + build + 43 vitest + a live login) before 8.1 is committed.

Modules moved: `enums.ts` (incl. `ROLE_RANK`), `types.ts`, `errors.ts`,
`api/client.ts`, `api/endpoints.ts`, and the async-AI hooks `useAIJob`/`useAIAction`.
UI (shadcn/Tailwind) does NOT move — mobile uses NativeWind/RN.

---

### D23 (BUILD_8 8.2) — Mobile Expo scaffold + how it consumes the shared layer

**Stack.** `create-expo-app` (Expo SDK 56, RN 0.85, React 19, Expo Router) +
React Query + React Hook Form + zod + NativeWind v4 (on the SAME indigo tokens as
web) + expo-secure-store. Bottom-tab shell (Dashboard/Goals/Feedback/Career/More)
+ an auth bootstrap that mirrors the web state machine, only swapping storage
(SecureStore) and the forced-logout wiring (a callback, not a window event).

**Consuming `shared/` from Metro (the hard part).** Metro would not resolve the
out-of-root `shared/src` via `extraNodeModules` (an absolute or relative target),
nor a babel-rewritten relative path — Expo/Metro resolves shared code through
`node_modules`, not arbitrary watch-folder source. The working approach:
- a `node_modules/pmsshared` SYMLINK → `../shared/src` (an in-`node_modules` entry
  Metro resolves cleanly; its realpath is covered by `watchFolders=[repoRoot]`),
- `babel-plugin-module-resolver` rewrites the source token `@shared` →
  `pmsshared` (so mobile imports read `@shared/...` exactly like web),
- `metro.config.js`: `watchFolders=[repoRoot]` + `nodeModulesPaths=[mobile/node_modules]`
  so `shared/`'s only bare dep (`axios`) resolves from mobile's modules,
- a `postinstall` (`npm run link-shared`) recreates the symlink after any install
  (npm prunes it otherwise — that was the multi-attempt red herring).
A scoped `@shared` symlink name was rejected (Metro parses `@scope/pkg` specially);
`pmsshared` is unscoped. Web is unchanged (it resolves `@shared` via the Vite alias).

**Device base URL.** Expo Go runs on the phone, so `localhost` ≠ the Mac: the API
base URL is derived from Expo's `hostUri` (the Metro LAN IP) → `http://<ip>:8080/api`,
overridable via `EXPO_PUBLIC_API_BASE_URL`.

**Verified [build]:** `expo export -p ios` bundles cleanly (1767 modules); mobile
`tsc` clean. **Live device run is Hari's** (the acceptance bar) — handed off at the
8.2 stop.

---

### D24 (BUILD_8 8.2-fix) — Downgrade to Expo SDK 54; Metro resolver for shared (no symlink)

**SDK 54, not 56.** Hari's iPhone Expo Go maxes at SDK 54, so the app was pinned
down: `expo@54` + a clean reinstall (`rm node_modules package-lock.json`) — needed
because the stale SDK-56 `react-server-dom-webpack@19.2.7` (peer react@^19.2.7)
blocked `expo install --fix` against SDK 54's react@19.1.0 — then `expo install
--fix` aligned everything (react 19.1.0, react-native 0.81.5, expo-router 6.0.24,
expo-secure-store 15.0.8) and `babel-preset-expo@54` was re-added (the clean
install had dropped it). `expo-doctor` 18/18.

**Shared resolution via a Metro resolver (replaces the symlink).** The earlier
node_modules symlink + babel alias + postinstall was fragile (npm prunes the
symlink; gitignored). Replaced with a single `metro.config.js`
`resolver.resolveRequest` that maps `@shared[/sub]` → `<repo>/shared/src[/sub]` and
returns the resolved source file directly (`{type:"sourceFile", filePath}`) — which
sidesteps Metro's refusal to resolve an out-of-root path passed as a module
specifier. `watchFolders=[repoRoot]` lets Metro serve `shared/`; `nodeModulesPaths`
pins `shared/`'s only bare dep (axios) to `mobile/node_modules`; tsconfig `@shared/*`
covers TS. Symlink, babel-plugin-module-resolver usage, postinstall, and the
`unstable_enableSymlinks` override all removed (the last was the only expo-doctor
failure). Mobile imports read `@shared/...` exactly like web.

**expo-secure-store web guard.** It's native-only and threw on web
("getValueWithKeyAsync is not a function"). `secureTokenStore.ts` now branches on
`Platform.OS`: native → SecureStore (Keychain), web → localStorage fallback (access
stays in memory either way). Hari tests on iOS (native path).

Verified [build]: expo-doctor 18/18, mobile tsc clean, `expo export -p ios` bundles
(1616 modules). Web app untouched. Device run pending Hari's re-scan.

---

### D25 (WEB_COE W1) — SAML SP via python3-saml (toolkit), not djangosaml2

**Library: `python3-saml` (OneLogin), pinned 1.16.0.** The brief allows either
python3-saml or djangosaml2. Chosen python3-saml because it is an SP *toolkit* —
it parses and cryptographically validates a SAML Response and hands back the
attributes, and nothing more. That fits our model exactly: SSO must authenticate
and then issue **our** tenant-scoped JWT through the existing `issue_tokens_for_user`
path, with tenant resolution + user binding done by our code (mirroring the OIDC
adapter). djangosaml2 (pysaml2) is an opinionated Django *auth framework* that wants
to drive `django.contrib.auth` login and its own user/session handling — it would
fight our JWT model and our no-JIT tenant-binding rule. Native deps (`libxmlsec1`,
`libxml2`, `xmlsec1`) added to the Dockerfile; probed to install + import cleanly on
`python:3.11-slim` before committing to the choice.

**Per-tenant, config-driven, no committed secrets.** New `SamlIdpConfig`
(TenantScopedModel, one per tenant) stores the tenant's IdP entity-id, SSO URL, and
**public** signing cert (a public cert is not a secret), plus the attribute names
and the role-map. Any SP-side *secret* (the SP private key, used only if a tenant's
IdP requires signed AuthnRequests / encrypted assertions) is referenced by
`sp_private_key_secret_ref` — the **name of an env var**, resolved at runtime —
never the key bytes in the DB or git. Endpoints are tenant-scoped by URL
(`/api/auth/saml/<tenant_slug>/{metadata,login,acs}`); the config is read inside
`tenant_context(tenant)`, exactly like the OIDC adapter, so the unauthenticated ACS
never escapes its tenant.

**Tenant isolation (the hard guarantee).** Three independent locks: (1) the ACS URL
is per-tenant, (2) the assertion signature is verified against *that tenant's*
configured IdP cert, so tenant A's IdP cannot produce an assertion that validates at
tenant B's ACS, and (3) the user is bound only within `tenant_context(tenant)` — no
JIT provisioning; an unknown identity is denied (mirrors OIDC). Tested:
tenant-A-signed assertion replayed at tenant B's ACS → rejected.

**Attribute → role mapping, fail-safe.** The configured role attribute is mapped
through the tenant-owned `role_map` to one of our Roles and stamped on the JWT (the
IdP is the tenant's federation trust root, so a tenant-administered role-map is
authoritative for the session — downstream server-side RBAC is unchanged). If the
attribute is absent or unmapped, we fall back to the **provisioned DB role** (never
escalate on missing data). `wantAssertionsSigned` + `strict` are forced on, so
unsigned/expired/wrong-audience assertions are rejected; a Redis-backed
consumed-assertion-id guard rejects replays within the validity window.

**JWT/MFA unchanged.** SAML and OIDC both terminate in `issue_tokens_for_user`; the
tenant_id+role claims, refresh model, and RBAC layer downstream are untouched.

**🔑 Not ours to deliver:** a *real* production IdP (Okta/Azure AD/etc.) is the
customer's — proven here against a self-signed mock IdP (real xmlsec-signed
round-trip in tests + a documented dev config). docs/SSO.md has the per-tenant setup.

---

### D26 (WEB_COE W2) — WCAG 2.1 AA: axe-in-jsdom + a token-contrast check, not Playwright

**Why axe-core in vitest/jsdom (not Playwright+axe).** The brief allows either. The
existing test stack is vitest+jsdom+RTL+MSW with no browser; standing up Playwright +
chromium in the headless build env is fragile, whereas axe-core runs directly over a
jsdom container. So the durable CI guard renders each key screen in the REAL shell with
MSW data and asserts zero `wcag2a/2aa/21a/21aa` axe violations (14 screens + the ⌘K
palette opened). Honest tradeoff: **jsdom has no layout engine**, so axe can't compute
color-contrast / focus-visible / reflow — those are handled out-of-band (below) and the
remaining manual/AT items are documented, not faked (docs/ACCESSIBILITY.md). We do NOT
claim certified full conformance from automated testing alone.

**Contrast handled by a token-contrast test, and tones were darkened to pass.** Since
axe can't do contrast in jsdom, `contrast.test.ts` parses the real tokens from
globals.css and asserts each text pair ≥ 4.5:1. The computation surfaced REAL failures:
the Badge `text-<tone>` on `bg-<tone>-subtle` pattern failed for success/warning/danger/
info/ai/premium (2.1–3.7:1) and `muted-foreground` was 4.34:1. Fix: darkened the base
tone tokens + `--muted-foreground` (keeping hue) so they clear AA — white-on-solid
`bg-<tone>` usages only gained contrast. (No `.dark` token block exists in the web
globals.css, so the web hub is light-only → only light tokens needed fixing.)

**Focus indicator made global.** `:focus-visible { outline: none }` was stripping the
indicator from any element not adding its own ring (AA 2.4.7 risk). Changed the base rule
to a visible `2px` outline; shadcn controls keep their ring because their utility-layer
`focus-visible:outline-none` overrides the base rule.

**Nine-box drag got a keyboard alternative (2.1.1).** The HTML5 drag is pointer-only; a
per-chip "Move to box" dropdown menu provides full keyboard operability without removing
drag. Drag isn't a WCAG-conformant sole mechanism, so the menu is the conformant path.

**Test-env shims.** jsdom lacks `ResizeObserver`/`scrollIntoView` (Radix/cmdk use them);
stubbed in the global test setup so overlay widgets render in the suite. No runtime effect.

---

### D27 (WEB_COE W1 follow-up) — SAML role sync is capped at the provisioned role (Hari's call on QUESTIONS Q2)

Hari resolved QUESTIONS Q2: keep IdP role-sync **opt-in** (empty `role_map` = no sync —
unchanged) AND add a **rank cap so a synced role can never EXCEED the admin-provisioned
role** — no IdP-driven privilege escalation. Implemented in
`apps/identity/saml/service.py::_resolve_and_sync_role`: a local `_ROLE_RANK`
(EMPLOYEE<MANAGER<HRBP<ADMIN); if the mapped role outranks the user's current DB role it
is refused and clamped to the current role (a warning is logged, nothing is written).
A mapped role at or below the current role still applies (de-escalation) and audits via
`identity.saml.role_synced`. Consequence (documented): because a de-escalation persists,
the current DB role is the ceiling for any later mapping — only an admin re-provisioning
raises a role. Tests: `test_saml_role_mapping_cannot_escalate_above_provisioned` +
`…_can_deescalate_and_audits` (replaced the prior "elevates" test). This refines D25 —
the role-mapping mechanism is unchanged; only the escalation direction is now blocked.

---

### D28 (BUGFIX BUG 3) — Employees get a READ-ONLY view of their OWN career roadmap

The employee dashboard advertises a "My career roadmap" tile (`to="/career"`), but
`/career` was wrapped in `RoleGate min="MANAGER"`, so an employee clicking it got "You
do not have access" — a dead link. Two coherent fixes were offered (hide the tile, or
show employees their own roadmap). **Chosen: show employees their own roadmap, read-only**
— the dashboard advertises it and the back-end already authorizes it (`VIEW_CAREER_ROADMAP`
is granted to `_EVERYONE`, OWN scope), so hiding it would contradict the system's own
access model and leave the advertised tile pointless.

Implementation (frontend only — the server already scopes correctly): removed the
`RoleGate` on the `career/*` route; lowered the sidebar "Career" entry to `minRole:
EMPLOYEE`; and in `CareerPage`, gated the "My team" tab and ALL manage controls
(choose/change target, refresh, AI-enrich, adopt, per-tier progress edit) behind
`atLeast("MANAGER")`. An employee sees only "My development" with their own roadmap
rendered read-only (tiers + progress badges + skill-gap + advisory/HITL context); the
empty state tells them their manager sets up the roadmap.

Note: the back-end's `MANAGE_CAREER_ROADMAP` is `_EVERYONE` (an employee *could* self-gen
their own roadmap), so this read-only presentation is intentionally MORE conservative than
the server allows — managers drive roadmaps, employees view. RBAC/scope are unchanged and
still enforced server-side; this is purely which controls the employee UI surfaces.

---

### D29 (BUGFIX BUG 4) — Chat intent is a 4-way taxonomy, not binary read/write

The chat assistant classified intent as only `write` vs `read`, and EVERY non-write
query fell through to the grounded goals+score answer — so "I feel lonely", "what day is
today?", and "what can you do?" all returned the same performance-metrics dump. Root
cause = the binary classifier, not the data layer.

Fix: expand the intent to **`write` | `performance` | `capability` | `general`** and route
each (`apps/ai/agents/chat.py`):
- `write` → the existing read-only refusal (**unchanged — must not regress**).
- `performance` → the existing grounded, RBAC-scoped goals + cycle-score answer (the
  `read` value is kept as a legacy alias so a real LLM returning `read` still grounds).
- `capability` → a plain-language description of what the assistant does.
- `general` → a polite decline + redirect to its purpose, **never** a metrics dump.

A read-only *performance* assistant is deliberately domain-bound: general/out-of-domain
questions get a courteous "that's outside what I can help with — here's what I can"
rather than a fabricated general-chatbot answer (and never a metrics summary). The LLM
classifies via the updated `_CHAT` system prompt; the `FakeLLMProvider` classifier
(`_fake`, used by tests + the no-key path) mirrors it deterministically (write → capability
→ performance → general, write first for safety). The frontend mock chat handler mirrors
the same routing. RBAC-scoping + the write-block are untouched — every performance fetch
still goes through `actor_can_access`.

---

### D30 (AI provider) — Switch active LLM provider Groq → OpenAI (Groq kept by config)

The gateway is provider-agnostic, so this is **config + a small provider class, not a
rewrite**. New `apps/ai/openai_provider.py::OpenAIProvider` mirrors `groq.py`: same
gateway contract (budget → PII-scrub → call → schema-validate → meter → confidence →
PENDING) and the same OpenAI-compatible **Chat Completions, JSON mode** request/response
shape, so nothing downstream changes. Differences vs Groq: base URL
`https://api.openai.com/v1` (`OPENAI_BASE_URL`), key `OPENAI_API_KEY` (Bearer), the model
map, and a JSON-mode guard (OpenAI's `json_object` 400s unless "json" is in the messages;
our prompts already say it — the guard covers a custom-prompt override). Used Chat
Completions (not the newer Responses API) for parity with the existing gateway.

**Models chosen** (`LLM_MODEL_MAP` defaults, each env-overridable): **`gpt-4o`** for the
human-read agents (review/feedback/succession/JD/career) — strong, JSON mode, broadly
available; **`gpt-4o-mini`** for chat + default — fast/cheap. Alternatives if preferred:
`gpt-4.1` / `gpt-4.1-mini` (same request shape). The o-series (reasoning) would need a
provider tweak (`max_completion_tokens`, no `temperature`) — deliberately not used.

**Groq kept available**: `LLM_PROVIDER` (compose default now the OpenAI provider) can be
pointed back at `apps.ai.groq.GroqProvider` with `GROQ_API_KEY` + the Groq model names —
documented in docs/AI_GOLIVE.md. `groq.py` is untouched.

**Paid-pricing guard**: OpenAI bills per token (Groq was free-tier), so `LLM_MAX_CALLS`
now defaults **ON** (60/run, cache-counted) instead of 0. Per-tenant budgets are call
counts and stay (FULL_AI 500/day ≈ $5–10 worst case at gpt-4o; 60/run ceiling ≈ $1) — no
change required, but `LLM_MAX_CALLS` / the daily cap can be lowered for a tighter $ ceiling.

**Safety unchanged**: unset key → `configured` False → 503; over-budget → 429; HITL PENDING,
TokenLedger metering, anonymised feedback, name-free succession, read-only/RBAC-bound chat
all flow through the same gateway. Key read from env only (never hardcoded/printed/staged).
**[test]** `apps/ai/tests/test_openai_provider.py` (8, requests mocked — no network);
FakeLLMProvider still covers the agent graphs; full backend 1209. Live OpenAI smoke pending
Hari's key in `.env`.

### D31 (RW_BUILD_1) — Nav visibility = the screen's primary-read capability; minRole ≡ capability

**Decision.** Drive the sidebar/dashboard visibility of each screen from the **backend capability its
primary (landing) read requires**, expressed as a per-item `minRole`. An item appears for a role iff the
role can use that screen's primary view. This is valid because every capability in `apps/rbac/matrix.py`
is granted to an **upward-closed** role slice (`_EVERYONE`/`_MANAGER_UP`/`_HRBP_UP`/`_ADMIN_ONLY`), so
`atLeast(minRole)` is exactly equivalent to `role_has_capability` — no separate capability map needed on
the client.

**Consequences (the re-cut, RW_BUILD_1):**
- **Employees gain Goals/Feedback/Reviews/Career** (own-scoped) — the sidebar shows them and the
  over-restrictive frontend `RoleGate min="MANAGER"` on `/goals`,`/reviews`,`/feedback` is removed.
  This is **not** an RBAC weakening: the frontend gate was *stricter* than the backend, which already
  grants `VIEW_OWN_GOALS`/`VIEW_OWN_REVIEW`/`GIVE_FEEDBACK` to all roles (own scope) and still enforces
  it server-side. Defense in depth is intact.
- **Enterprise screens (succession, org, JD, audit) demote to an HRBP+ "Advanced" group**; managers no
  longer carry them on the everyday surface. Routes + backend gates are **unchanged** — a manager can
  still deep-link to `/succession` (backend `VIEW_SUCCESSION` allows Manager+); we simply stop
  advertising it (per the re-weighting plan: "routes still exist and work").

**Options considered.** (a) Mirror the full capability matrix in TS and check `role_has_capability` on
the client — rejected: duplicates the matrix, drift risk, and is behaviourally identical given the
upward-closed grants. (b) Keep coarse hardcoded minRoles unrelated to caps — rejected: that is exactly
the current mismatch. (c) **[chosen]** minRole = lowest capability-holding role, documented per item in
`docs/NAV_RBAC_MAP.md`.

**Deviations from the (absent) PRODUCT_REWEIGHTING_PLAN.md, defaulted safely (see Q3–Q5):**
integrations/tenant-config/entitlements/users stay **Admin-only** (the plan's "HR set" listed Settings/
Integrations, but the backend gates them to Admin — exposing to HRBP would be a dead link); Check-ins/
1-on-1/Recognition/Templates are **omitted** (no routes yet — RW_BUILD_2/3); Approvals kept on the
Manager+ "Team" surface (a core workflow the plan didn't explicitly place).

### D32 (RW_BUILD_2) — Recognition: server-enforced visibility; sender-only delete; fixed values

**Decisions (kept deliberately simple — "do not over-build"):**
- **Visibility is enforced server-side** in `apps.recognition.services.recognition_feed` (one Q-object
  predicate) — never trusted from the client. PRIVATE = the two parties ONLY (not even HR/Admin —
  private is private); MANAGER_ONLY = + the recipient's direct manager; TEAM = + the recipient's/sender's
  immediate team (you manage a party, or share a manager with one); COMPANY = everyone in the tenant.
  Role/data-scope does NOT widen this — visibility is a property of the card. Reacting is gated the same
  way (react only to a card you can see; otherwise 404, never reveal it exists). This is the load-bearing
  security property, proven by `test_visibility_matrix` (8 viewers × 4 levels).
- **No edit; sender-only soft delete** (no time window — simpler than the "within a window" default;
  a window can be added if abuse appears). **No self-recognition.**
- **Company values are a FIXED default list** (`models.COMPANY_VALUES`), validated on create. Per-tenant
  customisation of the value list is deferred (Q7) — a config model would be over-building for now.
- **Analytics is aggregate-only** (total, top values, visibility breakdown, the caller's own
  given/received) — **no per-person leaderboard**, which would re-identify individuals.

### D33 (RW_BUILD_3) — Check-ins: scope in the service; core loop now, optional extras deferred

**Decisions:**
- **Scope is enforced in `apps.checkins.services`**: an employee writes/reads their OWN check-ins; a
  manager reads + responds within their reporting subtree (`actor_can_access`); cross-manager / peer →
  **404** (never reveal), cross-tenant impossible (TenantScopedManager). Proven live (a report's manager
  sees the check-in; a different manager gets an empty team feed + 404 detail).
- **One check-in per (author, week)** (`update_or_create`); priorities are REPLACED on re-submit (a
  queryset bulk-delete; carry-forward is a *status*, not a copy). Manager response is one-per-check-in.
- **Goal progress is a READ-ONLY pull** from the goals engine (`kpi_attainment`) — the check-in stores
  no goal/review state (it feeds review evidence; it is not a review). Proven by a test that the pull
  creates nothing.
- **Built the core loop; deferred the OUTLINE's *optional* extras** (Q8): the AI manager-side check-in
  summary moves to the AI builds (RW_BUILD_4/5) so RW_BUILD_3 needs ~zero LLM calls; the cadence "due"
  nudge + rotating custom questions are deferred (not needed to demonstrate the loop). The check-in
  already feeds review evidence by being readable scoped data; no review-state duplication.

### D34 (RW_BUILD_4) — AI assistant: propose-and-confirm (HITL), execution = the human path

**Decision.** The chat assistant's WRITE intent no longer just refuses — for a SUPPORTED, permitted
action it returns an inert **proposal** the UI renders as an Approve/Cancel card. Nothing executes until
the human taps Approve, which calls `POST /api/ai/actions/execute`. Hard invariants (all tested):
- **A proposal writes nothing** — only `execute_action` writes, only on the explicit tap.
- **Execute re-checks capability + object scope on the REAL targets** — it mirrors the human endpoint
  exactly (approve_goals = `APPROVE_GOALS` + `actor_can_access(goal.employee)` + the `goal.approved`
  audit + the same stamp). It can never do what the user couldn't do directly; out-of-scope targets are
  skipped, not approved.
- **Audited + idempotent** — each approval audits once; re-running an approved action is a no-op.
- **No capability → no proposal AND no execute** (an employee gets neither).

**Design choices.** The LLM decides only that the message is a WRITE *intent* (via the existing gateway
classification); the action MAPPING + target resolution + execution are **deterministic and
permission-checked** — the model never picks or runs the action. Started with ONE action
(`approve_goals`) behind an extensible registry (`apps/ai/actions.py`); more actions are a follow-up
(Q9). This keeps the headline upgrade small + safe first.

**Verified live:** ada chats "approve my team's goals" → proposal (1 OpenAI call); Approve → execute
200/approved 1; goal stamped by ada + 1 audit row; a second execute is a no-op; an employee's execute →
403.

### D35 (RW_BUILD_5) — AI goal-writer: a gateway-routed, HITL draft (persists nothing)

**Decision.** Shipped ONE AI quick win — the goal-writer — as the highest-value, self-contained one
(the outline explicitly allows "whichever you value most first"). A one-line intent → an editable SMART
goal draft (title + objective + 1–3 KPIs) via the one `LLMGateway` (budget → scrub → schema-validate →
meter → confidence), so it's metered, budget-bounded, and degrades to a clean 503 with no provider.
**HITL:** it persists NOTHING — the draft prefills the New-Goal form and the human edits + creates the
goal through the existing scope-gated, audited create endpoint.

- **Gating:** `POST /api/goals/ai-draft` requires `MANAGE_REPORTS_GOALS` (the same capability as goal
  creation) — an employee gets 403. No new entitlement/pack was added (gateway budget + capability gate
  cover it); the pack mapping (which tier includes the goal-writer) is a follow-up (Q10).
- **Frontend:** a "Draft with AI" field in the New-Goal dialog prefills title + objective + KPIs (weights
  evenly split to sum to 100, so the draft is immediately valid) — all editable before create.
- Tests use `FakeLLMProvider` (no network). Verified live: ada drafts a real goal (1 OpenAI call), nothing
  persisted, employee 403.

### D36 (RW_BUILD_5 overnight) — AI quick wins built BACKEND-ONLY + additive (the safe surface)

**Context.** An unattended overnight run with hard limits: touch ONLY additive AI features; do NOT modify
auth/SSO, the shared layer, deployment/Docker, navigation, or any existing passing module; never push a
red state. **Decision:** build each remaining AI quick win as a **backend-only, additive** feature in
`apps/ai` — a new agent + endpoint + tests through the existing `LLMGateway` (budget→scrub→validate→
meter→HITL), reading existing models READ-ONLY, **reusing existing capabilities** (no `matrix.py` change),
with `FakeLLMProvider` in tests and **zero live OpenAI**. The UI wiring (which would require the shared
layer + navigation — both forbidden surfaces) is deferred to a per-feature **follow-up spec in `docs/`**
for Hari's morning review. Each feature is its own committed+pushed+green phase; on any red, leave the last
green state, write `BLOCKER_<phase>.md`, and move to the next independent feature.

**Why safe.** The forbidden surfaces (auth/SSO/shared/deploy/nav) are exactly the ones that caused silent
breakage before; backend-only additive endpoints can't affect them. Reusing capabilities avoids touching
core RBAC. Every feature is HITL (drafts/proposes, never decides) and scope/tenant-bound.

### D37 (UI #1 follow-up) — AI prompt-quality contract for the human-read quick wins

**Context.** Feature #1 (meeting-summary) was plumbed correctly but its first live OpenAI output was poor:
it opened with filler ("the week has been strong"), dropped specifics (a "recognition feed" win vanished;
"design review for the check-in form" was flattened to "the process"), and the action item merely restated
the blocker ("unblock the design review process"). That's a PROMPT problem, not plumbing.

**Decision.** Every human-read AI quick win obeys this prompt contract, and it lives in the **SYSTEM prompt**
(`apps/ai/agent_config.py`, one tunable place — never duplicated in the agent's user turn):
  1. **Preserve specifics verbatim** — keep the names, concrete nouns and numbers from the input in the
     input's own words; never generalise ('a feature', 'the process') and never silently drop one.
  2. **No filler / preamble / mood-setting** — lead with substance; ban 'the week was strong', 'overall',
     'it is worth noting'.
  3. **Actionable + assigned** — action items / recommendations state WHO does WHAT (and to whom / by when
     if the input says); a restatement of a problem is NOT an action item.
  4. **Short** — say it once, no padding to length.
  5. **Invent nothing** not present in the input; output ONLY the required JSON.

This reinforces the existing `STYLE_SPEC` (already on the review/JD/career agents) and now governs the
quick wins too. **#2 review-quality, #3 stale-goal suggestion, #4 NL-search, #5 assistant actions inherit
these principles** as they are tuned/wired.

**Verification of the change.** Deterministic tests can't judge LLM quality, so the suite pins the two
things that DO determine it: the notes reach the model **verbatim** (recording-fake test over 3 example
notes) and the system prompt **encodes the contract** (asserted on `system_prompt_for('meeting_summary')`).
Actual quality is judged by ONE live OpenAI call. Before→after on the same notes:
  * BEFORE: "The week has been strong… unblocking the design review is a priority" / "Unblock the design
    review process." (filler; win dropped; blocker flattened; action = restatement).
  * AFTER: "Shipped the recognition feed slice; currently blocked, waiting on a design review for the
    check-in form." / "Ada to follow up on the design review for the check-in form with the design team."
    (no filler; both specifics kept verbatim; action names an owner + target). Prompt-only change — no
    plumbing touched.
  * Owner-agnostic refinement (no extra live call): the live AFTER named "Ada" only because the
    instruction's EXAMPLE used "Ada" — the notes named no doer. The example now shows the owner being
    COPIED from the notes ('Lin will sort the export' -> 'Lin to fix the export') with an explicit
    no-named-owner fallback, so the model takes owners ONLY from the notes. The same owner-less note now
    reads "Follow up on the design review for the check-in form with the design team" (no invented name).

**Schema reconciliation (Finding D).** The retune drifted the prompt and the meeting-summary SCHEMA apart:
the prompt invited an empty `action_items` ("return []") while the model sometimes also omitted the key or
returned `summary` as a list — the gateway correctly returned `SCHEMA_INVALID` (graceful 503), but valid
intent was being rejected. Reconciled BOTH sides: (a) added a `ListOf(item_spec)` marker to
`apps/ai/schemas.py` — a REQUIRED list must be present, non-empty, and item-shaped (Finding D: an empty
`action_items`/`tiers`/`responsibilities` is a hollow answer, and a list of objects where strings are
expected fails too); meeting-summary SCHEMA is now `{summary: NonEmpty(12), action_items: ListOf(NonEmpty(1))}`.
(b) Pinned the prompt to EXACTLY two keys — `summary` a single string, `action_items` a JSON array of
≥1 strings — and replaced "return []" with "always ≥1 item; if no task, a single 'No action needed' item",
so a valid TERSE answer is never wrongly rejected. Locked by tests: `validate_shape` unit tests for
`ListOf` and a meeting-summary shape-lock test (empty/missing/object-item/list-summary all fail; terse
valid passes). Confirmed live: an action-light note now returns OK with `["No action needed — informational
catch-up."]` instead of SCHEMA_INVALID. Prompt + schema only — no plumbing changed.
