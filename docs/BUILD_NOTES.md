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
