# BUILD NOTES

Append-only log of what each module delivered, per CLAUDE.md.

---

## Module 1 — Foundation (Identity, Access & Tenancy)

**Status:** ✅ Complete. **201 tests passing** on the locked stack (Django 4.2 +
DRF, MySQL 8, Redis 7, Celery, simplejwt, django-allauth, django-otp, Argon2)
inside Docker. Build contract: `docs/Document_2_..._Specification.md` §Module 1,
§2 (Roles & Permissions), §3 (System-wide Conventions), §Module 13 (Admin & Billing).

### What was built

**Project scaffold & infra**
- `config/` settings split (`base` / `dev` / `prod` / `test`), `celery.py`,
  `urls.py`, `wsgi.py`, `asgi.py`. DRF + simplejwt configured; Argon2 is the
  default password hasher; Redis is cache + session store + Celery broker/result
  backend (**no Kafka** — Redis is the only broker for MVP, overriding the spec's
  §4 diagram per CLAUDE.md). Structured JSON logging.
- `requirements.txt` / `requirements-dev.txt` (pinned), `Dockerfile`,
  `docker-compose.yml` (web, mysql8, redis7, celery-worker, celery-beat),
  `db/init.sql`, `.env.example` (every env var documented), `pytest.ini`.
- `apps/core`: `/healthz` liveness endpoint + tests.

**Tenancy core (`apps/tenancy`)** — the isolation foundation
- `Tenant` (UUID pk, name, slug, status) and `TenantScopedModel` abstract base
  (UUID pk, tenant FK, created/updated/deleted timestamps, **soft delete**).
- `TenantScopedManager` / `TenantScopedQuerySet`: every read auto-scoped to the
  current tenant and **fails closed** (returns nothing, never the whole table)
  when no tenant is bound; soft-deleted rows hidden by default.
- Current tenant lives in a **contextvar** set ONLY from the cryptographically
  verified JWT claims by `TenantMiddleware` — never from headers/body/query.
- `save()` enforces write-side isolation: you can only write into the bound
  tenant; cross-tenant writes raise; no-context+no-tenant writes raise.
- One escape hatch, `.all_tenants()`, for system/migration code only — it
  **raises if called on any request path** (a request-active contextvar guards it).

**Identity & auth (`apps/identity`)**
- Custom `User` on `TenantScopedModel` + `AbstractBaseUser`/`PermissionsMixin`:
  UUID pk, tenant FK, `email` (**unique per tenant**), `role`
  {EMPLOYEE, MANAGER, HRBP, ADMIN}, `manager` self-FK (org/reporting tree),
  `mfa_enabled`, `is_active`. Argon2 hashing.
- JWT (simplejwt) with custom claims embedding `tenant_id` + `role` + `email` on
  both access and refresh tokens; claims survive refresh-token rotation.
- Endpoints (`/api/auth/…`): `login` (tenant-qualified local creds → 401 on bad
  creds), `token/refresh`, `logout` (refresh blacklist + session flush),
  `mfa/enroll`, `mfa/enroll/confirm`, `mfa/challenge`, `me`, `oidc/complete`.
  Login enforces MFA only when `user.mfa_enabled`; sessions written to Redis.
- OAuth/OIDC via django-allauth generic OIDC provider configured entirely from
  env (demoable with placeholder config). `TenantSocialAccountAdapter` maps a
  verified OIDC identity to an existing tenant user (resolves tenant from a
  `?tenant=<slug>` hint / session / configured default), denying 403 for unknown
  identities; the IdP never provisions accounts.
- `TenantModelBackend` resolves the session principal by globally-unique pk on
  the SSO bootstrap (the scoped manager fails closed before a tenant is bound).

**RBAC engine (`apps/rbac`)** — implements the §2 matrix server-side
- `matrix.py`: the capability→roles table (the single source of truth);
  `bypass_tenant_isolation` / `alter_audit_log` map to **nobody**.
- `scope.py`: data scopes OWN (employee) / TEAM (manager's reporting subtree,
  transitive) / TENANT (HRBP, Admin), with cross-tenant defence-in-depth.
- DRF `HasCapability` (role/verb gate) + `WithinScope` (object/row gate),
  `RBACMixin`, `requires_capability` decorator. Out-of-scope targets (e.g. a
  peer record) → 403.

**Audit log (`apps/audit`)** — immutable, enforced at two layers
- Append-only `AuditLog` (UUID pk, tenant, actor, action, target, justification,
  metadata JSON, created_at; `db_table = "audit_log"`).
- App layer: queryset `update()`/`delete()` and re-`save()` of an existing row
  all raise `AuditLogImmutableError`.
- DB layer: migration `0002` adds MySQL `BEFORE UPDATE` / `BEFORE DELETE`
  triggers that `SIGNAL SQLSTATE '45000'` — proven to reject even raw SQL.
- `services.record(...)` writer + `audit_action(...)` context manager (writes
  the record before the side effect).

**Billing & entitlements (`apps/billing`)** — decoupled commercial model
- `Entitlement` per tenant with **independent** `seat_count` (int) and
  `feature_packs` (set of pack codes). "Tier" is a display label only.
- Pack registry: `STARTER → {agent1, agent2}`, `FULL_AI → {agent1…agent5}`.
- `requires_entitlement(agent_code)` DRF gate (API-level feature flag);
  `upgrade_to_full_ai()` adds the FULL_AI pack — unlocking agents 3–5 instantly
  **without touching seat_count** — and audits the change (admin-only endpoint).

### Files created
Full app trees under `apps/{core,tenancy,identity,rbac,audit,billing}/` (models,
managers, services, serializers, views, urls, permissions, migrations as
applicable) plus `apps/testsupport/` (test-only concrete `TenantScopedModel`),
`config/` (settings/celery/urls/wsgi/asgi), root `conftest.py`, infra files
(`Dockerfile`, `docker-compose.yml`, `db/init.sql`, `requirements*.txt`,
`.env.example`, `pytest.ini`, `.gitignore`, `.dockerignore`).

### Tests written and passing (201 total, MySQL-backed)
- tenancy 11 (cross-tenant read/write impossible, fail-closed, soft delete,
  all_tenants request-path guard).
- identity 29 (login success/MFA/401 paths, MFA enroll+confirm+challenge, refresh
  claim preservation, logout blacklist, session-to-store, OIDC mapping +
  complete, Argon2, email-unique-per-tenant, reporting line).
- rbac 89 (every role × every capability incl. nobody-bypass; OWN/TEAM/TENANT
  scope incl. manager-vs-peer 403 and cross-tenant denial; end-to-end HTTP via JWT).
- audit 15 (insert/select scoping, app-level immutability, **DB-trigger
  immutability against raw SQL**, writer tenant resolution).
- billing 27 (seats↔packs independence, locked agents denied → unlocked after
  upgrade, seat_count preserved across upgrade, admin-only 403, audit on upgrade).
- core 2 (/healthz).

### How to run
```bash
docker compose up -d --build              # bring up the stack
docker compose run --rm web pytest        # full suite (creates a MySQL test DB)
docker compose run --rm web python manage.py migrate   # apply migrations
```
Tests force `config.settings.test` via `pytest.ini` `--ds` (highest precedence,
above the `DJANGO_SETTINGS_MODULE` env var compose sets to dev).

### Known risks / TODOs
- **HRBP scope = tenant-wide (MVP approximation).** §2 describes HRBP as
  "business-unit wide", but there is no `BusinessUnit` model yet, so HRBP shares
  Admin's data *scope* (they differ on *capabilities*). When BU lands, revisit
  only `scope_for_role` + the TENANT branch of `actor_can_access`.
- **Deployment requirement for audit triggers.** Creating the `audit_log`
  triggers needs `log_bin_trust_function_creators=1` (set on the mysql service in
  compose) OR granting the migrating user `SUPER`/`TRIGGER` when binary logging is
  on. A managed prod MySQL must set this before `migrate`.
- **Soft-delete + email uniqueness.** `(tenant, email)` uniqueness is a plain
  constraint (MySQL has no partial indexes), so a soft-deleted user keeps its
  email reserved until hard-deleted. Acceptable for MVP; revisit if re-using
  emails of deactivated users becomes a requirement.
- **OIDC live round-trip.** The generic OIDC provider is wired and configured
  from env, and the tenant-mapping adapter + post-login JWT mint are unit/E2E
  tested; a full browser round-trip against a real IdP is integration-level and
  not exercised here (SAML is Phase 2 per spec).
