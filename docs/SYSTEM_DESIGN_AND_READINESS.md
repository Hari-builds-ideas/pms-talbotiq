# SYSTEM_DESIGN_AND_READINESS.md — Talbotiq PMS

> Senior-staff production-readiness + system-design assessment, grounded in the
> **actual code/config** (cited as `file:line` / setting). Where a doc and the
> code disagree, the code wins (flagged ⚠). Markers: **BUILT** / **PARTIAL** /
> **NOT-BUILT**. No code was changed; no Groq calls made. Accuracy over optimism.

---

## 1. Executive readiness verdict

**Pilot-ready, not yet real-load-ready.** This is materially more than a demo: the
web tier is genuinely stateless and documented to scale (`gunicorn.conf.py`,
`docker-compose` `--scale web=N`), tenant isolation is **fail-closed** in the ORM
(`apps/tenancy/managers.py:54` → `qs.none()`; `models.py:77` → `PermissionError`),
there are entitlement-driven per-tenant/user throttles (`apps/core/throttling.py`),
a hardened `config/settings/prod.py` (DEBUG off, HSTS, secure cookies, fail-closed
`SECRET_KEY`/`ALLOWED_HOSTS`), `/healthz`+`/readyz` probes, Sentry with a PII
scrubber, and 17 tenant-first composite DB indexes. But it runs as a **single-node
docker-compose** with a **single MySQL (no replica, capped at 100 connections)**,
secrets in a gitignored `.env`, the dev code-mount (`.:/app`) still in the only
compose file, AI on the Groq **free tier** behind a 60-call/run ceiling, and AI
calls executed **synchronously in the request path**.

**Single biggest scaling risk:** the **single MySQL node** — no read replica, no
router (`grep` for `DATABASE_ROUTERS`/`db_for_read` → none), `--max-connections=100`
(`docker-compose.yml`). It is both the first hard ceiling (~3 web replicas exhaust
the connection budget by the in-code sizing math, `base.py:147-150`) and a SPOF.

**Top 3 to fix before real load:** (1) **Managed MySQL** with proper connection
sizing + automated backups/PITR, and a plan for read replicas (router is NOT-BUILT).
(2) **Split Redis** — the broker DB (`/0`, `noeviction`) shares one instance with
the cache (`/1`); cache churn under load can starve queued jobs — run a separate
`allkeys-lru` cache Redis (the env URLs already allow this with no code change),
and move secrets to a vault. (3) **Decouple AI from the request thread** + raise off
the free tier — a slow/recovering Groq call can hold a gunicorn worker for tens of
seconds (synchronous gateway), and the per-tenant budget reserve is **not atomic
across replicas** (`apps/billing/services.py:379`).

---

## 2. Current architecture (as-built)

```
                      Internet
                         │  :8080
                ┌────────▼─────────┐
                │  frontend (nginx)│  edge: serves the built React SPA;
                │  frontend/nginx. │  reverse-proxies /api,/admin,/accounts,
                │  conf            │  /static,/healthz,/readyz → web:8000.
                └────────┬─────────┘  variable upstream re-resolves `web`
                         │            (survives restart/scale); 10m body cap;
                         │            read-timeout 65s (≈ gunicorn 60s).
                ┌────────▼─────────┐
                │  web (gunicorn)  │  Django 4.2 + DRF. (2×cores)+1 workers,
                │  STATELESS · N   │  2 threads (gthread), max_requests recycle.
                │  --scale web=N   │  Auto-migrate on boot. JWT auth; tenant
                └──┬───────┬───────┘  bound per-request from the JWT (contextvar).
                   │       │
        ┌──────────▼──┐  ┌─▼───────────────┐
        │  MySQL 8    │  │  Redis 7        │  /0 Celery broker+results (noeviction)
        │  SINGLE     │  │  SINGLE         │  /1 app cache (TTL, evictable)
        │  max_conn   │  │                 │  /2 sessions (cache-backed)
        │  =100       │  └─▲───────────────┘  + throttle/budget/AI-ceiling counters
        │  CONN_MAX_  │    │
        │  AGE=60     │    │ broker
        └─────────────┘  ┌─┴───────────┐  ┌──────────────┐
                         │ celery-     │  │ celery-beat  │ 1 schedule: approvals
                         │ worker      │  │              │ escalation sweep / 5min
                         └─────────────┘  └──────────────┘
                         ┌──────────────┐
                         │ flower :5555 │ basic-auth required
                         └──────────────┘
        AI: web → LLMGateway → Groq (OpenAI-compatible HTTP), IN-REQUEST/SYNC.
```

