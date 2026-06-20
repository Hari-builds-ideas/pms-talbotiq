# BUILD_4 — Prod settings & deploy-readiness, metrics/observability/health, optimistic locking, hot-read caching

> Read BUILD_0_READ_FIRST.md first. Build 4 of 5. This makes the app operationally production-ready at
> the CODE level: a clean prod settings/deploy posture (no infra provisioning), the metrics/observability
> the ops-gap needs, concurrency protection on contended writes, and response caching on hot reads. All
> repo-level, all verifiable against the existing stack. ZERO LLM calls.

---

## Phase 4.1 — Production settings separation & deploy-readiness (code only)

- Confirm/complete `config/settings/prod.py` as the production profile: DEBUG off, HSTS, secure cookies,
  fail-closed SECRET_KEY/ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS (no defaults), SECURE_PROXY_SSL_HEADER set
  (assumes a TLS-terminating proxy in front — that proxy is infra, not built here). Verify it imports a
  shared base and only overrides prod concerns.
- Add a PRODUCTION DOCKERFILE / build target that BAKES the code into the image (no `.:/app` source
  mount) and add a `docker-compose.prod.yml` (or an override) that: runs under `config.settings.prod`,
  uses the baked image, does NOT mount source, separates the cache Redis from the broker Redis via env
  URLs (the split-by-URL already exists — just point them at two instances/DBs and document it), and
  runs gunicorn with the tuned config. This is CONFIG for a real deploy; it does not provision anything.
- CONTROLLED MIGRATIONS: today migrate runs on every web boot (a race on N replicas). Add a dedicated
  one-shot migrate step (a separate compose service / documented command) and make the web container
  NOT auto-migrate in prod (keep auto-migrate in dev). Document the deploy order in docs/RUNBOOK.md
  (migrate once → roll web replicas).
- Keep the `secret_ref` indirection as the seam for a future vault (don't build a vault — just ensure
  prod reads secrets from env, never from a committed file, and document the swap point).

**Verify [build]+[test]:** prod settings import + check (`manage.py check --deploy` clean of the things
that are code-fixable; document any remaining warnings that are infra-dependent); the prod image builds;
a test that prod settings fail closed without required env. Commit `BUILD_4 4.1 — prod settings + baked
image + controlled migrations`.

## Phase 4.2 — Metrics, observability & health (the biggest ops gap)

- Add a metrics endpoint (Prometheus-style `/metrics`, gated/secured appropriately) exposing the signals
  that matter: request latency + count by route-class + status, DB connection usage, cache hit/miss,
  Celery queue depth + task success/failure, AI: Groq 429s / budget-exceeded / job status counts /
  TokenLedger usage, and per-tenant request counts (without leaking cross-tenant detail). Use a
  well-supported library (e.g. django-prometheus) if it fits the locked stack; else a small custom
  exporter. Document what each metric means in docs/OBSERVABILITY.md.
- Strengthen the existing health probes: `/healthz` (liveness, cheap) stays; `/readyz` (readiness) checks
  DB (default + replica alias), Redis (broker + cache), and broker reachability — returns structured
  per-dependency status so an LB/orchestrator can drain correctly. Add tests for the degraded responses
  (e.g. simulate cache down → readyz reports it).
- Ensure structured logging (the RequestIDMiddleware correlation) is on every log line and that Sentry
  (opt-in, already with the PII scrubber) captures the new async task failures too (Celery integration).
- Add lightweight dashboards-as-docs: a docs/OBSERVABILITY.md describing the key SLIs (latency, error
  rate, queue depth, DB conns, AI quota) + suggested alert thresholds (so when infra/monitoring is added
  later, the thresholds are already reasoned).

**Verify [test]+[live]:** `/metrics` returns the expected series; `/readyz` reports per-dependency
status incl. a simulated-degraded case; tests for both. Live-hit `/metrics` and `/readyz` on the running
stack and capture samples in PROGRESS.md. Commit `BUILD_4 4.2 — metrics + readiness + observability docs`.

## Phase 4.3 — Optimistic locking & concurrency protection

- Identify the HIGH-CONTENTION entities where last-writer-wins is a real risk (the system-design doc
  notes plain-field PATCHes are LWW; state-machine transitions already 409 on stale status). Candidates:
  goals/KPIs + actuals, review content during draft/edit, succession plan edits, tenant config, JD body
  edits, anything two roles can edit concurrently.
- Add an OPTIMISTIC-LOCKING `version` (integer) on those entities: each update must send the version it
  read; a mismatch → HTTP 409 with a clear "someone else changed this, reload" payload (consistent with
  the existing 409 convention). Do NOT add it everywhere — only contended entities; justify the list in
  DECISIONS.md.
- Ensure the state-machine transitions (which already re-derive from current status → 409) and the new
  version checks compose cleanly (no double-locking confusion). Use `select_for_update` on the default DB
  (router-aware) where a critical section genuinely needs it (e.g. KPI weight-sum validation, approval
  step advance) — keep transactions short.
- Frontend: handle 409 on these forms gracefully (surface "reload, your copy is stale", keep the user's
  unsaved input where feasible). This also tightens the editing UX.

**Verify [test]:** concurrent-update tests on each versioned entity (two writers, second gets 409);
a select_for_update critical-section test (e.g. concurrent KPI actuals can't corrupt the weight sum);
frontend handles 409. Commit `BUILD_4 4.3 — optimistic locking + concurrency protection`.

## Phase 4.4 — Response caching for hot reads

- Identify the hot, read-heavy, safely-cacheable endpoints: entitlement/my-features (already partly
  cached), the org tree/directory, analytics aggregates (already cached — verify), reference/lookup data,
  and any dashboard summary reads. For each, add response/queryset caching in Redis (the cache DB /1,
  `django_redis`) with: tenant-embedded keys (NEVER cache across tenants), a sane TTL, and CORRECT
  INVALIDATION on the writes that change the data (e.g. an entitlement upgrade busts the feature-flag
  cache; an org change busts the tree cache; a new actual busts the relevant analytics aggregate).
- Be conservative: only cache where staleness for the TTL is acceptable and invalidation is clear. Never
  cache anything user/role-specific under a tenant-only key. Never cache HITL/AI pending state in a way
  that hides a fresh human action. Document each cached endpoint + its TTL + its invalidation triggers in
  docs/CACHING.md.
- Make sure cache failures degrade to a live query (cache down → recompute, never error — confirm the
  django_redis IGNORE_EXCEPTIONS posture).

**Verify [test]+[live]:** cache-hit tests (second call doesn't hit the DB — assertNumQueries=0 on the
cached path); invalidation tests (the busting write makes the next read recompute); tenant-isolation of
cache keys; cache-down degrades to a query. Live-check one cached endpoint's hit/miss on the running
stack. Commit `BUILD_4 4.4 — hot-read response caching + invalidation + CACHING.md`.

---

## End of BUILD_4
Write `BUILD_4_REPORT.md`: prod settings/image/migration posture (and what remains as infra), the
metrics/readiness/observability added (with samples), the versioned entities + concurrency tests, the
cached endpoints + invalidation, QUESTIONS/DECISIONS/BLOCKER, test count after. Then proceed to BUILD_5.