- Local host runs Python 3.14 (Django 4.2 won't run there) and has no MySQL/Redis
  client — **all dev/test goes through Docker** (python:3.11 + mysql8 + redis7).
  Host ports remapped to 3307 (mysql) / 6380 (redis) to avoid local clashes.

### What Module 2 (Goals & KPIs) needs from this
- Inherit `apps.tenancy.models.TenantScopedModel` for every new model (gets UUID
  pk, tenant FK, soft delete, scoped manager + write isolation for free).
- Gate endpoints with `apps.rbac`: `RBACMixin` + a `Capability` (e.g.
  `manage_reports_goals`, `view_team_analytics`) and `WithinScope` for row-level
  checks against the reporting tree. Add new capability keys to `rbac/matrix.py`.
- Write audit rows via `apps.audit.services.record(...)` before consequential
  actions; never mutate audit rows.
- Gate AI-agent features with `apps.billing.gate.requires_entitlement("agentN")`
  (Agent 2 — KPI Intelligence is `agent2`, in STARTER).
- Resolve the current user/tenant from `request.user` / `request.user.tenant`;
  the tenant context is already bound by `TenantMiddleware` from the JWT.
- Reporting-tree helpers: `apps.rbac.scope.reporting_subtree_ids(manager)` and
  `User.manager` / `User.reports`.

---

## Phase 1.5a — Horizontal-Scaling Foundation

**Status:** ✅ Complete. **217 tests passing** on MySQL 8 + Redis 7 in Docker.
Adds NO product features — it makes the existing backend safe to run as multiple
stateless web replicas and lays the caching + health groundwork later modules
build on. Also folds in two Module-1 security-review fixes. Stack unchanged.

### What was built

**App server & scaling**
- `gunicorn.conf.py`: `workers = (2 × cores) + 1`, `threads = 2`, `timeout = 60`,
  `max_requests = 1000` + `max_requests_jitter = 100`, stdout/stderr logging.
  All overridable via `GUNICORN_*` env. Dockerfile `CMD` now runs gunicorn with
  this config (not `runserver`).
- `nginx.conf` + an `nginx` compose service (host `:8080` → `:80`). Round-robins
  across `web` replicas by re-resolving the compose service name per request via
  Docker DNS (resolver `127.0.0.11` + variable `proxy_pass`). `web` has no host
  port and is scaled with `docker compose up --scale web=3`. Verified: `/readyz`
  returns 200 through nginx served by 3 distinct replica IPs; `X-Served-By`
  header exposes which replica handled each request.
- mysql service capped at `--max-connections=100`.

**Statelessness (decision 1)** — verified, not just asserted
- The only per-request state is the current-tenant contextvar, set from the
  verified JWT by `TenantMiddleware` and reset in `finally`. No module-level
  mutable request/tenant globals; no local-disk writes on the request path.
- Tests (`apps/tenancy/tests/test_statelessness.py`): a fresh request starts with
  no tenant bound; an authenticated request binds the tenant but a subsequent
  request on the same worker thread sees `None` (no cross-request bleed); both
  the tenant and request-active contextvars are clean outside any request.

**Connections (decision 3)**
- `CONN_MAX_AGE = 60` (persistent) + `CONN_HEALTH_CHECKS = True` (revalidate a
  reused connection per request) on the default DB. Explicitly did NOT add
  django-db-geventpool (gevent monkeypatch conflicts with mysqlclient).

**Redis split (decision 4)** — one instance, isolated logical DBs
- `/0` Celery broker + results, `/1` application cache, `/2` sessions (separate
  `sessions` cache alias; `SESSION_CACHE_ALIAS = "sessions"`). The redis service
  runs `--maxmemory-policy noeviction` so memory pressure can never silently drop
  queued jobs; documented on the service that prod should run a *separate* Redis
  (or allkeys-lru) for the cache so cache churn can't starve the broker.

**Caching framework (decision 5)**
- `CACHES["default"]` = django-redis on `/1`, `KEY_PREFIX = "pms"`, `TIMEOUT = 300`.
- `apps/core/cache.py`: `tenant_cache_key(tenant_id, *parts)` — EVERY cache key
  embeds the tenant id (cross-tenant cache isolation is treated as a security
  control), plus `invalidate_tenant_cache(tenant_id, *parts)` (django-redis
  `delete_pattern`). Tested: two tenants computing the same logical key get
  distinct keys; invalidation clears only the target tenant.
- First user: `apps/billing` caches the per-tenant entitlement lookup
  (`get_entitlement_cached`, 300s) on the hot read path (the `requires_entitlement`
  gate) and invalidates via `delete_pattern` on `upgrade_to_full_ai` /
  `set_seats`. Tested: cache hit does zero DB queries; upgrade invalidates and a
  fresh read reflects FULL_AI.

**Health & readiness (decision via Agent C)**
- django-health-check. `/healthz` stays pure liveness (no dependency checks).
  `/readyz` runs all backends — DatabaseBackend, Cache (default + sessions),
  RedisHealthCheck, MigrationsHealthCheck, and a custom `CeleryBrokerHealthCheck`
  (broker *connection* reachability via `kombu`, NOT a worker ping, so a web
  replica is ready without a running worker) — returning 200 only if all pass,
  else 503 with minimal per-check `up`/`down` JSON. Tested: 200 when all up; 503
  with a backend mocked down; `/healthz` stays 200 even when a dependency is down.

**Security fixes (Module 1 review)**
- `config/settings/prod.py`: `SECRET_KEY = env("DJANGO_SECRET_KEY")` with NO
  default — prod refuses to boot without it (mirrors ALLOWED_HOSTS), and the JWT
  signing key is re-pointed at it. Tested in a clean subprocess: prod `django.setup()`
  fails without the key and succeeds with it.
- `apps/identity/adapters.py`: the OIDC adapter now requires the IdP
  `email_verified` claim to be true before mapping an identity to a tenant user
  (denies 403 otherwise), rejecting before the user lookup. Tested: unverified /
  missing claim denied; same identity with `email_verified=True` maps through.

### Files
New: `gunicorn.conf.py`, `nginx.conf`, `apps/core/cache.py`, `apps/core/health.py`,
`apps/core/tests/{test_cache,test_readyz,test_settings}.py`,
`apps/billing/tests/test_cache.py`,
`apps/tenancy/tests/{views,urls,test_statelessness}.py`.
Changed: `config/settings/{base,prod,test}.py`, `conftest.py`, `requirements.txt`
(+`django-health-check==3.18.3`), `.env.example`, `Dockerfile`, `docker-compose.yml`,
`apps/core/{views,urls,apps}.py`, `apps/identity/{adapters.py,tests/test_oidc.py}`,
`apps/billing/{services,views}.py`.

### max_connections sizing note
The mysql service caps connections at 100. With persistent connections
(`CONN_MAX_AGE=60`) each gunicorn worker thread holds a DB connection, so:

    peak_conns ≈ web_replicas × gunicorn_workers × threads
                + celery_worker_concurrency + headroom

e.g. 3 replicas × 9 workers × 2 threads = 54, plus Celery and buffer, stays under
100. Raise `--max-connections` (and DB resources) — or cap gunicorn `workers`
via `GUNICORN_WORKERS` — before scaling past that envelope. (Documented inline in
`config/settings/base.py` on the DATABASES block.)

### Tests
217 passing (Module 1's 201 + 16 new: statelessness 3, core cache 4, readyz 3,
prod-secret 2, billing cache 3, OIDC unverified-email 1). Test cache is real
django-redis on dedicated scratch DBs (15/14) so `delete_pattern` and cache
semantics are exercised as in prod; an autouse conftest fixture flushes them per
test. Suite runs only inside Docker (local host is Python 3.14 with no MySQL).

### Known risks / notes
- **Single Redis instance, noeviction global.** Broker safety (no eviction) is
  guaranteed, but the cache shares the policy — under memory pressure cache
  *writes* fail rather than LRU-evicting. Fine for MVP (cache entries are TTL'd
  and optional); production should split broker vs cache into separate Redis
  instances (cache on allkeys-lru). Documented on the compose redis service.
- **nginx DNS round-robin** uses Docker's embedded DNS with `valid=5s`, so
  distribution is approximate within a 5s window (observed traffic reaching all 3
  replicas). For finer control use a real LB / Swarm/k8s service in production.
- **Sticky-session assumption: none.** Sessions live in shared Redis `/2`, so any
  replica can serve any request — required for the stateless web tier.
- Prod runs gunicorn with `config.settings.prod` (wsgi default); the local
  `--scale` validation uses `config.settings.dev` (compose default) so there is
  no HTTPS redirect in front of plain-HTTP curl.

### What the next module needs from this
- Cache anything tenant-scoped through `apps.core.cache.tenant_cache_key(...)` and
  invalidate with `invalidate_tenant_cache(...)`; never build a cache key without
  the tenant id.
- New external dependencies a request truly needs at readiness → add a
  health-check backend (register in an app's `ready()`); keep `/healthz` pure.
- Assume N stateless web replicas: no in-process caches/locks/globals for
  cross-request state; use Redis/DB.

---

## Phase 1.5b — Rate Limiting & Observability

**Status:** ✅ Complete. **238 tests passing** on MySQL 8 + Redis 7 in Docker.
Adds NO product features — per-tenant/per-user rate limiting tied to entitlements
plus the observability layer (request-id correlation, structured-log enrichment,
Sentry, Flower). Folds in nothing new from the security review (those landed in
1.5a). Stack unchanged.

### What was built

**Rate limiting (DRF-native, entitlement-driven)**
- `apps/billing/services.rate_limits_for(tenant_id) -> {"tenant","user","ai"}` —
  DRF rate strings derived from the tenant's entitlement, NOT hardcoded at call
  sites: STARTER `{600,120,20}/min`, FULL_AI `{3000,600,120}/min`. Cached under
  `tenant_cache_key(tid, "rate_limits")` (300s) and invalidated together with the
  entitlement cache by clearing the whole tenant namespace on `upgrade_to_full_ai`
  / `set_seats`.
- `apps/core/throttling.py`: `TenantThrottle` (key `thr:t:{tenant}`), `UserThrottle`
  (`thr:u:{tenant}:{user}`), `AIThrottle` (`thr:ai:{tenant}:{user}`) — all
  `SimpleRateThrottle` subclasses that read their rate from `rate_limits_for` per
  request. EVERY key embeds tenant_id (cross-tenant counter isolation = a security
  control). Anonymous requests pass through (handled by AnonRateThrottle on login).
  Throttled requests raise a custom `RateLimited(Throttled)` → **429 + Retry-After**,
  with an `upgrade_hint` in the body for the tenant/AI buckets.
- `DEFAULT_THROTTLE_CLASSES = [TenantThrottle, UserThrottle]`. `AIThrottle` is
  implemented + tested but attached to NO endpoint yet — wired so Module 10 adds it
  to AI viewsets with one line (`throttle_classes = [..., AIThrottle]`).
- `AnonRateThrottle` attached to `LoginView` + `MfaChallengeView` (IP-throttle the
  unauthenticated surface against credential/MFA-code stuffing).
- DRF `SimpleRateThrottle` is a rolling-log window; fixed-window is fine for MVP. A
  comment in `throttling.py` marks the precise sliding-window upgrade path (Redis
  sorted-set + Lua INCR/EXPIRE).

**Observability**
- `apps/core/middleware.RequestIDMiddleware` (outermost): reads inbound
  `X-Request-ID` or mints a uuid4, binds it to a contextvar, stashes
  `request.request_id`, echoes `X-Request-ID` on the response, resets in `finally`
  (same no-bleed discipline as the tenant contextvar).
- `apps/core/logging.RequestContextFilter` enriches every log record with
  `request_id` + `tenant_id` (both `"-"` when unbound); the JSON formatter includes
  them, so every application log line is correlatable.
- `apps/core/observability.py`: `init_sentry(dsn, environment, traces_sample_rate)`
  — no-op (app boots normally) when `SENTRY_DSN` is unset; otherwise wires the
  Django + Celery integrations with `send_default_pii=False`. `before_send` scrubs
  Authorization/Cookie headers and redacts JWT/secret-named fields
  (authorization/token/access/refresh/password/mfa_token) across request data,
  cookies and extra, and tags events with `tenant_id` + `request_id`.
- **Flower**: a compose `flower` service on the existing Celery app/broker, port
  5555, basic-auth REQUIRED via `FLOWER_BASIC_AUTH` (never unauthenticated).

### Files
New: `apps/core/throttling.py`, `apps/core/middleware.py`, `apps/core/logging.py`,
`apps/core/observability.py`, `apps/core/request_context.py`,
`apps/core/tests/{test_throttling.py,throttle_urls.py,test_request_id.py,test_logging.py,test_sentry.py}`,
`apps/billing/tests/test_rate_limits.py`.
Changed: `config/settings/{base,test}.py`, `apps/billing/services.py`,
`apps/identity/views.py`, `requirements.txt` (+`sentry-sdk==2.18.0`, `flower==2.0.1`),
`.env.example`, `docker-compose.yml`.

### Env-flippable Redis split (decision 8 — the 1.5a known-risk fix)
Broker + results stay on Redis `/0` with `noeviction`. The cache and sessions are
addressed by their OWN env URLs (`REDIS_CACHE_URL` `/1`, `REDIS_SESSION_URL` `/2`),
so **production points them at a SEPARATE Redis instance (allkeys-lru) with no code
change** — just set the env vars. compose documents this on the app-environment
block. No second Redis container is added for MVP; the split is purely
configuration. (When split, the broker can never be starved by cache eviction.)

### Tests (238 total, +21)
billing rate_limits 4 (STARTER vs FULL_AI, cache hit 0-query, invalidation,
two-tenant independence); throttling 7 (tenant trip + 429/wait/upgrade_hint, user
independence + no hint, cross-tenant isolation, AI trip, anon bypass, e2e HTTP 429
+ Retry-After, anon-login cap); request-id 4; logging 2; sentry 4.

### Live validation (docker compose up)
`X-Request-ID` generated when absent and echoed when supplied; a hot loop on
`/api/auth/me` tripped at request 121 (STARTER user 120/min) → 429 with
`Retry-After: 59`; Flower returned 401 unauthenticated and 200 with basic-auth.

### Known risks / notes
- **Throttle precision:** DRF's rolling-log throttle stores per-window timestamps
  in the cache and is approximate under heavy concurrency across replicas (the
  cache is shared, so counters are global, but check-then-set is not atomic). For
  strict limits, move to the documented Redis sorted-set + Lua sliding window.
- **Cache eviction vs throttle counters:** throttle counters live in the cache DB
  (`/1`). With the MVP single-Redis `noeviction`, counters aren't evicted; once the
  cache is split to an allkeys-lru instance in prod, throttle counters could be
  evicted under pressure (fail-open). If strict enforcement matters, keep throttle
  counters on a non-evicting DB (another env-addressable split).
- **Sentry is opt-in:** disabled without `SENTRY_DSN`. PII scrubbing is enforced by
  `before_send` + `send_default_pii=False`; new event sources should be re-checked
  against the scrubber.
- **Flower auth** is HTTP basic over the app network; put it behind TLS / network
  policy in production and use a strong `FLOWER_BASIC_AUTH`.

### What the next module needs from this
- AI viewsets (Module 10): add `AIThrottle` to the view's `throttle_classes` (one
  line) to enforce the per-tenant AI budget; the rate already flows from the
  entitlement.
- Tenant-scoped rates: extend `rate_limits_for` (and invalidate the tenant cache)
  if a new pack changes limits.
- Correlate async work: `request_id`/`tenant_id` are on log records and Sentry tags
  on the web tier; propagate them into Celery task kwargs if cross-process
  correlation is needed.

---

## Module 2 — Goals & KPI Engine

**Status:** ✅ Complete. **382 tests passing** on MySQL 8 + Redis 7 in Docker
(Phase 1.5b's 238 + 144 new). Build contract: Document 2 §Module 3, §2, §3;
Document 3 §F1 (Agent 2) / Pattern 2. Stack unchanged. Built ON the foundation
(TenantScopedModel, RBAC, audit, cache) — not beside it.

### What was built (two new apps)
- **`apps/cycles`** — `PerformanceCycle` (DRAFT/ACTIVE/CLOSED, `elapsed_fraction()`
  for pace). Scoring is always scoped to (tenant, cycle).
- **`apps/goals`** — `Goal`, `Kpi`, `KpiMeasurement` (append-only actual history),
  `CycleScore` (unique per tenant+employee+cycle), `KpiTemplate`. Every model is a
  TenantScopedModel; every weight/ratio/value is **Decimal**, never float.

**Weight "= 100%" rule (exact Decimal equality, two levels)** — `validators.py`:
a goal's KPI weights and an employee's ACTIVE goals' weights must each sum to
exactly 100.00. 99.99 and 100.01 are rejected; 100.00 accepted. Surfaced in the
serializers (the editor's live-sum indicator) and tested at both levels + boundaries.

**Deterministic scoring engine** (`scoring/engine.py`, constants in
`scoring/constants.py`): per-KPI attainment (INCREASING actual/target, DECREASING
target/actual, actual==0→cap; clamped [0, 1.5]); goal raw = Σ(kpi.weight/100 ×
attainment); employee raw = Σ(goal.weight/100 × goal_raw) over ACTIVE goals;
two-pass normalisation over the cohort (μ, **population** σ, Z=(raw−μ)/σ,
T=50+10Z clamped [0,100]); deterministic `risk_status` (T tiers when the cohort is
sufficient, absolute-raw fallback when n<2 or σ==0 → `insufficient_cohort=True`);
`pace_behind` is a SEPARATE boolean (elapsed-fraction × 0.7) that never changes the
tier. All Decimal (engine sets `getcontext().prec=50` for exact `Decimal.sqrt`),
quantised to 4 dp internally / 2 dp display. `recompute_cycle_scores(tenant_id,
cycle_id)` (Celery `@shared_task`, also called directly/synchronously) upserts one
CycleScore per employee **idempotently** (re-running yields identical score fields,
no duplicate rows; only `computed_at` changes). A **golden worked example** test
locks the exact raw/z/t/risk numbers (the live demo reproduced them:
0.9→t62.2500 ON_TRACK, 0.6→t50 ON_TRACK, 0.3→t37.7500 AT_RISK).

**API (DRF, all RBAC-gated + audited):** cycles CRUD + recompute + score reads
(own / team / tenant by scope); goals CRUD (nested KPIs, weight-validated) +
manager approve; KPI CRUD with transactional weight re-validation; an OWN-scoped
actual-update endpoint (mobile self-service); KPI template list + instantiate.
Audits `cycle.created`, `goal.created`, `goal.approved`, `actual.recorded`,
`scores.recomputed` BEFORE the side effect.

**KPI templates:** `KpiTemplate` + a per-role `DEFAULT_TEMPLATES` catalogue (each
role's default_weights sum to 100), `seed_templates_for_tenant`, a
`seed_kpi_templates --tenant-slug` management command, and `instantiate_templates`/
`instantiate_role_templates` (validates weights = 100 in one transaction).

### Scoring constants + cohort decision
Constants live in `apps/goals/scoring/constants.py` (all tunable): ATTAINMENT_FLOOR
0, ATTAINMENT_CAP 1.5, T_CRITICAL 30, T_AT_RISK 40, ABS_CRITICAL 0.5, ABS_AT_RISK
0.8, PACE_SHORTFALL 0.7. **Cohort = all employees in the same (tenant, cycle) with
a raw score (≥1 ACTIVE goal); σ is population (divisor n).** `CycleScore.cohort_key`
defaults to `"tenant"` so role-based cohorts can be added later WITHOUT a migration
(the engine would group by cohort_key within tenant+cycle). The cohort NEVER spans
tenants (tested: a huge raw in tenant B does not move tenant A's Z/T).

### Agent-2 seam (Module 10 will own this)
`apps/goals/signals.py::cycle_scores_recomputed` is fired by the engine AFTER
storing scores, carrying structured risk data (`{employee_id, raw_score, z_score,
t_score, risk_status, pace_behind, insufficient_cohort, cohort_size}`). Module 10's
Agent 2 (Fast-AI KPI-Intelligence nudge, Doc 3 Pattern 2) connects a receiver here
to classify/compose/deliver. **This module composes/sends NOTHING.** The
`risk_status` is deterministic + core + ungated; the `requires_entitlement("agent2")`
gate attaches to Agent 2's nudge surface in Module 10, NOT to scoring.

### Jira seam (Module 12 will own the concrete client)
`apps/goals/services.record_actual(...)` is the single actuals write path (manual
AND Jira). `apps/goals/jira.py` is a real, loud seam: `JiraActualProvider` (ABC),
`NotConfiguredProvider` (raises `JiraNotConfiguredError`), `get_provider()`
(resolves `settings.JIRA_ACTUAL_PROVIDER` import-string, else NotConfigured), and
`sync_jira_actuals(tenant_id, cycle_id)` which logs-and-skips cleanly (returns
`{"synced":0,"skipped":n,"reason":"no_provider"}`) when unconfigured — never crashes.

### RBAC additions (`apps/rbac/matrix.py`)
Added `view_own_goals`, `update_own_actuals`, `approve_goals`, `view_team_scores`
(all Manager+; scope differs by role via WithinScope), `manage_kpi_templates`,
`configure_scoring` (admin), and `manage_cycles` (HRBP/Admin, for cycle CRUD —
added since §2 had no explicit cycle key). Goal create/edit reuses the pre-existing
`manage_reports_goals`. The matrix oracle test was extended to cover them.

### Files
New apps `apps/cycles/` and `apps/goals/` (models, validators, signals,
scoring/{constants,engine}, tasks, services, jira, templates, management command,
serializers, views, urls, migrations 0001, and tests test_models/test_weights/
test_scoring/test_actuals/test_jira/test_templates/test_api). Changed:
`config/settings/base.py` (LOCAL_APPS), `config/urls.py`, `apps/rbac/matrix.py` +
`apps/rbac/tests/test_matrix.py`, `apps/testsupport/factories.py` (Cycle/Goal/Kpi/
KpiMeasurement/KpiTemplate factories; tenant derived from parent to stay
single-tenant).

### Live validation (docker compose up)
admin→cycle 201; manager→3 goals (weights=100) 201; weight 99.99 → 400 with the
exact message; employees→own actuals 201, peer actual → 403; manager→recompute 200
(scored 3); team scores show the exact T/Z/risk; a Globex admin GET of an Acme
cycle's scores → 404 (cross-tenant isolation).

### Known risks / notes
- **Weight "=100" is a serializer/service invariant, not a DB constraint** (it
  spans rows). Direct ORM writes can create an unbalanced set; the API path
  enforces it. A goal can be saved DRAFT below 100 — the rule binds on the API and
  is the right place for the live editor.
- **Recompute is whole-cohort by necessity** (Z needs the tenant+cycle cohort), so
  a manager triggering a recompute recomputes every employee in that cycle (then
  only reads their own scope). It's idempotent, so this is safe.
- **`pace_behind` after a cycle's end** reads elapsed_fraction = 1.0, so anyone
  below 0.7 raw is "behind" — expected for a closed/past window; the flag is
  advisory and never changes the risk tier.
- **DECREASING with actual==0** is credited at the cap (1.5) — a deliberate "drove
  it to zero" reward; revisit if a metric legitimately bottoms at 0 without being
  a win.
- AI nudge composition (Agent 2) and the real Jira/Slack clients are explicitly
  OUT (seams left + documented above).

### What Module 3 (Reviews) / future modules need from this
- Extend `PerformanceCycle` for the review state machine (it was kept minimal for
  exactly this); Goals already FK a cycle.
- Read scores via `CycleScore` (per tenant+employee+cycle) and goal/KPI evidence
  via `Goal`/`Kpi`/`KpiMeasurement` for the Review Assistant (Agent 1) evidence
  gathering.
- Module 5 (Approvals) generalises the single `goal.approve` transition into the
  routing matrix.
- Module 10 (Agent 2) subscribes to `cycle_scores_recomputed`; Module 12 swaps a
  real provider into `apps.goals.jira.get_provider` via `settings.JIRA_ACTUAL_PROVIDER`.

---

## Module 3 — Reviews & Appraisal Cycles (build-order M3 = Doc 2 §Module 4)

**Status:** ✅ Complete. **467 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 2's 382 + 85 new). The FIRST HITL module: the human-in-the-loop gate and
the immutable audit from Module 1 are the centrepiece. Stack unchanged.

### What was built (`apps/reviews`)
- **Models** (all TenantScopedModel): `Review` (employee/reviewer/cycle FK to the
  EXISTING Module-2 `PerformanceCycle` — no second cycle model; state, draft/final
  bodies, `human_reviewer` NULL-until-approved, approved_at/finalized_at,
  rejected_reason, source MANUAL/AI, nullable confidence_score+citations for
  Agent 1; unique (tenant, employee, cycle)); `ReviewAssessment` (SELF/MANAGER/
  PEER/UPWARD, unique (tenant, review, assessor), SELF upserts, server-set
  submitted_at); `ReviewStateTransition` (append-style timeline powering the
  approval tracker — complements, never replaces, the AuditLog).

### The state machine (`apps/reviews/state_machine.py`)
Hand-rolled explicit transition table (no library) — the table IS the contract:

    DRAFT                -> AI_DRAFTING          request_ai_draft (Agent-1 seam)
    DRAFT                -> EDITING              start_edit (manual draft)
    AI_DRAFTING          -> PENDING_HUMAN_REVIEW ai_draft_ready (system lock)
    EDITING              -> PENDING_HUMAN_REVIEW submit_for_review
    PENDING_HUMAN_REVIEW -> EDITING              start_edit (edit again)
    PENDING_HUMAN_REVIEW -> APPROVED             approve (sets human_reviewer)
    PENDING_HUMAN_REVIEW -> REJECTED             reject (reason REQUIRED -> 422)
    REJECTED             -> EDITING              start_edit (revise)
    APPROVED             -> FINALIZED            finalize (single-step; M5 seam)

Every transition: legality vs the table (illegal → 409 naming from/action),
RBAC capability + row scope INSIDE the machine (peer manager / cross-tenant →
403), audit BEFORE the effect (proven by crash-injection: audit row exists, state
unchanged), persists, appends a timeline row. Transitions are `_tenant_bound`
(they bind the review's tenant like the Module-2 scoring engine) so they work on
requests AND off-request (Celery/tests). Re-running terminal/illegal transitions
(approve twice, finalize twice, edit FINALIZED) is REJECTED — never a no-op.

### THE HITL GATE — three layers, all proven
1. **State machine:** `finalize()` demands state==APPROVED AND non-null
   `human_reviewer` → else 422 (checks the reviewer, not just the state).
2. **Database:** CHECK constraint `ck_review_finalized_has_reviewer`
   (`state != 'FINALIZED' OR human_reviewer_id IS NOT NULL`) in migration 0001 —
   MySQL 8 enforces it. Tested AND live-demoed rejecting a direct ORM `save()`
   AND a queryset `.update()` (MySQL error 3819), the same standard as Module 1's
   audit-trigger raw-SQL proof.
3. **API:** finalize-without-approval returns **422 HITL_APPROVAL_REQUIRED**.
Status contract: 409 = illegal transition / structural conflict (incl. creating a
review against a non-ACTIVE cycle); 422 = HITL_APPROVAL_REQUIRED /
REJECTION_REASON_REQUIRED.

### API (mounted at /api/reviews/, all RBAC-gated + audited)
List/create (scope-filtered; create requires ACTIVE cycle, reviewer defaults to
the acting manager), detail (no direct PATCH — the machine is the only mutator),
timeline, assessments (SELF upsert by the subject only; MANAGER/PEER/UPWARD by
Manager+ in scope — broader peer/upward capture arrives with the Feedback
module), transitions (start-edit, submit + save-draft alias, approve, reject,
finalize, request-ai-draft), HRBP/Admin calibration read
(`/calibration?cycle=&state=`). Audits review.created / edit_started / submitted /
approved (with human_reviewer) / rejected (with reason) / finalized /
ai_draft_requested / ai_draft_ready / assessment.submitted.

### Agent-1 seam (Module 10 owns the agent)
`apps/reviews/agent1.py`: `ReviewAssistantProvider` ABC + `NotConfiguredProvider`
(raises tested `ReviewAssistantNotConfiguredError`) + `get_provider()` resolving
`settings.REVIEW_ASSISTANT_PROVIDER` (import string). `apps/reviews/tasks.py`:
`draft_review_with_agent1(tenant_id, review_id, actor_id=None)` — checks the
provider BEFORE transitioning (an unconfigured provider leaves the review in
DRAFT and returns `{"drafted": false, "reason": "no_provider"}`; the endpoint
surfaces 503 with a "lands in Module 10" detail); with a configured provider it
runs request_ai_draft (RBAC: an accountable human requester is REQUIRED —
actor_required otherwise) → provider.draft() → ai_draft_ready LOCKS the result
PENDING_HUMAN_REVIEW with confidence+citations (Doc 3 §5 pipeline). Module 10
will implement the provider (evidence gathering from Module-2 goals/scores +
Feedback, PII scrub, LangGraph via the LLM gateway) and gate its surface with
`requires_entitlement("agent1")`. The manual path reaches FINALIZED with no AI.

### Module-5 routing seam
`finalize` is deliberately SINGLE-STEP (APPROVED → FINALIZED). Module 5's
configurable approval matrix replaces the body of `state_machine.finalize` with
multi-step sequential/parallel routing, completing with the same audited
FINALIZED write. Documented in the state-machine module docstring.

### RBAC additions (`apps/rbac/matrix.py` + oracle test)
`manage_reviews`, `finalize_review` (Manager+), `view_own_review`,
`submit_self_assessment` (everyone), `submit_assessment` (Manager+),
`calibrate_reviews` (HRBP/Admin). The HITL approval reuses the pre-existing
`approve_review`; the AI-draft request reuses `run_ai_review_draft`.

### Files
New: `apps/reviews/` (models, exceptions, state_machine, services, agent1, tasks,
serializers, views, urls, migrations/0001 incl. the CHECK constraint, tests
test_state_machine/test_hitl/test_agent1_seam/test_api — 61 tests). Changed:
`config/settings/base.py` (+ReviewsConfig), `config/urls.py` (+/api/reviews/),
`apps/rbac/matrix.py` + `apps/rbac/tests/test_matrix.py`,
`apps/testsupport/factories.py` (+ReviewFactory, ReviewAssessmentFactory).

### Live validation (docker compose up, via nginx)
cycle 201 → review 201 (DRAFT) → SELF+MANAGER assessments 201 → start-edit/submit
200 (PENDING_HUMAN_REVIEW) → **finalize 422 HITL_APPROVAL_REQUIRED** → approve
200 (human_reviewer set) → finalize 200 (FINALIZED) → employee GET own finalized
200 → peer-manager GET 403 / transition rejected → Globex admin GET 404 →
**direct ORM FINALIZED+null-reviewer write rejected by MySQL CHECK 3819** →
timeline DRAFT→EDITING→PENDING_HUMAN_REVIEW→APPROVED→FINALIZED.

### Known risks / notes
- **Legality is checked before scope** in transitions, so probing a transition on
  a terminal review returns 409 even for out-of-scope actors (GET remains 403).
  State names are not sensitive; acceptable for MVP.
- **Assessments are capturable in any review state** (incl. after FINALIZED) —
  the cycle, not the review state, is the natural fence; revisit with Module 4
  (360 cycles) if capture must close at finalization.
- **PEER/UPWARD assessors currently require Manager+ capability** — deliberate
  until the Feedback module brings designated-reviewer flows + anonymization.
- `ReviewCycleConfig` (review-specific cycle settings) was NOT needed — Module 4
  adds it one-to-one with PerformanceCycle when cycle-level review config arrives.

### What Modules 4/5/10 need from this
- **Module 4 (Feedback):** assessments live on `ReviewAssessment` — extend with
  anonymization + designated reviewers; reviews expose `.assessments` and the
  state machine remains untouched.
- **Module 5 (Approvals):** replace the body of `state_machine.finalize` with the
  routing engine (entering at APPROVED, completing with the same audited
  FINALIZED write + timeline row). The CHECK constraint keeps holding regardless.
- **Module 10 (Agent 1):** implement `ReviewAssistantProvider` (evidence from
  apps.goals + feedback, PII scrub, LangGraph via the LLM gateway), point
  `settings.REVIEW_ASSISTANT_PROVIDER` at it, and gate the request-ai-draft
  surface with `requires_entitlement("agent1")`. The state machine already locks
  its output PENDING_HUMAN_REVIEW.

---

## Module 4 — 360° Feedback & Anonymisation (build-order M4 = Doc 2 §Module 5)

**Status:** ✅ Complete. **538 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 3's 467 + 71 new). The second AI-safety module: anonymisation-before-
any-LLM and the per-group minimum-volume threshold are the centrepiece, as the
HITL gate was for Module 3. Stack unchanged. ReviewAssessment untouched.

### What was built (`apps/feedback`)
Models (all TenantScopedModel): `FeedbackCycle` (per-subject 360 window,
DRAFT/COLLECTING/CLOSED, optional PerformanceCycle alignment, per-cycle
`min_volume` override), `FeedbackRequest` (the invitation = the
designated-reviewer flow Module 3 deferred here; unique (tenant, cycle, giver);
relationship fixed by the inviter), `Feedback` (giver STORED, never egressed;
360 + cycle-less CONTINUOUS via MySQL NULL-distinct unique semantics; sentiment
null until Module 10), `OneOnOneNote` (participants-only, not anonymised, not
summarised), `FeedbackSummary` (sections NULL until Agent 3 — NEVER fabricated;
status PENDING_HUMAN_REVIEW/HRBP_HOLD/APPROVED/RELEASED; unique per cycle).

### THE ANONYMISATION GUARANTEE (deterministic, proven)
- Anonymisation at the EGRESS boundary, never in storage:
  `anonymize.build_anonymized_payload(cycle)` is the only artifact that leaves
  the sensitive store (recipients, HRBP, and later Agent 3 all consume it). It
  strips giver UUID/name/email and substitutes opaque per-cycle pseudonyms
  (PEER#1…) ordered by feedback-row UUID hex (deterministic, uncorrelated with
  identity or submission time). PROVEN: tests serialize the payload and assert
  ZERO giver identifiers (the analog of Module 3's CHECK-constraint proof) —
  the live demo re-proved it over HTTP. `subject_id` is the single declared
  identifier (recipients know whose 360 it is; SELF is inherently attributed).
- PER-GROUP min-volume: `MIN_FEEDBACK_VOLUME = 3` (constants.py; 5 documented
  as the conservative option; per-cycle override on the model). Applied to PEER
  and UPWARD only (SELF/MANAGER are attributed by nature) and PER GROUP — a
  cycle with 5 responses but 1 peer still excludes the peer group. Excluded
  groups never egress and are recorded in `insufficient_groups` (+
  `insufficient_volume`, the Doc 2 partial-summary-with-warning path).
- DETERMINISTIC pre-LLM breach guard: `scan_for_identity_leaks` scans every
  INCLUDED body for any tenant user's full email and for ANY email-like pattern
  (conservative). Findings (which never carry giver identity) →
  `anonymity_passed=False`, `status=HRBP_HOLD`, provider NEVER called. NOTE:
  Users have no name fields (email-only identity), so name-scanning activates
  if/when profiles gain names — documented in anonymize.py. Agent 3 adds the
  post-LLM check in Module 10.
- CROSS-PEER protection at the serializer: the ONLY serializer that renders a
  Feedback row giver-attributed is the giver's own view; recipients get the
  anonymised payload or giver-less continuous items; summary serializer omits
  reviewed_by; giver/opened_by/reviewed_by are always server-set (anti-spoof).

### Summarize pipeline + Agent-3 seam (Module 10 owns the agent)
`tasks.summarize_feedback(tenant_id, cycle_id, actor_id=None)` — fired by
close_cycle, in the Doc-2 diagram order: bind tenant → anonymised payload
(ALWAYS, before any provider logic) → per-group threshold flags → deterministic
breach guard (breach: HRBP_HOLD + audit, STOP — no provider call, proven by an
exploding fake provider) → sensitive hold (any giver_marked_sensitive →
HRBP_HOLD) → provider seam: `agent3.FeedbackSummarizerProvider` ABC +
NotConfiguredProvider (raises tested FeedbackSummarizerNotConfiguredError) +
`get_provider()` via `settings.FEEDBACK_SUMMARIZER_PROVIDER`. Unconfigured →
log-and-skip, summary stays PENDING with sections NULL, POST /summarize returns
503 "lands in Module 10". A configured provider's sections are stored verbatim
but the summary STAYS pending-human-release (HITL discipline). Idempotent upsert
(unique tenant+cycle). Module 10 gates its surface with
`requires_entitlement("agent3")` (FULL_AI).

### API (mounted at /api/feedback/, all RBAC-gated + audited)
Cycles CRUD + open/close (+/summarize re-trigger), invitations (cycle requests +
requests/mine + decline), give (invitation-authorised, giver server-set),
continuous, mine/received (received is giver-less), the subject's anonymised
view (CLOSED only) + released summary (403 SUMMARY_NOT_RELEASED until released),
HRBP review queue + approve (HRBP_HOLD/PENDING → RELEASED), 1:1 notes
(participants ONLY — even Admin is denied via API). Audits:
feedback_cycle.opened/closed, feedback_request.sent, feedback.submitted,
summary.generated, summary.held_for_hrbp, summary.approved, summary.released —
all BEFORE the effect.

### Slack "notify reviewers" seam (Module 12)
The PENDING FeedbackRequest row IS the in-app notification for MVP; Module 12
pushes it to Slack (documented on send_feedback_request).

### RBAC additions (matrix + oracle test)
`manage_feedback_cycle` (Manager+), `give_feedback`, `view_own_feedback_summary`,
`manage_one_on_one` (everyone), `approve_feedback_summary` (HRBP/Admin).

### Files
New: `apps/feedback/` (constants, exceptions, models, anonymize, services,
agent3, tasks, serializers, views, urls, migration 0001, tests test_anonymize/
test_services/test_agent3_seam/test_api — 51 tests). Changed: settings
LOCAL_APPS, config/urls, rbac matrix + oracle, testsupport factories.

### Live validation (via nginx)
create+open+invite 201s → 6 submissions 201 → spoof re-give 403 → close 200
(summarize reason=no_provider) → POST /summarize 503 "lands in Module 10" →
subject GET /anonymized: giver_identifiers_found=[], pseudonyms PEER#1–3,
UPWARD (1 < 3) excluded + flagged insufficient → subject summary 403 until HRBP
approve → RELEASED (sections null — never fabricated) → breach cycle (peer body
contained a colleague's email) → HRBP_HOLD, anonymity_passed=False → peer GET
/anonymized 403 → Globex admin GET 404.

### Known risks / notes
- **Breach guard scans emails only** (Users have no name fields). Free-text
  names ("ask Priya about this") are NOT deterministically detectable today;
  Agent 3's post-LLM semantic check (Module 10) is the second net. If profiles
  gain names, extend `scan_for_identity_leaks` immediately.
- **Pseudonym stability:** pseudonyms are stable per cycle (UUID-hex order). A
  giver who edits their item keeps the same pseudonym; across cycles pseudonyms
  do not correlate.
- **A held (breach/sensitive) summary is released by HRBP approval without
  body redaction** — the HRBP is the human judging the leak; redaction tooling
  could come with the Module-10 console.
- **Continuous feedback is recipient-visible immediately** and giver-less; it
  bypasses the 360 threshold by design (it is direct, not anonymous-aggregated).
- The (tenant, cycle, giver) unique constraint relies on MySQL NULL-distinct
  semantics for continuous rows — documented on the model; revisit if the DB
  ever changes (it won't; stack is locked).

### What Modules 5/10/12 need from this
- **Module 5 (Approvals):** the HRBP summary approve is a single step; the
  routing matrix can generalise `services.approve_summary` the same way it
  replaces Module 3's finalize.
- **Module 10 (Agent 3):** implement `FeedbackSummarizerProvider` (consumes the
  anonymised payload ONLY), set `settings.FEEDBACK_SUMMARIZER_PROVIDER`, gate
  with `requires_entitlement("agent3")`, add the post-LLM breach check + the
  Fast-AI sentiment tagger (Feedback.sentiment is waiting). Agent 1 (reviews)
  may now also consume `build_anonymized_payload` as feedback evidence.
- **Module 12 (Slack):** push FeedbackRequest invitations + summary-released
  notifications; the audit trail and request rows are already in place.

---

## Module 5 — Approval Workflows (build-order M5 = Doc 2 §Module 6)

**Status:** ✅ Complete. **599 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 4's 538 + 61 new; the 538 stayed green — Module 3 untouched). DELIBERATELY
AI-FREE (the spec requires deterministic, auditable approvals). Stack unchanged.

### What was built (`apps/approvals`)
TEMPLATE: `ApprovalWorkflow` (name, artifact_type, mode SEQUENTIAL/PARALLEL,
active — at most one active per (tenant, artifact_type)) + `ApprovalStep` (order,
approver_kind ROLE/NAMED, approver_role MANAGER/HRBP/ADMIN, approver_user,
required, timeout_hours, escalation_role/user). RUNNING INSTANCE: `ApprovalRoute`
(workflow, artifact_type, artifact_id, mode, status, initiated_by) + 
`ApprovalStepInstance` (the decision slot — resolved approver / role-slot, status,
due_at, decided_by/at, comment, escalation snapshot, escalated). All TenantScoped.
Instances are snapshotted at start, so editing a template never mutates an
in-flight route.

### Engine contract (`engine.py`, deterministic, tenant-bound, audited)
- `start_route` resolves the active workflow, checks no route is already in flight
  for the artifact (one active route per artifact, 409), resolves EVERY step
  (raising 422 ROUTE_APPROVER_UNRESOLVABLE before writing any row), and creates the
  route + instances. SEQUENTIAL: only order-1 is active (lowest-order PENDING is
  computed, not stored) and its clock starts; the rest wait. PARALLEL: all PENDING
  with clocks at once.
- `record_decision` — actor must be the assigned approver (NAMED/MANAGER) or an
  in-scope holder of the role-slot (HRBP/ADMIN, tenant-wide); cross-tenant and the
  protected subject are 403. Out-of-order / already-decided / route-not-in-progress
  are 409 (never a silent no-op). Audits BEFORE the effect (crash-injection
  proven). SEQUENTIAL: approve activates the next step; last approval → APPROVED →
  `on_route_complete`. PARALLEL: APPROVED when every REQUIRED step is approved
  (non-required are advisory). REJECT anywhere → REJECTED → `on_route_rejected`.
- Approver RESOLUTION: ROLE=MANAGER → the subject's direct manager (specific
  user); ROLE=HRBP/ADMIN → a role-slot (any in-scope holder acts, first owns it);
  NAMED → the user. SELF-APPROVAL BLOCK: a step resolving to a protected user is
  reassigned to the escalation target (escalation_user → escalation_role → ADMIN
  slot fallback, so it is always resolvable).
- `escalate_step` reassigns an overdue PENDING step in place to its escalation
  target (escalated=True, new due_at, audits `step.escalated`).

### Escalation (Celery beat)
`tasks.escalate_overdue_routes()` scans `engine.overdue_pending_steps()`
cross-tenant (off-request, system escape), escalates each within its own tenant
context (one failure logged, sweep continues), returns
`{scanned, escalated, errors}`. Registered in `CELERY_BEAT_SCHEDULE`
(`APPROVALS_ESCALATION_INTERVAL_SECONDS`, default 300s) on the existing
celery-beat service.

### Registry + the review finalize seam (filled OPT-IN, Module 3 intact)
`registry.py` keeps the engine generic: an artifact type registers
`resolve_context` (subject, the subject's manager, `protected_user_ids`),
`on_route_complete`, `on_route_rejected`. Dependency is one-way (consumers →
approvals; the engine never imports a consumer). `apps.reviews` registers "review"
in `ReviewsConfig.ready()`:
- `review.finalize` now: HITL gate first (still 422 without an approver); THEN if
  the tenant has an ACTIVE "review" workflow it ENTERS the route (review stays
  APPROVED + gains a nullable `approval_route` link) instead of finalising; with NO
  active workflow it is single-step EXACTLY as Module 3.
- `on_route_complete` → `state_machine._finalize_apply` (the EXISTING audited
  APPROVED→FINALIZED path; the Module-3 CHECK constraint still governs).
- `on_route_rejected` → a new additive `route_rejected` transition (APPROVED→EDITING)
  returns the review to its author; a re-submission starts a FRESH route.
- The Module-3 state machine was NOT rewritten and NO review state was added: the
  only changes are a nullable FK, one additive transition edge, and finalize
  branching. All 538 prior tests stayed green.

SELF-APPROVAL DESIGN NOTE (reconciling the rule with the Manager→HRBP demo): for a
review the protected set is `{subject}` (the employee being reviewed) — NOT the
authoring manager. A review's author IS the subject's manager, so protecting the
manager would make a "Manager" approval step always self-collide and defeat the
canonical Manager→HRBP matrix. The manager already human-approved the content in
Module 3; the route is the additional org sign-off, so the manager is a legitimate
approver and only the subject is barred from approving their own review.

### Module-5-fills-Module-3 / future routing
`finalize` is now multi-step via the engine for reviews; the SAME pattern fills
JD (Module 6) and record-amendments — register the artifact type + wire its
finalise/return callbacks. ROUTE.ESCALATED status is reserved for a no-target
dead-end (the ADMIN-slot fallback means it does not occur in a tenant with an
admin).

### RBAC additions (matrix + oracle)
`configure_approval_workflow` (Admin/HRBP), `act_on_approval_step` (Manager+; the
engine enforces assignment on top), `view_approval_status` (all).

### API (mounted at /api/approvals/, RBAC-gated + audited)
Workflow CRUD + activate/deactivate (the designer backend), the approver `inbox`
(SEQUENTIAL surfaces only the active step), route `tracker`
(`/routes/<id>` and `/routes?artifact_type=&artifact_id=`, visible to
initiator/approver/config-holder), and `steps/<id>/approve|reject` → the engine.
Audits route.started / step.approved / step.rejected / route.completed /
route.rejected / step.escalated / workflow.activated/deactivated /
review.finalize_routed / review.route_rejected — all BEFORE the effect.

### Files
New: `apps/approvals/` (models, exceptions, registry, engine, tasks, serializers,
views, urls, migration 0001, tests conftest/test_engine/test_escalation/test_api —
44 tests). Changed: `apps/reviews/` (models +approval_route FK, migration 0002,
state_machine finalize/_finalize_apply/route_rejected, apps.ready, new
approval_integration.py, test_routing_integration.py — 5 tests), rbac matrix +
oracle, settings (LOCAL_APPS + CELERY_BEAT_SCHEDULE), config/urls, testsupport
factories.

### Live validation (via nginx)
Admin configures SEQ Manager→HRBP (employee config → 403); a review reaches
APPROVED and finalize ROUTES (stays APPROVED, route IN_PROGRESS); out-of-order
step-2 → 409; manager inbox shows step 1 only, HRBP inbox empty until step-1
approved; manager→HRBP approve → review FINALIZED; a step-1 REJECT → review back to
EDITING (not finalised); peer-manager decide → 403, cross-tenant route GET → 404;
a PARALLEL both-required approve → FINALIZED; a forced-overdue step → the beat task
escalates it to the HRBP slot, audited; a tenant with NO workflow single-step
finalises (Module-3 behaviour).

### Known risks / notes
- **At-most-one-active and one-active-route-per-artifact are enforced in code**
  (MySQL has no partial unique indexes), with an index to back the lookups.
- **Escalation reassigns in place** (not a new slot); `escalated` + the
  `step.escalated` audit record the history. ROUTE/STEP ESCALATED statuses are
  reserved for the no-escalation-target dead-end (unreachable with the ADMIN
  fallback).
- **Step-template edits after creation** aren't exposed via PATCH (workflow
  name/mode/active only) — re-create the workflow to change steps; in-flight routes
  are unaffected (snapshotted).
- **Notifications are in-app** (the inbox / tracker); Slack push is Module 12.
- **Resolution snapshots managers at start** — a later manager change does not
  re-resolve an in-flight route (deterministic by design).

### What Modules 6/7/10/12 need from this
- **Module 6/7 (JD, record-amendments):** register the artifact type with the
  registry (resolve_context + on_route_complete + on_route_rejected) and add an
  active workflow; the engine + API + escalation work unchanged.
- **Module 10 (Fast-AI hints):** "suggested next approver" / "looks like a prior
  approved item" attach to the inbox/route surfaces — read-only, advisory; the
  engine stays deterministic.
- **Module 12 (Slack):** push inbox assignments + escalations; the audit trail and
  step instances are already in place.


## Module 6 — JD Library & AI JD Generator (build-order M6 = Doc 2 §Module 7)

**Status:** ✅ Complete. **657 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 5's 599 + 58 new; the 599 stayed green — nothing prior was rewritten).
JD is the FIRST NEW CONSUMER of the Module-5 approval engine — registering "jd"
proves the engine is generic. NO LLM / LangGraph / actual generator (loud seam
only; the generator lands in Module 10). Stack unchanged.

### What was built (`apps/jd`)
- `JobDescription` — the stable library entry. `status` (DRAFT /
  PENDING_HUMAN_REVIEW / IN_REVIEW / PUBLISHED / ARCHIVED) tracks the WORKING
  version's lifecycle; `current_version` FK points at the live PUBLISHED version
  (null until first publish). `source` MANUAL/AI, `created_by`, nullable
  `approval_route` (opt-in routing). Indexes ix_jd_status, ix_jd_title_level.
- `JDVersion` — an immutable-once-published body `{summary, responsibilities[],
  must_haves[], nice_to_haves[]}` + `inputs_snapshot`, nullable
  `confidence_score`/`citations` (generator-only), `is_published`. Unique
  (tenant, jd, version_number).
- `JDTemplate` — deterministic role-family scaffolds (Engineering ×2, Sales,
  People), seeded idempotently per tenant + instantiated into a DRAFT JD.
- `JDRequest` — a Manager's OPEN→FULFILLED/DECLINED ask that HRBP author a JD.
All TenantScoped (UUID pk, tenant FK).

### Lifecycle (`lifecycle.py`, hand-rolled, guarded, audited, tenant-bound)
`create_jd` → DRAFT + v1. `save_draft` edits the working version (DRAFT/PENDING;
never a published version). `submit_for_review` DRAFT→PENDING_HUMAN_REVIEW,
validating title+level + body summary/responsibilities/must_haves first (422
INVALID_JD_INPUT). `approve` (THE HITL human gate) PENDING→ either ENTERS a route
(active "jd" workflow → IN_REVIEW + `approval_route` link) or single-step
PUBLISHES. `_publish` marks the working version `is_published=True`, sets
`current_version`, status PUBLISHED. `route_rejected` IN_REVIEW→PENDING (engine
callback). `revise` PUBLISHED→a NEW DRAFT version (copies the published body;
`current_version` stays live + immutable so the library never loses content
mid-revision). `archive` →ARCHIVED. Illegal transitions → 409
ILLEGAL_JD_TRANSITION. Every entry binds the tenant (off-request safe) and audits
BEFORE the effect (jd.created/drafted/submitted/approved/routed/published/
route_rejected/archived).

### "jd" approval registration (`approval_integration.py`) — engine is generic
Registered in `JdConfig.ready()`. `resolve_context` returns
`protected_user_ids={created_by}` (the author can never approve their own JD's
route) and `subject=None, manager=None`. `on_route_complete` → `_publish`;
`on_route_rejected` → `route_rejected`. Routing is OPT-IN exactly like reviews:
no active workflow → single-step publish; an active "jd" workflow → route.
NOTE: because a JD has no employee subject, a ROLE=MANAGER step has no manager to
resolve to and falls back to the engine's universal ADMIN slot (escalated) — it
is NOT unresolvable. The genuine 422 ROUTE_APPROVER_UNRESOLVABLE path is an
unrecognised approver config (a ROLE that is neither MANAGER nor an HRBP/ADMIN
slot); both are tested. JD workflows should use ROLE=HRBP/ADMIN or NAMED.

### JD-Generator SEAM (`generator.py` + `tasks.py`) — Module 10 owns the LLM
`JDGeneratorProvider` ABC + `NotConfiguredProvider` (raises
`JDGeneratorNotConfiguredError`) + `get_provider()` resolving
`settings.JD_GENERATOR_PROVIDER` (import string; defaults to NotConfigured).
`tasks.generate_jd(tenant_id, jd_id, actor_id)` — (a) binds the tenant, (b)
VALIDATES generation inputs (title+level+non-empty inputs snapshot) BEFORE any
provider call → 422 INVALID_JD_INPUT, (c) no provider → returns
`{"generated": False, "reason": "no_provider"}` and leaves the JD UNTOUCHED (the
endpoint surfaces a loud 503; NEVER fabricates a body). A configured provider's
body is written (source=AI) and locked PENDING_HUMAN_REVIEW via the lifecycle —
a generated JD is never published directly. Same shape as the Module-3 Agent-1
seam and the Module-2 Jira seam.

### Services (`services.py`)
Template seed (`seed_templates_for_tenant`, idempotent) + `instantiate_template`
(deep-copies the scaffold via `create_jd`). `visible_jds` / `search_jds` apply
the §2 scope rule (managers+ see the whole library; everyone else PUBLISHED
only — non-managers 404 on a draft, never a 403 that leaks existence).
`render_jd_text` + `jd_export` (plain text + structured JSON; NO binary
PDF/docx — Module 14). JD-request services `create_jd_request` /
`fulfil_jd_request` (409 if not OPEN) / `decline_jd_request` /
`visible_jd_requests` (Manager sees own; HRBP/Admin all). Management command
`seed_jd_templates --tenant-slug`.

### RBAC additions (matrix + oracle)
`generate_jd` / `manage_jd_library` ALREADY existed (HRBP+) from Module 1 — reused
(library write + lifecycle + templates + request fulfil/decline ride on
`manage_jd_library`). NEW: `request_jd` (Manager+), `view_jd_library` (everyone;
WithinScope restricts non-managers to PUBLISHED). Oracle table extended.

### API (mounted at /api/jd/, RBAC-gated + audited; views are the SOLE RBAC gate)
JD CRUD (`GET/POST /`), detail/`versions`/`export` (VIEW_JD_LIBRARY, scoped via
`visible_jds`), lifecycle transitions `save-draft|submit|approve|revise|archive`
(MANAGE_JD_LIBRARY), `generate` (GENERATE_JD; 503 seam / 422 inputs / 409 / 200),
`templates` + `templates/<id>/instantiate` (MANAGE_JD_LIBRARY), `requests`
(GET/POST, REQUEST_JD) + `requests/<id>/fulfil|decline` (MANAGE_JD_LIBRARY).
Thin views; lifecycle/services are the only mutators; NO PATCH/PUT.
created_by/requested_by/tenant always server-set.

### Files
New: `apps/jd/` (models, exceptions, lifecycle, approval_integration, generator,
tasks, services, serializers, views, urls, apps, migration 0001,
management/commands/seed_jd_templates, tests test_lifecycle/test_routing/
test_generator_seam/test_services/test_api — 53 tests). Changed: rbac matrix +
oracle (2 new caps), settings (LOCAL_APPS + JD_GENERATOR_PROVIDER), config/urls,
testsupport factories (JobDescription/JDVersion/JDTemplate/JDRequest).

### Live validation (via nginx)
HRBP manual flow create→save-draft→submit→approve→PUBLISHED; employee reads the
published JD + versions + export, but 404s on a draft (manager sees it); the
generator seam → 503 with the JD left DRAFT (never fabricated); employee/manager
create → 403, employee generate → 403; a Manager JD-request → HRBP fulfil → 409
on re-fulfil; templates seeded + instantiated; an ACTIVE "jd" workflow makes
approve ENTER the route (IN_REVIEW), the author's own step-decision → 403
self-approval block, a second HRBP approves → route APPROVED → JD PUBLISHED;
cross-tenant JD GET → 404.

### Known risks / notes
- **Working version vs current_version:** `status` follows the latest (working)
  version; `current_version` is the live published one. Revising a published JD
  opens a new draft while the published version stays live + frozen.
- **MANAGER steps on a JD** silently resolve to the ADMIN slot (no subject →
  engine's universal fallback), not a 422 — document HRBP/ADMIN/NAMED as the
  recommended JD-workflow approvers.
- **Export is text + JSON only**; binary PDF/docx is Module 14.
- **No `jd_generator` billing entitlement yet** — added in Module 10 with the real
  generator (kept out of billing now per scope).

### What Modules 7/10/14 need from this
- **Module 7 (Org Chart) / later:** the JD library + published versions are queryable
  per tenant; link roles → published JDs as needed.
- **Module 10 (real generator):** implement `JDGeneratorProvider.generate` (LangGraph
  + LLMGateway, PII-safe, confidence + citations), point `JD_GENERATOR_PROVIDER` at
  it, and gate the endpoint with the `jd_generator` entitlement. The seam, the
  HITL lock, and `source=AI` are already wired — no lifecycle change needed.
- **Module 14 (export):** a binary renderer plugs into `services.jd_export` (already
  returns rendered text + structured body).


## Module 7 — Live Org Chart (build-order M7 = Doc 2 §Module 8)

**Status:** ✅ Complete. **712 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 6's 657 + 55 new; the 657 stayed green — nothing prior was rewritten).
AI-FREE (the "who reports to X" NL lookup is the Module-10 Chat Assistant;
span-of-control insight is Phase 2 — NEITHER built, no agent seam). A DATA API,
not a UI — the canvas is Module 13. Stack unchanged. This is the first
substantial use of the Phase-1.5a cache framework beyond billing.

### Design — reads from `User.manager`, `Position` only for vacancies
The reporting hierarchy is READ from the live identity graph (`User.manager`, the
self-FK that has powered RBAC scope + approver resolution since Module 1) — NOT
duplicated. Module 7 adds exactly ONE model — `Position` (an approved headcount
slot / vacancy unit: title, reports_to→User, department, status OPEN/FILLED/
CLOSED, filled_by→User, published_jd→jd.JobDescription, opened_at, filled_at,
created_by) — and ONE explicit tree mutation (cycle-checked reassignment of
`User.manager`). Positions model the approved plan / vacancies, NOT the roster —
there is no Position per employee.

### Org tree + rollups (`services.py`), computed live + cached
`build_org_tree(actor)` returns `{nodes, edges, roots}` from active users only
(the scoped manager hides soft-deleted; `is_active=True` is filtered explicitly —
deactivated users never appear in the tree or rollups). Per node: `headcount` =
active users in the subtree (inclusive, transitive); `vacancies` = OPEN positions
whose `reports_to` is anywhere in the subtree. Rollups are a post-order DFS with a
cycle guard. The EXPENSIVE full-tenant tree+rollups is cached once per tenant
under `tenant:<id>:org:tree` (TTL 600s) via `tenant_cache_key`; per-actor SCOPE
filtering is then a PURE in-memory pass over the cached structure — so one cache
entry serves every scope without a per-manager key explosion (a second `/tree`
read issues 0 DB queries; proven by `django_assert_num_queries(0)`).

### Scope (mirrors `apps.rbac.scope`; person-card/search/export bounded the same)
- Employee (OWN)    → own node + ancestor chain to the root (their reporting line).
- Manager  (TEAM)   → own `reporting_subtree_ids` + self + ancestor chain.
- HRBP/Admin(TENANT)→ the full tenant tree (multiple roots: users with manager=null).
`person_card`/`search_people`/`export_org`/`list_vacancies` apply the same tier; an
out-of-scope (or inactive / cross-tenant) target is a 404, never a 403 that leaks
existence (the Module-6 rule). `User` carries only email/role, so a person's
"title" comes from a FILLED Position; search matches email OR filled-position title.

### Writes (HRBP/Admin) — guarded, audited BEFORE the effect, cache-invalidating
- Positions (`positions.py`): `create_position` (OPEN; reports_to must be active +
  in-tenant), `fill_position` (→ FILLED + filled_at; filling a FILLED one → 409
  POSITION_ALREADY_FILLED, a CLOSED one → 409 ILLEGAL_POSITION_TRANSITION),
  `close_position` (OPEN/FILLED → CLOSED, clears the vacancy; CLOSED again → 409),
  `link_jd`/`unlink_jd` (a linked JD must be PUBLISHED + in-tenant else 422
  INVALID_ORG_INPUT). EVERY position write invalidates the org cache — including
  create (a regression the live demo caught: `/vacancies` reads live so it was
  right, but the cached tree's vacancy rollup was stale until create also
  invalidated).
- `reassign.py::reassign_reporting_line(actor, user, new_manager)` — the ONLY place
  Module 7 mutates the tree. CYCLE DETECTION: new_manager must not be the user, nor
  anyone in the user's own `reporting_subtree_ids` (the transitive case — moving a
  grandparent under a grandchild → 422 REPORTING_CYCLE). new_manager must be active
  + in-tenant. Audits before; invalidates the org cache. RBAC scope is computed live
  from `User.manager`, so clearing the `org` cache namespace is sufficient (no
  separate scope cache exists). Does NOT touch positions.

Audit actions: position.created/filled/closed/jd_linked/jd_unlinked,
reporting_line.reassigned. Cache-invalidation triggers: any position
create/fill/close/link/unlink and any reassignment.

### RBAC additions (matrix + oracle)
`view_org_chart` (everyone; the services scope the rows OWN/TEAM/TENANT),
`manage_positions` (HRBP/Admin — vacancies + JD link), `reassign_reporting_line`
(HRBP/Admin). Oracle table extended.

### API (apps/org, mounted at /api/org/, RBAC-gated + audited; views are the SOLE RBAC gate)
Reads (view_org_chart, scope-filtered by the services): GET `/tree`, `/people/<id>`
(404 out-of-scope), `/search?q=`, `/export`, `/vacancies`. Position management
(manage_positions): GET/POST `/positions`, GET `/positions/<id>`, POST
`/positions/<id>/fill|close|link-jd|unlink-jd`. Reassignment
(reassign_reporting_line): POST `/reassign`. Thin views; services/positions/reassign
are the sole mutators; no blind PATCH of `User.manager`. actor/tenant server-set.

### Files
New: `apps/org/` (models, exceptions, services, positions, reassign, serializers,
views, urls, apps, migration 0001, tests test_services [25] + test_api [18]).
Changed: rbac matrix + oracle (3 new caps), settings (LOCAL_APPS), config/urls,
testsupport factories (PositionFactory).

### Live validation (via nginx)
HRBP `/tree` → 7-node tenant tree (hrbp headcount 7); an employee sees only their
line {self, manager, hrbp}; a manager sees their subtree; HRBP creates an OPEN
position under a manager → `/vacancies` shows it and the cached tree's vacancy
rollup updates; fill → vacancy clears, fill again → 409; reassign an employee to a
new manager → both subtree headcounts update on the next read (cache invalidation
proven); a transitive cycle + a self-reassign → 422 REPORTING_CYCLE; an employee
drilling into an out-of-scope person → 404; scoped search; `/export` → scoped tree
JSON; employee create-position / reassign → 403; cross-tenant person + position →
404.

### Known risks / notes
- **Tree is read live from `User.manager`** — Module 7 never forks the hierarchy;
  positions are a separate plan/vacancy layer (no auto-rewiring of `User.manager`
  from positions, per scope).
- **Cache is per-tenant (full tree), scope-filtered in memory** — avoids a
  per-manager key explosion; every write clears the `org` namespace so reads are
  never stale (create-position included).
- **Rollup DFS recurses by tree depth** with a cycle guard; org depth far below
  Python's recursion limit. Real cycles are prevented at the reassign boundary.
- **`reports_to`/`filled_by` are SET_NULL** so soft-deleting a user never blocks; a
  null-`reports_to` OPEN position is a tenant-level vacancy visible only to
  HRBP/Admin.
- **Export is text/JSON only** (no binary); **no BusinessUnit model** yet, so HRBP
  scope = tenant-wide (the Module-1 simplification).

### What Modules 8/10/13 need from this
- **Module 8 (Succession):** the live tree + `reporting_subtree_ids` + person cards
  give the report tier per manager; critical-role registry can reference Positions.
- **Module 10 (Chat Assistant):** the "who reports to X" NL lookup reads the SAME
  scoped `build_org_tree` / `person_card` / `search_people` services — permission-
  bound by construction; span-of-control flags (Phase 2) attach as advisory reads.
- **Module 13 (frontend canvas):** renders `GET /tree` (nodes+edges+roots+rollups),
  `/people/<id>`, `/vacancies`, `/search`, `/export`; all already scoped + cached.


## Module 8 — Succession & Talent (build-order M8 = Doc 2 §Module 9)

**Status:** ✅ Complete. **792 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 7's 712 + 80 new; the 712 stayed green — nothing prior was rewritten).
Holds the MOST SENSITIVE data in the system (readiness, 9-box, flight-risk) —
MANAGEMENT-ONLY by construction. The deterministic engine is CORE (works with no
AI); Agent 4 (Module 10) only ENRICHES via a loud seam. Stack unchanged.

### THE SENSITIVITY RULE (the headline)
Succession is invisible to employees: there is NO employee access to ANY endpoint
— not even their own 9-box or readiness. An EMPLOYEE hitting any succession
endpoint gets **404, not 403** (no existence leak). Enforced by
`apps/succession/permissions.py::SuccessionMixin`, which orders
`[IsAuthenticated, SuccessionParticipant, HasCapability]` — `SuccessionParticipant`
raises `NotFound` for any non-management role BEFORE the capability check could
403. EVERY view subclasses `SuccessionMixin`. A Manager is confined to their
reporting subtree (out-of-tier target → 404, raised in the services); a Manager
lacking an HRBP-only capability (critical-role registry / generate / publish) gets
the normal 403 (they're a participant); cross-tenant → 404.

### Models (`apps/succession/models.py`, all TenantScoped)
`CriticalRole` (name, optional `position`→org.Position, `incumbent`→User,
criticality HIGH/CRITICAL, knowledge_risk LOW/MEDIUM/HIGH, risk_notes, marked_by,
status ACTIVE/ARCHIVED). `BenchCandidate` (critical_role, candidate, readiness
READY_NOW/READY_SOON/DEVELOPING/NOT_READY, `readiness_overridden`, notes, added_by;
unique tenant+role+candidate). `NineBoxPlacement` (employee, cycle, performance_band
DERIVED, potential_band HUMAN-assigned, box 1–9, assessed_by/at; unique
tenant+employee+cycle). `SuccessionPlan` (critical_role, status DRAFT/
PENDING_HUMAN_REVIEW/PUBLISHED, ranked_bench JSON, coverage_status RED/AMBER/GREEN,
red_flags JSON, action_items JSON, source DETERMINISTIC/AI, confidence_score
nullable, generated_at, reviewed_by, published_at).

### Deterministic engine (`engine.py` + `constants.py`, all tunable)
- **Performance band from the Module-2 CycleScore T-score:** `t < 40 → LOW`;
  `40 ≤ t ≤ 60 → MEDIUM`; `t > 60 → HIGH` (tested 39→LOW, 50→MEDIUM, 70→HIGH). No
  CycleScore → performance UNKNOWN → readiness NOT_READY (never a crash).
- **9-box numbering:** `box = perf_index*3 + pot_index + 1` (LOW=0/MED=1/HIGH=2),
  so LOW/LOW=1 … HIGH/HIGH=9 (top-talent). Unique per (employee, cycle), upserts.
- **Readiness default mapping** (HRBP may OVERRIDE — `readiness_overridden` STICKS,
  a re-generate never recomputes it): LOW/UNKNOWN perf → NOT_READY; HIGH+HIGH →
  READY_NOW; (HIGH|MED) perf + (MED|HIGH) potential → READY_SOON; MED perf +
  (LOW|MED) → DEVELOPING; HIGH+LOW → DEVELOPING. Missing potential treated as LOW
  (conservative — unassessed potential never inflates readiness).
- **Coverage per critical role:** any READY_NOW → GREEN; else any READY_SOON →
  AMBER; else RED (the spec's inadequate-coverage flag; empty bench is RED). RED
  populates `red_flags`.
- `compute_analysis(role)` recomputes non-overridden readiness, ranks the bench (by
  readiness then performance), and returns ranked_bench + coverage + red_flags —
  deterministic, always available, ungated beyond RBAC.

### SuccessionPlan HITL (`plans.py`)
`generate_plan` → a NEW plan locked PENDING_HUMAN_REVIEW (source=DETERMINISTIC) →
HRBP `add_action_item` during review → `publish_plan` → PUBLISHED (to the
dashboard, sets reviewed_by + published_at). A plan that has NOT been through
PENDING_HUMAN_REVIEW cannot be published — illegal transition → 409
ILLEGAL_PLAN_TRANSITION. The scoped `dashboard(actor)` shows each visible role with
its latest published coverage. All audited before the effect.

### Agent-4 enrichment SEAM (`agent4.py` + `tasks.py`) — Module 10 owns the agent
`SuccessionAnalyzerProvider` ABC + `NotConfiguredProvider` (raises
`SuccessionAnalyzerNotConfiguredError`) + `get_provider()` resolving
`settings.SUCCESSION_ANALYZER_PROVIDER`. `enrich_succession_with_agent4(tenant_id,
plan_id, actor_id)` binds the tenant, resolves the provider; with NONE configured
it logs-and-skips → `{"enriched": False, "reason": "no_provider"}` and the endpoint
surfaces a loud 503. THE KEY DIFFERENCE from prior seams: the deterministic plan
stays COMPLETELY INTACT (the baseline is core, not faked — proven in tests + the
live demo). A configured Module-10 provider reads internal CycleScores/goals +
ANONYMISED Module-4 360 (never raw givers), producing a NEW plan (source=AI) locked
PENDING_HUMAN_REVIEW with a confidence score for HRBP re-review; its surface will
be gated with `requires_entitlement("agent4")`.

### RBAC additions (matrix + oracle) — management-only, NO employee anywhere
`manage_critical_roles` (HRBP/Admin), `manage_bench` (Manager+, own-tier),
`assess_nine_box` (Manager+, own-tier), `view_succession` (Manager+, own report
tier ONLY), `generate_succession_analysis` (HRBP/Admin), `publish_succession_plan`
(HRBP/Admin). Employees hold NONE — and `SuccessionParticipant` turns any employee
access into 404. Manager-held caps are additionally scoped in the services.

### API (apps/succession, mounted at /api/succession/, RBAC-gated + audited)
dashboard (view_succession); critical-roles CRUD + knowledge-risk + archive
(manage_critical_roles); bench list/add (view/manage_bench, scoped) + readiness
(manage_bench); nine-box list/assess (view/assess_nine_box, scoped); generate
(generate_succession_analysis); plan detail/action-item/publish
(view/publish_succession_plan); enrich (the 503 seam). Thin views; services/plans/
tasks are the sole mutators + scope authority; no PATCH/PUT. Audits
critical_role.marked/risk_updated/archived, bench.added, readiness.set,
ninebox.assessed, plan.generated/action_item_added/published — all before the effect.

### Files
New: `apps/succession/` (models, constants, engine, exceptions, services, plans,
agent4, tasks, permissions, serializers, views, urls, apps, migration 0001, tests
test_engine [25] + test_services [20] + test_api [11]). Changed: rbac matrix +
oracle (6 new caps), settings (LOCAL_APPS + SUCCESSION_ANALYZER_PROVIDER),
config/urls, testsupport factories (CriticalRole/BenchCandidate/NineBoxPlacement/
SuccessionPlan).

### Live validation (via nginx)
HRBP marks "VP Engineering" CRITICAL (knowledge_risk HIGH); assigns 9-box (alice
perf HIGH→box 9, bob perf MED→box 5, performance pulled from CycleScores); adds 3
bench candidates (readiness seeded READY_NOW/READY_SOON/DEVELOPING); generates →
PENDING_HUMAN_REVIEW, ranked alice>bob>eve, coverage GREEN; a second "Lead DBA"
role with a scoreless candidate → coverage RED + INADEQUATE_COVERAGE red flag; HRBP
adds an action item → publishes → dashboard shows it; a Manager assesses their own
report's 9-box but a peer's report → 404 and their dashboard is tier-scoped; an
EMPLOYEE → 404 on dashboard / critical-roles / their OWN 9-box / create; a Manager
lacking the HRBP cap → 403 (not 404); enrich-with-agent4 → 503 with the
deterministic plan verified unchanged; cross-tenant role + plan → 404.

### Known risks / notes
- **Management-only is enforced at two layers:** capabilities exclude employees,
  AND `SuccessionParticipant` 404s them first (so even a capability mistake can't
  turn into a 403 existence-leak). Out-of-tier/cross-tenant → 404 in the services.
- **Deterministic baseline is core, never faked** — the Agent-4 no-provider path
  leaves the published plan completely intact (unlike the review/JD seams where the
  artifact had no content without AI).
- **HRBP readiness override sticks** (`readiness_overridden=True`); a re-generate
  recomputes only non-overridden candidates.
- **Performance is read-only from Module-2 CycleScore**; no CycleScore → UNKNOWN →
  NOT_READY. 9-box performance for an unscored cycle falls back to the latest score
  then LOW. Raw Module-4 360 is NOT pulled into the deterministic path (anonymised
  themes feed Agent 4 only, Module 10).
- **No `agent4` billing entitlement yet** — added in Module 10 with the real agent.

### What Modules 9/10/13 need from this
- **Module 9 (Career Roadmap LITE):** readiness + 9-box + the gap to a critical role
  feed the development path; the bench/plan models are queryable per tenant.
- **Module 10 (Agent 4 + Chat):** implement `SuccessionAnalyzerProvider.analyze`
  (LangGraph + LLMGateway over internal CycleScores/goals + ANONYMISED 360, schema-
  validated weights, confidence), point `SUCCESSION_ANALYZER_PROVIDER` at it, gate
  with `requires_entitlement("agent4")`. The seam, the new-AI-plan PENDING lock, and
  `source=AI` are wired. The Fast "who is ready now for role X" lookup reads the
  deterministic readiness/dashboard services (permission-bound) — no new store.
- **Module 13 (dashboard UI):** renders `GET /dashboard`, `/critical-roles`,
  `/plans/<id>`, `/nine-box`, all already scoped + management-gated (employees 404).


## Module 9 — Career Development (Roadmap LITE) (build-order M9 = Doc 2 §Module 10)

**Status:** ✅ Complete. **850 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 8's 792 + 46 new career tests + 12 matrix-oracle params for the 3 new
capabilities; the 792 stayed green — nothing prior was rewritten). Advisory-only,
NEVER auto-promotion. Reuses the Module-8 readiness band-math + Module-2 attainment
WITHOUT exposing succession's sensitive surface to the viewer. AI-free (the LLM
roadmap drafting is the Module-10 seam). Stack unchanged.

### THE DATA BOUNDARY (the headline safety property)
Career reuses the readiness COMPUTATION only — it must NEVER surface the
management-only succession surface (bench / 9-box potential / coverage / other
employees). Enforced structurally:
- The engine (`engine.py`) reads ONLY the subject employee's OWN performance data:
  their `CycleScore` (via the Module-8 `performance_band_from_tscore` band math —
  literally `from apps.succession.engine import performance_band_for`) and their
  `Goal`/`Kpi` attainment (via the Module-2 `goal_raw_score`). It does NOT read
  `BenchCandidate` / `CriticalRole` / `SuccessionPlan` / `NineBoxPlacement`.
- The career response vocabulary is kept LITERALLY free of succession terms: the
  advisory tier copy says "preparedness"/"growth", never "readiness"/"potential",
  so "a career response can never contain a succession token" is a trivially
  auditable invariant (the same spirit as Module 4's "zero giver identifiers").
- PROVEN three ways: a structured API test (no succession FIELD key, no seeded
  succession VALUE like `READY_NOW`/`potential_band`, no other-employee id appears),
  a service test, and the live demo — all with full succession data SEEDED for the
  employee, and all showing zero leakage.

### Models (`apps/career/models.py`, all TenantScoped)
- `TargetRoleSelection` — an employee's chosen target role: a nullable FK PAIR
  (`target_jd` → a PUBLISHED `jd.JobDescription`, `target_position` → an
  `org.Position`), EXACTLY ONE set (service-validated, 422). `selected_by` +
  `selected_at` server-set.
- `DevelopmentRoadmap` — the advisory tiered path. `status` {DRAFT, ACTIVE,
  ARCHIVED}, `tiers` JSON, `skill_gap` JSON snapshot, `source` {DETERMINISTIC, AI},
  `advisory` (ALWAYS True), `confidence_score` (AI only). **`advisory` is enforced
  at the DB by a CHECK constraint `ck_roadmap_advisory_always_true`** — a structural
  guarantee the feature can never become auto-promotion (tested: an `advisory=False`
  insert is rejected by MySQL, the same standard as Module 3's HITL CHECK). "One
  ACTIVE deterministic roadmap per (tenant, employee, target)" is a code-enforced
  invariant (the service upserts the ACTIVE row) — MySQL's NULL-distinct semantics
  make a unique key over a nullable FK pair unable to express it (the documented
  Module-5/7 pattern).
- `RoadmapProgress` — per-tier progress {NOT_STARTED, IN_PROGRESS, DONE}, unique per
  (tenant, roadmap, tier_index).

### Deterministic engine (`engine.py` + `constants.py`, all tunable)
- `compute_skill_gap(employee_id)` → `{current_performance_band,
  required_performance_band, performance_band_gap, weak_categories}`. The
  performance band is the Module-8 band of the employee's latest CycleScore T-score
  (UNKNOWN when unscored → maximal gap). The LITE requirement is sustained HIGH
  performance (`REQUIRED_PERFORMANCE_BAND = HIGH`); the gap is the 0/1/2 band
  distance. Deliberately contains NO potential band / readiness / bench.
- `weak_goal_categories(employee_id)` → the employee's ACTIVE goals (in their latest
  scored cycle) whose Module-2 `goal_raw_score` is below `WEAK_GOAL_THRESHOLD`
  (= the Module-2 `ABS_AT_RISK` 0.8 — one definition of underperformance).
- `build_roadmap_tiers(gap, target_label)` → an ordered, reproducible advisory path:
  a performance tier per band to climb, a tier per weak category, a "demonstrate
  growth via a stretch assignment" tier, and a final stretch-goal tier — each with a
  `basis` provenance code. Pure + deterministic (same input → identical output).

### Career Roadmap agent SEAM (`roadmap_agent.py` + `tasks.py`) — Module 10 owns the LLM
`CareerRoadmapProvider` ABC + `NotConfiguredProvider` (raises tested
`CareerRoadmapNotConfiguredError`) + `get_provider()` resolving
`settings.CAREER_ROADMAP_PROVIDER`. `tasks.generate_roadmap(tenant_id, employee_id,
target_ref, actor_id)` binds the tenant off-request, computes the deterministic gap
ALWAYS, then resolves the provider; with NONE configured it returns
`{"generated": False, "reason": "no_provider"}` and the DETERMINISTIC roadmap (the
working baseline, produced by `select_target_role`) is left COMPLETELY INTACT — the
endpoint surfaces a loud 503, never a fabricated roadmap. A configured provider
drafts an enriched, still-ADVISORY path and locks a NEW `source=AI` roadmap as a
DRAFT (the human accepts it before ACTIVE); the baseline is never overwritten. Same
shape as the M3/M6/M8 seams; its surface gets `requires_entitlement("career_roadmap")`
in Module 10.

### Scope (employee-visible, unlike succession)
An Employee acts on / sees ONLY themselves; a Manager covers their reporting subtree
(`reporting_subtree_ids` + self); HRBP/Admin the tenant. Enforced in the services via
`actor_can_access`; an out-of-scope / cross-tenant target raises `NotFound` (404),
never a 403 (no existence leak — the project rule). Employees DO see their own
roadmap + gap (the friendly counterpart to succession's employee-404).

### RBAC additions (matrix + oracle)
`select_target_role`, `view_career_roadmap`, `manage_career_roadmap` — all held by
EVERY role; the services restrict the rows by scope. Oracle table extended (the
`test_expected_table_covers_every_capability` guard).

### API (apps/career, mounted at /api/career/, RBAC-gated + audited; views are the SOLE RBAC gate)
`POST /target` (SELECT_TARGET_ROLE) → 201 `{selection, roadmap}`; `GET /roadmap`
(own) + `GET /roadmaps[?employee=]` (scoped) + `GET /roadmaps/<id>` (404 out-of-scope)
+ `GET /roadmaps/<id>/skill-gap` (VIEW_CAREER_ROADMAP); `POST /roadmaps/<id>/regenerate`
(refresh deterministic) + `POST /roadmaps/<id>/enrich` (the 503 seam) +
`GET,POST /roadmaps/<id>/progress` (MANAGE_CAREER_ROADMAP for writes). Thin views;
services/tasks are the sole mutators + scope authority; no PATCH/PUT. Audits
career.target_selected / roadmap_generated / progress_updated / roadmap_ai_drafted —
all BEFORE the effect.

### Files
New: `apps/career/` (constants, models, exceptions, engine, roadmap_agent, services,
tasks, serializers, views, urls, apps, migration 0001, tests test_engine [13] +
test_services [16] + test_api [17]). Changed: rbac matrix + oracle (3 new caps),
settings (LOCAL_APPS + CAREER_ROADMAP_PROVIDER), config/urls, testsupport factories
(TargetRoleSelection/DevelopmentRoadmap/RoadmapProgress).

### Live validation (via nginx)
An employee (MEDIUM performer, t=50) selects a PUBLISHED-JD target → 201 deterministic
roadmap (advisory True, band_gap 1, 3 tiers: "Reach HIGH sustained performance" →
"Demonstrate growth…" → "Complete a stretch goal aligned to Staff Engineer (L5)");
skill-gap shows current MEDIUM / required HIGH / gap 1; with a READY_NOW bench
candidate + HIGH 9-box potential SEEDED for the employee the roadmap leaks ZERO
succession tokens and no other-employee id; enrich → 503 no_provider with the
deterministic roadmap intact (source DETERMINISTIC, ACTIVE); a manager views the
report's roadmap (200); the employee viewing a peer's roadmap → 404; progress mark →
200; an other-tenant admin → 404.

### Known risks / notes
- **The "required band" is a LITE rule (sustained HIGH).** A genuine per-role
  required profile (parsed from the target JD's level/competencies) is a Phase-2 /
  Agent (Module 10) refinement; the gap math is band-distance to HIGH for now.
- **The data boundary is enforced by NOT READING the sensitive surface** (the engine
  imports only `performance_band_for`/`goal_raw_score`) AND by keeping career copy
  free of succession vocabulary, so the leak-scan invariant is literally true.
- **The deterministic roadmap is the working baseline** (ACTIVE, ungated beyond RBAC
  + scope); the AI variant lands as a separate `source=AI` DRAFT for human
  acceptance (Module 10) — honouring CLAUDE.md rule 4 without an over-heavy HITL flow
  on the advisory deterministic path.
- **Export / a binary roadmap PDF is out** (Module 14).

### What Modules 10/13 need from this
- **Module 10 (Career Roadmap agent):** implement `CareerRoadmapProvider.draft`
  (LangGraph + LLMGateway over the deterministic gap + baseline tiers, PII-safe,
  confidence), point `CAREER_ROADMAP_PROVIDER` at it, gate the enrich surface with
  `requires_entitlement("career_roadmap")`. The seam, the AI-DRAFT lock, and
  `source=AI` are already wired — never auto-promotion (the advisory CHECK holds).
- **Module 11 (entitlements):** add `career_roadmap` to the feature-flag registry +
  the FULL_AI pack so `feature_flags_for` resolves it.
- **Module 13 (frontend):** renders `GET /roadmap`, `/roadmaps/<id>` (tiers +
  skill_gap), `/roadmaps/<id>/skill-gap`, `/progress`; all already scoped.


## Module 11 — Entitlements, Billing & Admin (+ Audit Console) (build-order M11 = Doc 2 §Module 13 + §Module 14 console)

**Status:** ✅ Complete. **919 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 9's 850 + 69 new; the 850 stayed green — nothing prior was rewritten).
Completes the decoupled commercial model (seat_count × feature_packs) from Module 1,
adds usage metering + per-tenant agent budgets that Module 10 will write to, and the
searchable READ-ONLY audit console. Deterministic, AI-free (the "which packs would
help" advisory is a Module-10 seam). Stack unchanged. Three touchpoints: `apps/billing`
(extended), `apps/audit` (console added), `apps/administration` (NEW app).

### Feature flags + the AI upgrade switch (`apps/billing`)
- `packs.py`: added the non-agent feature codes `chat` / `jd_generator` /
  `career_roadmap` and a `PACK_FEATURES` map (a SUPERSET of the Module-1
  `FEATURE_PACKS`, which is kept byte-for-byte so every Module-1 billing test stays
  green). `STARTER → {agent1, agent2, chat}`; `FULL_AI` adds agents 3-5 +
  jd_generator + career_roadmap. `features_for_packs` + `ALL_FEATURES` back the flag
  map. (See `NEEDS_HARI_pack_mapping.md` re: the Agent-1 STARTER-vs-FULL_AI nuance.)
- `feature_flags_for(tenant) -> {feature: bool}` over EVERY `ALL_FEATURES` code,
  derived from the tenant's PACKS (NOT seat_count — the two axes stay independent).
  Cached 300s under `tenant_cache_key(tid, "feature_flags")`; the existing
  upgrade/set_seats already clear the whole tenant namespace, so an upgrade flips
  flags instantly.
- `add_pack` / `remove_pack` (generic, audited, cache-invalidated) generalise the
  Module-1 `upgrade_to_full_ai`; `upgrade_prompt(tenant)` returns locked features +
  what FULL_AI would unlock — CONCEPTUAL only, no pricing/payment (Phase 2).
- Endpoints (Admin / MANAGE_ENTITLEMENTS): `GET /api/billing/feature-flags`,
  `GET /api/billing/upgrade-prompt`. The existing entitlement/upgrade/seats stay on
  MANAGE_TENANT (untouched).

### Usage metering + agent budgets (`apps/billing`)
- `TokenLedger` (TenantScoped): tenant, agent_code, model, prompt/completion/total
  tokens, occurred_at — the meter the Module-10 LLMGateway writes to.
  `record_usage(...)` binds the tenant (off-request safe) and computes the total.
- `AgentBudget` (TenantScoped): tenant, agent_code (or `"all"`), window
  {DAILY, MONTHLY}, limit; unique per (tenant, agent_code, window).
  `check_and_reserve_budget(tenant, agent_code, window)` reserves one call against a
  CACHE counter whose key EMBEDS THE TENANT ID (+ agent + window + period stamp) —
  cross-tenant budget isolation is a security control. Over budget → `BudgetExceeded`
  (429) with an `upgrade_hint`. `resolve_budget_limit` resolves an explicit per-agent
  row → a tenant-wide `"all"` row → the entitlement-derived default
  (`DEFAULT_AGENT_BUDGETS`, STARTER < FULL_AI, so an upgrade lifts budgets too). The
  M10 LLMGateway calls this BEFORE running an agent. Fixed-window approximation (same
  documented precision caveat as the Module-1.5b throttle; the precise path is a
  Redis Lua INCR).

### Audit Console (`apps/audit`, fills Doc 2 §Module 14)
`GET /api/audit/logs` (VIEW_AUDIT_CONSOLE — HRBP + Admin) — a DRF `ListAPIView`, so
READ-ONLY BY CONSTRUCTION (only GET is exposed; POST/PUT/DELETE → 405; there is NO
write surface). Paginated (50/page, `page_size` up to 200). Tenant-scoped
automatically by the append-only `AuditLog.objects` manager (the bound tenant —
HRBP = tenant in the MVP). Optional filters: actor / action / target_type /
target_id / date_from / date_to. The M1 immutability still governs every write path
(re-proven in the console tests: a direct `.update()` raises
`AuditLogImmutableError`). Nobody can write/alter the log via any surface.

### Admin Hub (`apps/administration`, NEW app — label "administration", NOT "admin")
Avoids the `django.contrib.admin` label clash. One new model `TenantConfig`
(TenantScoped, per-tenant `settings` JSON, unique per tenant). Services (Admin-only
at the view, audited before effect): `create_user` (422 on dupe email / unknown
role), `set_role`, `set_active` (de/reactivate), `set_reporting_line` (DELEGATES to
the Module-7 `reassign_reporting_line` with its cycle check — reused, not
duplicated), `list_users`, `get_tenant_config` / `update_tenant_config`. Endpoints
(`/api/admin/`): `GET,POST /users`, `POST /users/<id>/role|deactivate|reactivate|
reporting-line`, `GET,PUT /tenant-config`. Referenced user UUIDs resolve through the
tenant-scoped manager → cross-tenant id is 404; a reporting cycle → 422.

### RBAC additions (matrix + oracle)
`manage_entitlements`, `manage_tenant_config`, `manage_users_roles` (all
ADMIN-only), `view_audit_console` (HRBP + Admin, read-only). `MANAGE_TENANT` remains
the umbrella Admin capability on the existing billing endpoints. Oracle extended.

### Files
New: `apps/administration/` (apps, models, exceptions, services, serializers, views,
urls, migration 0001, tests test_services [11] + test_api [~14]); `apps/audit/`
(views, serializers, urls, tests test_console [~9]); `apps/billing/` migration 0002
(TokenLedger + AgentBudget), exceptions.py, tests test_feature_flags [7] +
test_budgets [8] + test_module11_api [~6]. Changed: `apps/billing/{packs,models,
services}.py`, rbac matrix + oracle (4 caps), settings (LOCAL_APPS), config/urls,
testsupport factories (TokenLedger/AgentBudget/TenantConfig).

### Live validation (via nginx + live Redis)
A STARTER tenant's `feature-flags` shows agent4/jd_generator/career_roadmap False
(agent2/chat True); Admin `upgrade` → all flags True with seat_count unchanged
(10→10), audited; an AgentBudget(limit=2) trips on the 3rd reserve (429) while
another tenant's counter is independent (1); `record_usage` writes a TokenLedger row
(total 420); Admin creates a user + assigns a role; HRBP reads the audit console
filtered by action (count 1), an EMPLOYEE → 403, `POST /api/audit/logs` → 405
(read-only); a non-Admin → 403 on tenant-config; an other-tenant Admin acting on
org's user → 404.

### Known risks / notes
- **Agent-1 pack placement** is flagged in `NEEDS_HARI_pack_mapping.md` (kept in
  STARTER per the registry; M10 prose suggested FULL_AI — a one-line commercial
  toggle, non-blocking).
- **HRBP audit-console scope = tenant-wide** (the Module-1 MVP HRBP simplification);
  when BusinessUnit lands, narrow it in the queryset.
- **Budget counters are fixed-window approximations** in the cache (documented; the
  precise path is a Redis Lua INCR, same as the throttle). Counters live in the
  cache DB; under a future allkeys-lru cache split they could be evicted (fail-open)
  — keep them on a non-evicting DB if strict enforcement is required.
- **No payment gateway** (entitlements are demoable without it — Phase 2); the
  upgrade prompt is conceptual (no pricing).

### What Module 10 needs from this
- The LLMGateway calls `check_and_reserve_budget(tenant, agent_code)` BEFORE running
  an agent (429 + upgrade hint over budget) and `record_usage(...)` AFTER each call.
- Gate each agent surface with `requires_entitlement(<feature_code>)` — the codes
  (`agent1..agent5`, `jd_generator`, `career_roadmap`, `chat`) and `feature_flags_for`
  are ready; `jd_generator` + `career_roadmap` are already in the FULL_AI pack.
- The `AIThrottle` (Phase 1.5b) + these budgets are complementary (rate vs quota).


## Module A — Analytics & Reporting (build-order insert = Doc 2 §Module 12)

**Status:** ✅ Complete. **957 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 11's 919 + 38 new; the 919 stayed green — nothing prior was rewritten).
Deterministic, cache-backed reporting over already-built data — NO new persisted
model. Scope-flagged in `NEEDS_HARI_analytics_scope.md` (Analytics is ✅ MVP in
Doc 2 §Module 12 but absent from CLAUDE.md's 14-step order; built tonight because
it is deterministic + MVP-marked + builds only on completed modules — Hari to
confirm scope). Stack unchanged. The Fast-AI anomaly narrative is a Module-10 seam.

### THE HEADLINE SAFETY PROPERTY — MIN-COHORT SUPPRESSION (≥ 5)
`apps/analytics/constants.MIN_COHORT = 5`. Any department/cohort view with FEWER
than 5 members returns AGGREGATE-ONLY with individual values SUPPRESSED, so a small
team can never be de-anonymised by its manager. This is a DIFFERENT, larger
threshold than the Module-4 360 per-group min-volume of 3 — both are kept and the
distinction is documented in `constants.py`. Proven at the boundary (a 4-person
dept exposes NO individuals; a 5-person dept does) in tests AND the live demo.

### No new model — computed + cached from existing data
- Performance from the Module-2 `CycleScore`; the calibration grid REUSES the
  Module-8 9-box `NineBoxPlacement`; a "department" is a manager + their reporting
  subtree (the Module-1/7 `User.manager` tree — no `Department` model yet).
- Department aggregates are cached under `tenant_cache_key(tid, "analytics", "dept",
  head, cycle)` (TTL 300) and INVALIDATED on a Module-2 recompute: `apps.py` connects
  a receiver to the `cycle_scores_recomputed` signal (→ `invalidate_analytics_cache`),
  so rollups never serve stale numbers. Proven in tests (cache hit returns the
  stale-by-design value; invalidation forces a fresh compute).

### Services (`services.py`, read-only, scoped)
- `individual_trend(actor, employee)` — an employee's performance trend across
  cycles (their OWN data; no cohort, no suppression). Scoped: Employee self / Manager
  reports / HRBP+Admin tenant; out-of-scope → 404.
- `department_analytics(actor, head, cycle)` — the cohort rollup with min-cohort
  suppression (aggregate = headcount, scored, mean/median T, risk distribution;
  individuals only when cohort ≥ 5). `head` must be in the actor's scope (404).
- `calibration_grid(actor, cycle)` — 9-box box-counts + placements (HRBP/Admin;
  reuses already-management-only succession data).
- `export_department(actor, head, cycle, fmt)` — text/JSON only (NO binary),
  honouring the same scope + suppression.

### Insights SEAM (`insights_agent.py`) — Module 10 owns the LLM
`AnalyticsInsightsProvider` ABC + `NotConfiguredProvider` (raises tested
`AnalyticsInsightsNotConfiguredError`) + `get_provider()` resolving
`settings.ANALYTICS_INSIGHTS_PROVIDER`. The DETERMINISTIC at-risk rollup (the
`risk_distribution`) is the always-available baseline; the AI anomaly/highlight
narrative lands in Module 10. No 503 endpoint yet (no AI surface) — just the seam.

### RBAC additions (matrix + oracle)
`view_individual_analytics` (all roles; scoped OWN for an employee),
`view_department_analytics` (Manager+; NEVER an employee — the employee-403 on
department analytics), `view_calibration_grid` (HRBP/Admin). Min-cohort suppression
applies ON TOP of scope.

### API (apps/analytics, mounted at /api/analytics/, RBAC-gated; views are the SOLE gate)
`GET /individual[?employee=]` (VIEW_INDIVIDUAL_ANALYTICS), `GET /department?head=&cycle=`
(VIEW_DEPARTMENT_ANALYTICS), `GET /calibration?cycle=` (VIEW_CALIBRATION_GRID),
`GET /export?head=&cycle=&format=json|text` (VIEW_DEPARTMENT_ANALYTICS). Thin views;
the service is the sole scope + suppression authority; UUIDs resolve through
tenant-scoped managers (cross-tenant → 404); a missing `?cycle` → 400. The export
view installs a small `_ExportContentNegotiation` so DRF's `?format=` override does
not intercept the endpoint's own `?format` param (it returns a raw HttpResponse).

### Files
New: `apps/analytics/` (apps [signal wiring], constants, services, insights_agent,
views, urls, tests test_services [13] + test_api [14]). Changed: rbac matrix +
oracle (3 caps), settings (LOCAL_APPS + ANALYTICS_INSIGHTS_PROVIDER), config/urls.
No migration (no model). NEEDS_HARI_analytics_scope.md at repo root.

### Live validation (via nginx)
A 4-person department → `suppressed=True`, `individuals=[]`, aggregate mean_T 49.5
(aggregate-only); a 5-person department → `suppressed=False`, all 5 individuals; an
employee reads their OWN individual trend (200) but is 403 on department analytics;
a manager pulling a peer manager's department → 404 (own line only); HRBP reads the
calibration grid (box 9 = 1, box 5 = 1) while an employee → 403; export returns
`text/plain` and `application/json`; an other-tenant admin → 404.

### Known risks / notes
- **"Department" = a manager + reporting subtree** (no `Department`/`BusinessUnit`
  model yet — flagged in NEEDS_HARI_analytics_scope.md alongside the HRBP-scope
  approximation carried since Module 1).
- **Suppressed cohorts still return the aggregate** (mean/median/risk counts) per the
  Doc-2 "aggregate-only" allowance; only INDIVIDUAL values are hidden. Tighten to a
  bare marker if even small-cohort aggregates are deemed sensitive.
- **Calibration is not min-cohort-suppressed** (it is HRBP/Admin-only over data they
  already see via succession) — documented; revisit if calibration is ever widened.

### What Module 10 needs from this
- Implement `AnalyticsInsightsProvider.summarize` (the Fast-AI at-risk/anomaly
  narrative over the deterministic rollup), point `ANALYTICS_INSIGHTS_PROVIDER` at
  it, surface it read-only/advisory. The deterministic rollup is the baseline.


## Module 12 — Integrations: Jira + Slack (build-order M12)

**Status:** ✅ Complete. **985 tests passing** on MySQL 8 + Redis 7 in Docker
(Module A's 957 + 28 new; the 957 stayed green — the signal additions to M4/M5 did
not regress anything). Fills the REAL provider/client behind the seams left in M2
(Jira actuals) and M4/M5 (Slack notifications). NO real Jira/Slack credentials are
used or required — everything external is behind per-tenant config + injectable
clients, tested with in-repo FAKES; unconfigured = the existing no-op/NotConfigured
behaviour. Stack unchanged.

### Secrets (NEVER in plaintext) — `NEEDS_HARI_secrets.md`
`TenantIntegration` stores only NON-secret `config` + a `secret_ref` — the NAME of
an env var holding the token, never the token. `secrets.resolve_secret(integration)`
reads `os.environ[secret_ref]` (else the convention `<KIND>_TOKEN_<SLUG>`); the value
is NEVER logged and NEVER serialized out of any endpoint. Unset env → `None` → clean
no-op. `NEEDS_HARI_secrets.md` recommends a real secrets manager (KMS/Vault) for
production — `resolve_secret` is the single swap point.

### Jira (fills `apps.goals.jira.get_provider` via `settings.JIRA_ACTUAL_PROVIDER`)
`jira_provider.JiraActualProvider` (subclasses the M2 ABC) resolves the current
tenant's enabled JIRA `TenantIntegration` and fetches a `source=JIRA` KPI's actual
via an INJECTABLE HTTP client (`JIRA_HTTP_CLIENT_FACTORY` — a FAKE in tests, the real
`JiraHTTPClient` inert without a token). The value is written through the EXISTING
`record_actual` path (the M2 single write path). A tenant with NO enabled Jira
integration → `fetch_actual` raises `JiraNotConfiguredError` → the M2
`sync_jira_actuals` log-and-skips (`no_provider`) UNCHANGED. `JIRA_ACTUAL_PROVIDER`
is deliberately LEFT UNSET in base settings so PRODUCTION stays on the M2
NotConfigured path; tests/real deployments set it.

### Slack (fills the M4/M5 notification touchpoints) — decoupled via SIGNALS
The emitters fire signals; integrations subscribes (one-way, the M2 Agent-2
pattern — the core apps never import integrations):
- `apps/feedback/signals.feedback_request_sent` fired in `send_feedback_request`.
- `apps/approvals/signals.approval_step_assigned` fired in `start_route` (initial
  active step) AND `_advance_after_approval` (next step activates);
  `approval_step_escalated` fired in `escalate_step`.
- All emitted with `send_robust` so a misbehaving receiver can NEVER break the
  action. `apps/integrations/receivers.py` (wired in `apps.ready`) calls the
  best-effort `notifications.notify_*`, which resolve the tenant's enabled SLACK
  integration and post via an INJECTABLE client (`SLACK_CLIENT_FACTORY` — a FAKE in
  tests). Every send is wrapped/logged/swallowed: a Slack failure leaves the
  triggering action intact (proven in tests + the live demo); unconfigured/disabled
  → clean no-op. `notify_kpi_nudge` is ready for the Module-10 Agent-2 surface.

### RBAC additions (matrix + oracle)
`manage_integrations` (Admin only — configure/enable per tenant). The syncs/sends
are system-driven (signals / the M2 Celery task), not user endpoints.

### API (apps/integrations, mounted at /api/integrations/, Admin-only)
`GET /api/integrations/` (list the tenant's integrations) + `GET, PUT
/api/integrations/<kind>` (kind = JIRA|SLACK; PUT upserts enabled / non-secret
config / `secret_ref`, audited `integration.configured`). The serializer exposes NO
token/secret value — only the env-var NAME. Thin RBACMixin views; `upsert_integration`
is the audited mutator. A raw token is never accepted.

### Files
New: `apps/integrations/` (models, secrets, clients, jira_provider, notifications,
receivers, services, serializers, views, urls, apps [signal wiring], migration 0001,
tests fakes + test_jira [4] + test_slack [12] + test_api [7]);
`apps/feedback/signals.py`; `apps/approvals/signals.py`;
`apps/approvals/tests/test_signals.py` [2]; `NEEDS_HARI_secrets.md`. Changed:
`apps/feedback/services.py` (fire signal), `apps/approvals/engine.py` (fire signals +
`_notify_assigned`), rbac matrix + oracle, settings (LOCAL_APPS + client-factory
settings), config/urls, testsupport factories (TenantIntegration).

### Live validation (config via nginx; sync + Slack in-process with FAKE clients)
Admin PUTs Jira + Slack config (200; the response carries NO token — only the
`secret_ref` NAME); a `source=JIRA` KPI's actual is pulled (fake client → 87) and
written via `record_actual`, and a recompute reflects it (raw_score 0.8700 for
target 100); a feedback request + an approval assignment + an escalation each record
a Slack send (3 total); a forced Slack outage records 0 sends but the feedback
request is STILL created (best-effort, the failure is logged not raised); an
unconfigured tenant → notify returns False (clean no-op, no crash).

### Known risks / notes
- **Secrets via env-var convention for the MVP** — swap `resolve_secret` for a real
  secrets manager in production (`NEEDS_HARI_secrets.md`).
- **Slack sends are synchronous in the signal receiver for the MVP** (best-effort,
  fast POST / fake in tests). Production should move the send to a Celery task (the
  notify functions already bind the tenant, so they are task-safe) to avoid holding
  the request/transaction during the network call.
- **The real `JiraHTTPClient` reads one field** (`config['value_field']`, default a
  custom field) from the issue JSON — adjust per the tenant's Jira schema; JQL
  aggregation is a later enhancement (`external_ref` currently = issue key).
- **`approval_step_assigned` fires for the active step(s)** at start + on
  next-step activation; role-slot steps carry `approver_id=None` (any in-scope
  holder acts) — the Slack message names the route/step, not a DM.

### What Module 10 needs from this
- Agent 2 (KPI nudges) calls `notifications.notify_kpi_nudge(tenant_id, message=...)`
  to deliver to Slack (best-effort, no-op when unconfigured) — the seam is ready.


## Module 10 — AI Agents via LangGraph + LLM Gateway (build-order M10)

**Status:** ✅ Complete. **1026 tests passing** on MySQL 8 + Redis 7 in Docker
(Module 12's 985 + 41 new; the 985 stayed green). The biggest module, built
AGENT BY AGENT and committed separately for durability. **No real LLM key is used
or required** — production stays on `NotConfiguredProvider` (loud 503, no
fabrication); the full agent graphs are exercised in tests + the demo via a
deterministic in-repo `FakeLLMProvider` (no network). Stack note below.

### Stack decision (transparent) — LangGraph NOT installed tonight
`langgraph` / `langsmith` / an LLM SDK are NOT in the image. Per contract rule 10
(no external deps tonight) and the paramount "leave all prior modules green," a
heavy LangChain dependency tree was NOT added to the unattended build (version-
conflict risk against Django 4.2). Instead the LangGraph node sequences are
implemented as deterministic Python (`apps/ai/graph.run_graph` — a faithful
`StateGraph` stand-in; the node FUNCTIONS are the real logic) and LangSmith tracing
is a no-op behind env. `NEEDS_HARI_llm_provider.md` documents the one-step swap to
real LangGraph + a provider SDK at go-live (the node functions don't change).

### The LLM Gateway (`apps/ai`, committed first) — the single choke (CLAUDE.md rule 6)
`LLMGateway.run(tenant, agent_code, prompt, schema, ...)` does, on EVERY call:
resolve the provider (`settings.LLM_PROVIDER`) → reserve the per-tenant agent
BUDGET (M11 `check_and_reserve_budget`) BEFORE the call → PII-scrub the prompt
(`pii.scrub`) → call the provider in a LangSmith trace span (no-op) → meter usage to
the M11 `TokenLedger` → schema-validate the output → attach confidence +
low-confidence flag. It NEVER raises to its caller — it returns a structured
`GatewayResult` (OK / NOT_CONFIGURED / BUDGET_EXCEEDED / SCHEMA_INVALID /
PROVIDER_ERROR). Providers: `LLMProvider` ABC, `NotConfiguredProvider` (prod
default), `FakeLLMProvider` (deterministic, per-agent output registry),
`HTTPLLMProvider` (inert scaffold). Each agent provider's `configured` delegates to
`llm_configured()`, so pointing a seam at an agent provider is SAFE in production
(503 until `LLM_PROVIDER` is set) and in existing tests.

### The seven agents (each committed separately)
- **Agent 1 — Review Assistant** (Large): node sequence (validate → gather evidence
  → gateway 5-section draft → structure → confidence/citations); fills the M3 seam;
  the M3 state machine locks the draft PENDING_HUMAN_REVIEW (HITL); confidence < 0.70
  attaches a warning but still locks pending.
- **Agent 2 — KPI Intelligence** (Fast): subscribes to the M2 `cycle_scores_recomputed`
  signal (+ weekly-beat callable); deterministic nudge rules (ON_TRACK→none;
  CRITICAL→critical; AT_RISK & ≤14d→suppress+warning; AT_RISK→standard); delivers via
  the M12 Slack notifier (best-effort); `manager_nudges` is the scoped read-only
  dashboard. NEVER mutates scoring.
- **Agent 3 — Feedback Summarization** (Large): consumes the M4 ANONYMISED payload →
  gateway 4-section summary → LOAD-BEARING post-LLM anonymity-breach check (catches a
  free-text leak the M4 email-only pre-LLM guard missed) → the M4 task (additively)
  holds the summary HRBP_HOLD + `anonymity_passed=False`. Sections stay HITL-gated.
- **Agent 4 — Successor Planning** (Large): enriches the deterministic M8 analysis
  (internal CycleScore signals only — NEVER raw 360 givers) with a gateway narrative
  + confidence; the M8 task locks a NEW `source=AI` plan PENDING, deterministic plan
  intact.
- **JD Generator** (Large): validated inputs → gateway JD body → the M6 lifecycle
  locks `source=AI` PENDING.
- **Career Roadmap** (Large): deterministic gap (M9) + baseline → gateway enriched
  tiers → a NEW `source=AI` DRAFT for human acceptance; the M9 `advisory` DB CHECK
  still holds (never auto-promotion).
- **Chat Assistant** (Fast, READ-ONLY — the safety-critical one): `POST /api/ai/chat`.
  The LLM classifies read-vs-write intent; reads route DETERMINISTICALLY against the
  existing scoped data using the CALLER's identity + RBAC (`actor_can_access` /
  tenant-scoped managers), so it can NEVER surface data the caller couldn't already
  see (employee→peer goals = nothing; cross-tenant = nothing — identical to a direct
  scoped API call); write/approval intents are BLOCKED. Gated `USE_CHAT` (everyone) +
  `requires_entitlement("chat")`; the chat budget trips 429 via the gateway.

### Entitlements
`requires_entitlement` now resolves FEATURES (`tenant_has_feature` — the superset
covering agents + chat/jd_generator/career_roadmap), so the same gate works for every
agent. Chat is gated live (`chat`, STARTER). The other agent surfaces' gates
(agent1 STARTER; agent3/agent4/jd_generator/career_roadmap FULL_AI) are wired at
go-live alongside the provider — documented in `NEEDS_HARI_llm_provider.md` — to keep
every agent commit self-contained with zero prior-module test churn (adding a FULL_AI
gate to an existing seam surface would 403 its STARTER 503-test).

### RBAC additions (matrix + oracle)
`use_chat` (everyone; data scope-bounded in the services + entitlement-gated).

### Files
New: `apps/ai/` (apps [signal wiring + fake registration], exceptions, pii, tracing,
graph, schemas, providers, gateway, views [Chat], urls, agents/{review,kpi,feedback,
succession,jd,career,chat}, tests test_gateway + per-agent tests). Changed:
`apps/feedback/tasks.py` (+post-LLM breach → HRBP_HOLD), `apps/billing/{gate,services}.py`
(requires_entitlement → tenant_has_feature), rbac matrix + oracle (use_chat), settings
(LOCAL_APPS + LLM_PROVIDER + LANGSMITH_API_KEY), config/urls. NEEDS_HARI_llm_provider.md.

### Live validation (chat-503 via nginx; agents in-process with FakeLLMProvider)
Authenticated chat through nginx with no LLM provider → 503; Agent 1 → a 5-section
draft PENDING (confidence 0.9) → manager approve+finalize → FINALIZED (human_reviewer
set); Chat → an employee asking for a peer's goals gets `[]` (RBAC-bound) and a write
intent is blocked; Agent 3 → a planted free-text email leak in the generated summary
→ HRBP_HOLD (anonymity_passed False); the TokenLedger metered every gateway call (4
rows across agent1/chat/agent3).

### Known risks / notes
- **LangGraph/LangSmith/LLM SDK not installed** (deliberate, documented) — the node
  functions are the real logic; the library swap is config (NEEDS_HARI_llm_provider.md).
- **Production is 503 by design** until `LLM_PROVIDER` + the per-seam provider settings
  are set + FULL_AI provisioned for paid agents — the single source of truth for "is
  AI live" is `llm_configured()`.
- **Budget enforcement is tested at the gateway** (clean BUDGET_EXCEEDED result) and
  surfaced as 429 by the Chat view; agents routed through the pre-existing M3/M4/M6/M8/M9
  seam tasks meter usage + reserve budget, and an over-budget result there surfaces as a
  task skip (those tasks' broad except predates the budget concept) — documented.
- **Agent 2 nudge composition is deterministic** (the M2 risk classification is the
  intelligence); optional LLM phrasing via the gateway is a later enhancement.

### What going live needs (NEEDS_HARI_llm_provider.md)
Pick a provider; `pip install langgraph langsmith <sdk>` + rebuild; set `LLM_PROVIDER`
(+ key) and each seam provider setting; provision FULL_AI for paid agents; confirm the
per-tenant agent budgets. Until then: 503 everywhere, by design.


## Pre-frontend — Agent-1 repackaging + Frontend Contract

**Status:** ✅ Complete. **1026 tests passing** on MySQL 8 + Redis 7 in Docker
(unchanged count — the commercial change updated existing billing/feature-flag test
expectations; the contract is docs-only). Two pieces, no new app code beyond
`apps/billing/packs.py`:

### Agent 1 → FULL_AI (commercial repackaging)
Resolved `NEEDS_HARI_pack_mapping.md` (now marked RESOLVED) with Hari's decision:
Agent 1 (Review Assistant) is **PREMIUM**. `apps/billing/packs.py` now has
`FEATURE_PACKS` STARTER = `{agent2}`, `PACK_FEATURES` STARTER = `{agent2, chat}`;
FULL_AI = the full suite (`agent1..5, chat, jd_generator, career_roadmap`). Agent 2 +
Chat are the STARTER "AI taste"; every generative agent (incl. Agent 1) is FULL_AI.
The decoupled seat×pack model is unchanged; billing pack/service/endpoint/
feature-flag test expectations updated. Commit `Agent 1 → FULL_AI (commercial repackaging)`.

### Frontend Contract → `docs/frontend-contract/`
A code-derived, design-agnostic spec a designer + frontend engineer can build
Module 13 against WITHOUT reading Python (no visual-design opinions):
- `00_overview.md` — the two surfaces (Desktop Hub / Mobile-Web), role×screen×surface
  reachability, the full auth/MFA/OIDC flow, the global status/error conventions
  (incl. the "404 = not yours/not there" rule, 429/Retry-After/upgrade_hint,
  feature-flag-driven premium gating), and the HITL principle.
- `01_screens.md` — the screen inventory (16 areas): per screen, the endpoints
  (method · path · capability · scope), the data (serializer + fields), every user
  action → endpoint → state transition, every state (incl. error-per-code / locked /
  404 / pending / 429 / 503), and the validation rules.
- `02_state_machines.md` — Review · Approval route · JD · Succession plan · Career
  roadmap, each as a state list + transition table (from · action · to · who) for
  stepper/timeline UI.
- `03_data_dictionary.md` — every entity, field, **enum value set**, read-only vs
  settable, referencing the serializers as the source of truth.
- `04_role_journeys.md` — the 4 primary end-to-end journeys (Employee / Manager /
  HRBP / Admin) with surface crossings + HITL gates marked.
- `05_open_questions.md` — assumptions + assumed defaults (pagination, timezone,
  workflow-designer scope, exports, feature-flag visibility, real-time, etc.) + a
  short list of recommended small backend follow-ups (a `my-features` read endpoint,
  a manager `nudges` endpoint, list pagination, a user display-name).

**Out of scope (NOT done, by instruction):** any React/frontend code.