- **One process vs separable:** `web`, `celery-worker`, `celery-beat`, `flower`,
  `frontend` are already separate services from one image (`docker-compose.yml`
  YAML-anchored env). The web tier scales as N replicas; workers scale independently.
- **Stateless vs stateful:** `web` + `celery-*` are **stateless** (there's a
  `apps/tenancy/tests/test_statelessness.py` asserting it). **State lives in**:
  MySQL (all domain data), Redis (`/0` queue+results, `/1` cache, `/2` sessions,
  plus throttle/budget/AI-ceiling counters). ⚠ The only compose file mounts the
  source (`.:/app`) into `web`/`celery` — that's a **dev** convenience, NOT a
  production image; prod must bake the code into the image.

---

## 3. Scalability (actual code vs not)

### 3.1 Rate limiting / throttling — **BUILT** (global tenant+user) / **PARTIAL** (AI per-view, non-atomic)
- DRF default throttles are `TenantThrottle` + `UserThrottle` (`base.py:237-240`),
  each resolving its rate **per request** from `rate_limits_for(tenant)` so an
  upgrade lifts limits everywhere (`apps/core/throttling.py`). Cache keys **embed
  the tenant id** → counter isolation is a tenant-isolation control.
- `AnonRateThrottle` (IP-based) guards the login surface, default `100/min`
  (`base.py:244`).
- `AIThrottle` exists + is unit-tested but is **per-view (Module 10), not global**
  (`throttling.py` docstring) — ⚠ confirm it is attached to every AI route.
- **AI gateway ceiling/budget:** the gateway reserves a per-tenant **AgentBudget**
  before every call (`check_and_reserve_budget`, `billing/services.py:368`) → 429
  `BudgetExceeded` when hit; and a process-wide **global call ceiling**
  (`LLM_MAX_CALLS`, default 60) counted in Redis (`apps/ai/groq.py` `_reserve_global`).
  Groq 429 → honour `Retry-After`, back off, retry ×3 (`groq.py` `_post_with_backoff`).
- **Missing:** throttling is a DRF rolling-window over the cache; check-then-reserve
  for budgets is **not strictly atomic across replicas** (documented, `services.py:379`)
  — two replicas can both pass the check at the limit edge. The fix (a Redis Lua
  `INCR/EXPIRE`) is noted in the code as the upgrade path. No edge/nginx rate limit.

### 3.2 Database — **BUILT** (single node, well-indexed) / read replicas **NOT-BUILT**
- MySQL 8, `django.db.backends.mysql`, **`CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True`**
  (`base.py:151-152`) → persistent connections revalidated per request (a killed
  conn is transparently replaced). Strict SQL mode (`base.py:156`).
- **Connection sizing is the ceiling:** `--max-connections=100` (`docker-compose.yml`);
  the code comments the math: `replicas × workers × threads + celery + headroom`,
  e.g. `3 × 9 × 2 = 54 < 100` (`base.py:146-150`). So **~3 web replicas** before the
  connection budget is the bottleneck — raise both before scaling past that.
- **Indexing:** **17 composite indexes, all leading with `tenant`** across the
  models (`grep models.Index(fields=` over `apps/*/models.py`), matching the
  hot multi-tenant query pattern (`WHERE tenant_id = ? AND …`). Good.
