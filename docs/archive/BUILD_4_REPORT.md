# BUILD_4 — Prod Ops, Concurrency & Cache — REPORT

**Status: COMPLETE.** All 4 phases implemented, verified, committed, pushed.
Backend suite **1123 passed, 2 deselected**; frontend `tsc`+`lint`+`build` clean;
**zero LLM calls**. Repo-level only — no infra provisioned.

## Phase-by-phase

**4.1 — Prod settings + baked image + controlled migrations** (`3089af1`)
`config/settings/prod.py` was already fail-closed (DEBUG off, HSTS, secure
cookies, no-default SECRET_KEY/ALLOWED_HOSTS, proxy SSL header); added
`XFrameOptionsMiddleware` so `check --deploy` is CLEAN under prod settings.
`docker-compose.prod.yml`: `config.settings.prod`, a BAKED image
(`INSTALL_DEV=false`, no source mount), a SEPARATE cache Redis (allkeys-lru) from
the broker Redis (noeviction), `${VAR:?}` fail-closed secrets. Controlled
migrations: a one-shot `migrate` service runs ONCE; web/workers wait on it and
never auto-migrate (no N-replica race). Prod image builds; compose verified
fail-closed. Deploy order in the RUNBOOK.

**4.2 — Metrics + readiness + observability** (`7b9c6fc`)
`/metrics` — a small custom Prometheus exporter (no new dep): cross-worker
request counters (cache-backed, by route/status) + live aggregates (Celery queue
depth, AI jobs by status, token usage by agent, tenants). Token-gated +
fail-closed (unset token → 404). `/readyz` gained a `DatabaseReplica` check;
Sentry already wires the Celery integration. `docs/OBSERVABILITY.md` documents
the probes, every metric, and the SLIs + alert thresholds. Live-verified.

**4.3 — Optimistic locking + KPI weight critical section** (`b503b92`)
A server-controlled `version` on `Goal` + `TenantConfig` (the clearest plain-field
LWW cases): a stale version on update → 409 STALE_VERSION; omitting it still works.
Review/JD/succession excluded with justification (single-editor / lifecycle-gated).
The KPI weight-sum invariant (= 100.00) is now guarded by `SELECT ... FOR UPDATE`
on the goal across the three weight paths, so concurrent edits can't both pass.
Frontend: the tenant-config form sends the version it read and keeps the user's
input on a 409.

**4.4 — Hot-read caching: degrade-not-error** (`<this commit>`)
The hot reads were already cached (entitlement/rate-limits/feature-flags 300s, org
tree 600s, analytics aggregate) with tenant keys + write-time invalidation — so no
speculative new caches. The real gap was the degradation posture:
`IGNORE_EXCEPTIONS=True` (+ logged) so a Redis outage recomputes from the DB rather
than 500ing. `docs/CACHING.md` documents each cached read + TTL + invalidation.

## What this closes (system-design ops gaps)
- No metrics/observability → `/metrics` + `/readyz` per-dependency + OBSERVABILITY.md.
- Auto-migrate-on-every-web-boot race → one-shot migrate, web waits.
- Plain-field PATCH is LWW → optimistic `version` on the contended entities.
- Cache as a hard dependency → degrade-to-DB on outage.

## Invariants preserved
Tenant isolation (cache keys + metrics aggregates carry no cross-tenant detail);
RBAC/HITL untouched; the audit log still INSERT-only to `default`; AI degradation
+ deterministic fallbacks intact.

## Verification ledger
- **[test]** 1123 passed, 2 deselected; new: 3 prod-settings, 4 metrics, +2 readyz,
  3 optimistic-locking, 4 caching. Zero Groq.
- **[build]** prod image builds; frontend tsc+lint+build clean.
- **[live]** `/readyz` 7/7 up incl `DatabaseReplica`; `/metrics` real series
  (request counts, queue depth, AI jobs, token usage, tenants).

## Remaining (Hari / infra, out of series)
TLS-terminating proxy in front; managed MySQL/Redis (point the prod compose env
at them); a Prometheus scraper + alerting wired to the documented SLIs; a real
read replica (`DB_REPLICA_HOST`). All config, no code.

Next: **BUILD_5 — Web UX completion**.
