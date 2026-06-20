# BUILD_3 — Redis-backed atomic budgets & rate limiting; DATABASE_ROUTERS for read replicas

> Read BUILD_0_READ_FIRST.md first. Build 3 of 5. Two related correctness-under-concurrency items:
> (A) make the per-tenant budget reserve + the throttles ATOMIC across replicas (today the
> check-then-reserve is not strictly atomic — two replicas can both pass at the limit edge,
> billing/services.py:379), and (B) add a DATABASE_ROUTERS read/write split that is correct and tested
> against the SINGLE existing DB now, so the day a real replica is provisioned it's a config change, not
> a code change. No replica is created in this build (infra, out of scope) — only the router code.

ZERO LLM calls. Use FakeLLMProvider where an AI seam is touched.

---

## Phase 3.1 — Atomic per-tenant AI budget reserve

- Replace the non-atomic check-then-reserve in the budget path with an ATOMIC Redis operation. Use a
  Lua script (the code already notes this as the upgrade path) that does the check + increment + TTL in
  one round trip, so concurrent reservers cannot both succeed past the cap. Keys must embed tenant id
  (preserving tenant isolation of counters).
- The atomic reserve must: return success/failure deterministically at the boundary; respect daily +
  monthly windows (whatever AgentBudget tracks today); set/refresh the correct TTLs; and on a downstream
  provider failure, RELEASE/refund the reservation so a failed call doesn't permanently consume budget
  (decide refund-on-failure in DECISIONS.md; default: refund on provider error, keep consumed on a
  successful metered call). Keep the existing TokenLedger metering as the source of truth for actual
  usage; the Redis counter is the fast pre-check.
- Keep behaviour identical to today at the API surface: over-budget → 429-class result + upgrade_hint;
  the gateway never raises.

**Verify [test]:** a concurrency test that fires N simultaneous reserves at a cap of M (M<N) and asserts
EXACTLY M succeed (use threads or simulated concurrent calls against a real/fakeredis); a refund-on-
failure test; daily/monthly window + TTL tests; tenant-isolation of the counter (tenant A's usage never
affects tenant B). Suite green. Commit `BUILD_3 3.1 — atomic per-tenant budget reserve (Lua)`.

## Phase 3.2 — Atomic throttling + the global AI ceiling

- Apply the same atomicity to the DRF `TenantThrottle`/`UserThrottle` counters and the global AI call
  ceiling (`LLM_MAX_CALLS`, the Redis counter in groq.py): make increment+window atomic so concurrent
  requests can't overshoot the limit across replicas. Preserve the per-request rate resolution from
  `rate_limits_for(tenant)` (so an entitlement upgrade still lifts limits everywhere).
- Confirm `AIThrottle` is attached to EVERY AI route (the system-design doc flagged it as per-view —
  verify and, if any AI route is missing it, attach it). Document the final list of throttled AI routes
  in DECISIONS.md.
- Keep `AnonRateThrottle` on the login/auth surface; verify it can't be trivially bypassed across
  replicas now.

**Verify [test]:** concurrency test on a throttle (N concurrent, limit M → exactly M pass, rest 429);
the global ceiling can't be overshot by concurrent callers; every AI route is throttled (a test that
enumerates AI routes and asserts a throttle class is present). Commit `BUILD_3 3.2 — atomic throttles +
global AI ceiling + AIThrottle coverage`.

## Phase 3.3 — DATABASE_ROUTERS (read/write split, replica-ready)

- Implement a `DATABASE_ROUTERS` class that routes reads to a `replica` alias and writes to `default`,
  with the correct safety rules:
  - `db_for_write` → `default`; `db_for_read` → `replica`.
  - READ-AFTER-WRITE correctness: within a request that has written (or a transaction), reads must go to
    `default` to avoid replica lag serving stale data. Implement this (e.g. pin to `default` for the rest
    of a request after any write, or for atomic blocks) and TEST it.
  - `allow_relations` permits relations across the two (same DB, replica is a copy).
  - `allow_migrate` → only on `default` (never migrate the replica).
- Configure `DATABASES` so that, WITH NO REPLICA CONFIGURED (today), the `replica` alias FALLS BACK to
  the same connection as `default` (read the replica DSN from env; if unset, alias `replica` = `default`).
  So the router is active and tested now, and provisioning a replica later is purely setting the env DSN
  — no code change. Document this in DECISIONS.md and docs/RUNBOOK.md.
- Be careful with: the audit log (INSERT-only, must write to default), Celery tasks (set the right DB
  context), and any `select_for_update` (must hit default).

**Verify [test]:** router unit tests (reads→replica alias, writes→default, migrate only on default);
a read-after-write test (after a write in a request/transaction, a subsequent read in the same unit goes
to default); the full suite green with the router active and replica=default fallback; an explicit test
that with a distinct (even if same-host) `replica` alias configured, reads route there. Commit
`BUILD_3 3.3 — DATABASE_ROUTERS read/write split (replica-ready, default fallback)`.

## Phase 3.4 — Connection sizing & resilience

- Make the DB connection math explicit + configurable: surface the `replicas × workers × threads +
  celery + headroom` sizing (referenced at base.py:147-150) as documented settings/comments, and ensure
  `CONN_MAX_AGE` + `CONN_HEALTH_CHECKS` are correct for both `default` and `replica`. Add a note in
  docs/RUNBOOK.md on setting MySQL `max_connections` to match the chosen replica/worker counts (this is
  the documented ceiling, not a code change to the DB).
- Ensure Celery DB usage closes connections appropriately (long-lived workers shouldn't leak conns); add
  the standard close-old-connections handling if missing.

**Verify [test]+[build]:** settings load correctly for default + replica; a smoke that the app + a Celery
task both run with the router active. Commit `BUILD_3 3.4 — connection sizing + resilience`.

---

## End of BUILD_3
Write `BUILD_3_REPORT.md`: the atomic-limits implementation + the concurrency tests proving exactly-N,
the router design + the read-after-write handling + the replica=default fallback (so it's live now and
replica-ready later), the connection-sizing notes, QUESTIONS/DECISIONS/BLOCKER, test count after. Then
proceed to BUILD_4.