- **N+1 risk — ⚠ REAL:** the Part-1 name-resolution added `*_name` SerializerMethodFields
  that dereference person FKs per row (reviews, approvals, goals, etc.). Paginated
  list views (50/page) generally **don't `select_related`**, so a 50-row reviews
  list can fire ~150–200 queries. Cheap fix: add `select_related`/`prefetch_related`
  on the list querysets. Flag before large tenants.
- **Migrations:** standard Django; the audit log uses **DB triggers** for INSERT-only
  immutability (needs `log-bin-trust-function-creators` / TRIGGER+SUPER at migrate
  time — `docker-compose.yml` mysql command; documented for managed DBs).
- **Read replicas / sharding:** **NOT-BUILT** — no `DATABASE_ROUTERS`, no
  `using()`/`db_for_read`. Adding read replicas needs: a second `DATABASES` entry +
  a router sending reads to the replica (careful with read-after-write on the
  request that just wrote), and replica-lag awareness in the hot read paths.
  Sharding: not needed at pilot scale; tenant_id is the natural shard key later.

### 3.3 Caching — **BUILT**
Redis split by logical DB (`base.py:165-193`): `/0` Celery broker+results,
`/1` app cache (`django_redis`, `TIMEOUT=300`, `KEY_PREFIX=pms`), `/2` sessions
(cache-backed). Cache holds: entitlement reads (`get_entitlement_cached`),
feature-flag + rate-limit maps, analytics aggregates (`tenant_cache_key`), the
throttle + per-tenant-budget + AI global-ceiling counters. **What ISN'T cached but
could be:** per-request directory/name lookups (the N+1 above), the org tree
(recomputed per request server-side; cached client-side only), and hot read
endpoints lack response caching. ⚠ The cache + broker share one Redis instance in
the only compose file — see §1 risk #2.

### 3.4 Async / background — **PARTIAL**
- Celery worker + beat are separate services on the Redis `/0` broker. **One beat
  schedule**: approvals escalation sweep every 300s (`base.py:310-315`).
- ⚠ **AI is NOT offloaded** — the agent seams (e.g. `request-ai-draft`,
  feedback close→summarize, succession enrich) call the gateway **synchronously in
  the request** (Module-3/4 tasks invoked inline). So a slow Groq call holds a
  gunicorn worker (up to `LLM_TIMEOUT=30s`, ×retries on 429). Under AI load this is
  worker-starvation, not queue back-pressure. Moving AI to Celery (poll/callback) is
  the scale fix.
