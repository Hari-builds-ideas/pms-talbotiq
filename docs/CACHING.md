# CACHING — Talbotiq PMS (BUILD_4)

Hot, read-heavy reads are cached in Redis (the cache DB `/1`, `django_redis`).
Every cached value is keyed with the tenant id (`tenant_cache_key` →
`tenant:<id>:…`) so a value is **never** served across tenants, has a TTL, and is
**busted by the writes that change it**. Caches are an optimisation, never a hard
dependency: with `IGNORE_EXCEPTIONS=True` a Redis outage degrades to a live DB
query (logged via `DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS`), it never 500s.

## Cached reads

| Read | Key (per tenant) | TTL | Invalidated by |
|---|---|---|---|
| Entitlement | `…:entitlement` | 300s | any entitlement write (upgrade / seat / pack change) → `invalidate_tenant_cache(tenant)` |
| Rate-limit map | `…:rate_limits` | 300s | same (the map derives from the entitlement) |
| Feature flags | `…:feature_flags` | 300s | same |
| Org tree (`{nodes,edges,roots}` + headcount/vacancy rollups) | `…:org_tree:full` | 600s | any org write — position create/fill/close, JD link, reporting-line change → invalidate the `org` namespace |
| Department analytics aggregate | `…:analytics:dept:<head>:<cycle>` | 300s | a Module-2 score recompute → `invalidate_analytics_cache(tenant)` (signal-wired) |

The org tree is cached ONCE per tenant as the full structure; each scope (OWN /
TEAM / TENANT) is a cheap in-memory filter over that one entry — no per-manager
key explosion. The analytics aggregate keeps its min-cohort suppression (the
cached value is already suppressed where required).

## Rules we hold to

- **Tenant-embedded keys only** — never a tenant-agnostic key for tenant data.
- **No user/role-specific data under a tenant-only key** — the org tree is cached
  tenant-wide because the per-scope view is derived after the cache read, not
  baked into the cached value.
- **Never cache HITL/AI pending state** in a way that hides a fresh human action —
  review/feedback/succession PENDING artifacts are read live, not cached.
- **Conservative TTLs** (300–600s) where staleness for that window is acceptable
  and the invalidation trigger is unambiguous; otherwise not cached.
- **Degrade, never error** — `IGNORE_EXCEPTIONS=True`; a cache miss/outage
  recomputes from the DB.

## Tested (apps/billing/tests/test_caching.py)

- a cache HIT does zero DB queries (`django_assert_num_queries(0)`);
- the busting write (an upgrade) INVALIDATES — the next read reflects it
  immediately, not after the TTL;
- keys are TENANT-ISOLATED — one tenant's cached value is never served to another;
- a cache OUTAGE (Redis unreachable) degrades to a live DB query, no 500.

## NOT cached on purpose

Per-request lists already made O(1) by BUILD_1's `select_related`/indexes
(reviews, goals, positions, …) are fast enough uncached and would need per-filter
invalidation; the atomic budget/throttle counters are live Redis counters (BUILD_3),
not TTL caches. Request-latency/DB-conn metrics are exposed via `/metrics`, not cached.