- Broker back-pressure: `/0` is `noeviction` → under memory pressure Redis **rejects**
  enqueue writes (jobs error loudly, never silently dropped) — correct, but shared
  with the cache today (risk #2).

### 3.5 Horizontal scaling — **BUILT (web tier)**
The web tier is genuinely stateless: JWT auth (no server session affinity for the
API — sessions exist only for the allauth/OIDC handoff, and they're in shared
Redis `/2`, so **no sticky sessions needed**), no local file/disk state
(`test_statelessness.py`), gunicorn tuned for replicas (`gunicorn.conf.py`), and
nginx re-resolves the `web` upstream so `--scale web=N` works today. **What blocks
scaling past ~3 replicas:** the MySQL 100-connection cap (§3.2) and the
non-atomic-across-replicas budget/throttle edge (§3.1) — neither breaks, both need
sizing/Lua before high replica counts.

### 3.6 AI layer under load — **BUILT (graceful) but free-tier + synchronous**
- Provider limits: Groq free tier (~30 RPM / 12k TPM); `LLM_MAX_CALLS=60` run
  ceiling; per-tenant daily/monthly `AgentBudget`. A **burst of AI requests** →
  budget/ceiling 429s (with `upgrade_hint`) + Groq 429 back-off, then the surface
  shows "try again / upgrade" — **it degrades, it doesn't fabricate or crash**
  (`LLMGateway.run` returns a structured `GatewayResult`, never raises; no key →
  `NOT_CONFIGURED` → 503 and the deterministic/manual path still works).
- ⚠ Two real limits under load: (a) **synchronous in-request** execution (worker
  starvation, §3.4); (b) the **free tier** is a hard, low ceiling — a handful of
  concurrent AI actions is the first thing to bottleneck (by design, gracefully).

---

## 4. Deployment system design (target) — current vs SHOULD-BE

| Piece | Current (compose) | Target (prod) | Status |
|---|---|---|---|
| Edge / TLS | nginx in-container, HTTP :8080 | managed LB + TLS termination (or nginx + cert-manager); `prod.py` already sets `SECURE_PROXY_SSL_HEADER`/HSTS | **PARTIAL** (prod.py BUILT; LB/TLS infra NOT-STARTED) |
| Web tier | `--scale web=N`, dev `.:/app` mount | N stateless replicas from a **baked image** (no source mount) behind the LB | **PARTIAL** (stateless BUILT; image-bake NOT-STARTED) |
| MySQL | single container, 100 conns | managed MySQL (sized conns, automated backups + PITR) **+ read replica** | **PARTIAL** (single BUILT; replica/router NOT-BUILT) |
| Redis | one instance, cache+broker+sessions | **separate** managed Redis: broker (noeviction/persistent) vs cache (allkeys-lru) — env URLs already allow it | **PARTIAL** (split-by-URL BUILT; separate instances NOT-STARTED) |
| Celery | worker + beat containers | autoscaled worker pool + a single beat; AI offloaded to a queue | **PARTIAL** |
| Secrets | gitignored `.env` + compose interpolation | a vault (AWS/GCP Secrets Manager / Vault); `resolve_secret` is one swap point | **NOT-STARTED** (env-ref convention BUILT) |
| Object storage | none needed (exports are text/JSON) | only if file uploads/PDF land later | **N/A today** |
| CDN | none | CDN for the SPA static assets | **NOT-STARTED** |
| Health checks | `/healthz` (liveness) + `/readyz` (DB/Redis/broker) | wire to LB + orchestrator probes | **BUILT** (`apps/core/health.py`, `views`) |
| Deploys | `compose up --build` | rolling/blue-green; migrations are `--noinput` on boot (⚠ couple to a controlled migrate step, not every replica boot) | **NOT-STARTED** |
| Backups / DR | mysql_data volume only | managed backups + tested restore + RPO/RTO | **NOT-STARTED** |

---

## 5. Observability & ops

- **Logging — BUILT:** structured request-id correlation (`RequestIDMiddleware`,
  contextvar) on every log line; gunicorn access/error logs to stdout
  (`gunicorn.conf.py`).
- **Error tracking — BUILT (opt-in):** Sentry via `apps/core/observability.py`
  with a real `before_send` scrubber (redacts authorization/token/password/
  mfa_token; tags `tenant_id`+`request_id`); no-op without `SENTRY_DSN`. PII-safe.
- **Tracing — PARTIAL:** LangSmith spans around LLM calls, opt-in (`LANGSMITH_API_KEY`,
  no-op until set). No general APM/distributed tracing.
- **Metrics/dashboards/alerting — NOT-BUILT:** no Prometheus/metrics endpoint, no
  dashboards, no alerting/uptime. **This is the biggest ops gap** for running in prod.
- **Celery — BUILT:** flower dashboard (basic-auth required, `docker-compose.yml`).
- **Audit log — BUILT:** INSERT-only (DB triggers), tenant-scoped, read-only console.
- **Missing for prod:** metrics + dashboards + alerting (latency, error rate, queue
  depth, DB conns, Groq 429/budget, uptime), and log aggregation/retention.

---

## 6. Security & multi-tenancy hardening

- **Tenant isolation — BUILT, fail-closed:** `TenantScopedManager.get_queryset` →
  `qs.none()` when no tenant is bound (`managers.py:54`); a cross-tenant write
  raises `PermissionError` (`models.py:77`); cross-tenant reads/details → **404, not
  403** (never reveal existence). Counters (throttle/budget/cache) embed the tenant id.
- **Authn/z — BUILT:** JWT (HS256, 15-min access / 7-day refresh, **rotate +
  blacklist-after-rotation** so a raced/reused refresh is blacklisted), Argon2
  hashing, server-side RBAC matrix + scope on every endpoint. ⚠ HS256 with
  `SECRET_KEY` as signing key — fine for one service; if tokens are ever verified by
  other services, move to RS256 (asymmetric).
- **Secrets — PARTIAL:** `prod.py` fails closed (no `SECRET_KEY`/`ALLOWED_HOSTS`
  default), integration tokens are env-var **references** never stored
  (`secret_ref`), and the Groq key is gitignored. ⚠ But there is **no vault** —
  `.env` is the store today; required before real customer data.
- **PII in the AI path — BUILT:** the gateway PII-scrubs prompts (emails) before the
  provider; feedback summaries are built from the anonymised payload (giver identity
  never enters a prompt); Agent-3 post-LLM breach check; succession evidence is
  name-free. Sentry scrubs secrets.
- **Anonymisation — BUILT:** 360 giver identity never egressed; per-group min-volume
  (≥3) suppression; verified live.
- **MFA/OIDC — PARTIAL/BUILT:** TOTP MFA (`django-otp`) BUILT + verified live; OIDC
  via allauth wired (env-driven), full SSO round-trip needs a real IdP.
- **Known gaps before customer data:** vault; HTTPS/LB in front (prod.py expects a
  TLS-terminating proxy); rotate the demo `SECRET_KEY`; per-tenant data-retention/
  export/delete (GDPR) is not built; no WAF/DDoS layer.

---

## 7. Edge cases & failure modes (current behaviour)

| Scenario | Current behaviour | Graceful? | Fix |
|---|---|---|---|
| **DB down** | `/readyz` fails (health backend); requests error 500; `CONN_HEALTH_CHECKS` replaces killed conns on recovery | Partial (LB can drain via readyz) | managed DB + replica failover |
| **Redis down** | cache misses recompute, BUT **sessions** (`/2`) + **Celery enqueue** (`/0`) + throttle/budget counters fail → SSO/session breaks, tasks can't enqueue, `/readyz` fails | ⚠ No — Redis is a SPOF for sessions+async | managed Redis HA; consider DB-backed session fallback |
| **Celery backed up** | jobs queue in `/0` (noeviction → enqueue **errors** if full, never silent drop); escalation sweep delayed | Yes (loud, not lossy) | autoscale workers; separate broker Redis |
| **Groq down / timeout / 429 / over-budget** | gateway returns structured result: NOT_CONFIGURED→503, PROVIDER_ERROR, BUDGET_EXCEEDED→429+upgrade_hint, 429→Retry-After back-off ×3; **never fabricates**; deterministic/manual path holds | Yes | move AI off the request thread (timeout holds a worker ~30s) |
| **Expired/invalid JWT + refresh race** | expired access→401→refresh; rotate+blacklist means a reused refresh is blacklisted→401→re-login | Yes | — |
| **Cross-tenant access attempt** | `qs.none()` / `PermissionError` / 404 — fail-closed | Yes (secure) | — |
| **Concurrent writes** | state machines re-derive from current status → stale action → **409**; ⚠ plain-field PATCHes are last-writer-wins (no optimistic `version` field) | Partial | add optimistic version on high-contention entities if needed |
| **Large tenant (10k employees)** | lists paginate (50/page) on tenant-first indexes; ⚠ **N+1** from name SerializerMethodFields without `select_related`; ⚠ client `useDirectory` loads the whole org tree | Partial | `select_related` on list views; paginate/lazy the directory |
| **360 below suppression threshold** | groups < min_volume excluded from the egress payload + flagged `insufficient_groups`; never egressed | Yes (verified) | — |
| **Partial AI failure mid-pipeline** | gateway schema-validates; a failed step → `result not ok` → task logs, artifact stays pre-AI (no fabricated draft); feedback breach → HRBP_HOLD | Yes (human-gated) | — |

---

## 8. Load expectations & limits (honest order-of-magnitude)

Reasoning, not measured — treat as ±1 order of magnitude on the **current single-node
compose**:

- **Web tier:** one node ≈ `(2×cores)+1` workers × 2 threads. On a 4-core node ≈ ~18
  concurrent request slots; typical DB-bound requests ~50–150ms → **tens of req/s
  sustained per node**, i.e. **a few hundred active concurrent users** doing normal
  PMS work. Scales out near-linearly — **not the first ceiling**.
- **MySQL:** `max_connections=100` + persistent conns → **~3 web replicas** exhaust
  the connection budget (in-code math). Beyond connections, a single managed MySQL
  node handles thousands of simple indexed tenant-scoped queries/s — but it is the
  **first hard ceiling and the SPOF**.
- **Redis:** trivially 10k+ ops/s; **not** the throughput bottleneck — but memory
  pressure on the **shared** instance can starve the noeviction broker (risk #2).
- **AI (Groq free tier):** ~30 RPM + a 60-call run ceiling → **a handful of
  concurrent AI actions** is the **first thing to saturate** — by design it 429s/503s
  gracefully rather than failing the app.

**Plausible envelope today:** a single pilot tenant of **O(100s–1k) employees** with
**O(10s) concurrent users** doing reviews/goals/feedback, AI used **sparingly**, on
one beefy node (or 2–3 web replicas + the 100-conn DB). **First tier to give:** AI
quota (immediately, gracefully) → MySQL connections (~3 replicas) → MySQL node IOPS →
Redis memory (if cache+broker shared). Multi-tenant at scale needs §4's target.

---

## 9. Pre-deployment checklist (prioritised, sized)

**Must-have before ANY real users (data + correctness):**
- [ ] **Secrets → a vault** (Groq key, integration tokens, `SECRET_KEY`); rotate the demo key. — **M** *(build + infra)*
- [ ] **Managed MySQL** with automated backups + tested restore; set conn limit to the sizing math. — **M** *(infra decision)*
- [ ] **Bake the prod image** (drop the `.:/app` mount); run under `config.settings.prod` with real `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`. — **S** *(build)*
- [ ] **TLS + LB** in front of the web tier (prod.py already assumes a TLS proxy). — **M** *(infra)*
- [ ] **Controlled migration step** (not `migrate` on every replica boot — race on N replicas). — **S** *(build/ops)*
- [ ] **Separate Redis for cache vs broker** (broker noeviction; cache allkeys-lru) — env-only change. — **S** *(infra)*
- [ ] **`select_related` on paginated list views** to kill the name-resolution N+1. — **S** *(build)*

**Before scale (load):**
- [ ] **Move AI off the request thread** (Celery + poll/callback) so Groq latency can't starve workers. — **M** *(build)*
- [ ] **Atomic budget/throttle enforcement** across replicas (Redis Lua INCR/EXPIRE; path already noted in code). — **M** *(build)*
- [ ] **Raise off the Groq free tier** to a paid tier (or alt provider) + size per-tenant budgets. — **S** decision **/ M** wiring.
- [ ] **Read replica + DB router** for read-heavy endpoints (analytics, lists). — **L** *(build + infra)*
- [ ] **Metrics + dashboards + alerting + uptime** (the biggest ops gap). — **M–L** *(build + infra)*
- [ ] **Autoscale Celery workers**; size the broker. — **M** *(infra)*

**Nice-to-have:**
- [ ] Optimistic-locking `version` on high-contention entities; CDN for SPA assets;
      RS256 JWTs if multi-service; per-tenant data-retention/export/delete (GDPR);
      response caching on hot reads; real-LangGraph swap; load test to replace §8's
      estimates with measured numbers. — **S–L** each.

---

*Grounded in the repo as read this session. `BUILT` = present in code/config (cited);
`PARTIAL` = partially present; `NOT-BUILT` = absent (target only). The target
architecture in §4 does **not** exist yet — it is the destination, not the state.*
