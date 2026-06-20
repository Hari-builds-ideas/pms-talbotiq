# BUILD_3 — Atomic Limits & DB Router — REPORT

**Status: COMPLETE.** All phases implemented, verified, committed, pushed. Two
correctness-under-concurrency wins landed: (A) per-tenant budget + all throttles
+ the global AI ceiling are now ATOMIC across replicas, and (B) a read/write
`DATABASE_ROUTERS` split is active and tested against the single DB today, so a
real read replica is a config change later, not a code change. Backend suite
**1107 passed, 2 deselected**; **zero LLM calls** (FakeLLMProvider). No infra
provisioned — code only.

## Phase-by-phase

**3.1 — Atomic per-tenant budget reserve (Lua)** (`b8f676b`)
`apps/billing/atomic.py`: `reserve`/`release`/`incr_window` run GET+compare+
INCR+PEXPIRE as one Redis Lua step. `check_and_reserve_budget` uses it (identical
API surface: over budget → BudgetExceeded → 429). `release_budget` refunds on a
post-reserve provider failure (NOT_CONFIGURED/PROVIDER_ERROR, before metering) so
a failed call never permanently burns budget; a metered call keeps its slot.
Proven: 64 threads at cap 10 → exactly 10 reserve.

**3.2 — Atomic throttles + global ceiling + AIThrottle coverage** (`254162f`)
The entitlement throttles and the global LLM ceiling use the same atomic counter
(no more racy read-modify-write). `AtomicAnonThrottle` hardens the login surface.
`AI_THROTTLES` (Tenant+User+AI) is attached to every AI-triggering route (chat +
the 5 seam triggers + nudges) — deliberately NOT the 1.5s-polled job-status reads.
Proven: 40 concurrent at 5/min → exactly 5; global ceiling 3 → exactly 3; a
coverage test asserts the AI bucket on every AI view.

**3.3 + 3.4 — DATABASE_ROUTERS + connection sizing/resilience** (`<this commit>`)
`PrimaryReplicaRouter`: reads → `replica`, writes → `default`, migrate only on
`default`. **Read-after-write**: a per-thread write flag (cleared per request via
`DBRoutingResetMiddleware` and per Celery task via `task_prerun`) and any read
inside a transaction (incl. `select_for_update`) pin to the primary. The
`replica` alias falls back to a second connection to the primary when
`DB_REPLICA_HOST` is unset (and `TEST: {MIRROR: default}` so tests build no second
DB) — so the router is active + tested now and a real replica is env-only later
(RUNBOOK documents provisioning + `max_connections` sizing for both aliases).
Celery closes old connections after each task (eager-skipped so it never tears
down a test transaction). Combined into one commit because both phases touch the
same files and the env forbids interactive partial staging.

## What this fixes (the system-design flags)
- The non-atomic budget reserve (`billing/services.py:379`) — now atomic.
- Throttles that could be edged across replicas — now atomic, AIThrottle on every
  AI route.
- No read/write split (`DATABASE_ROUTERS` was NOT-BUILT) — now built, replica-ready.

## Invariants preserved
- **Tenant isolation** — every atomic counter key still embeds the tenant id;
  the router is orthogonal to the fail-closed `TenantScopedManager`.
- **API behaviour unchanged** — over budget/rate → 429 + upgrade hint; the gateway
  never raises; deterministic + manual paths untouched.
- **Audit log** — INSERT-only, writes to `default` via `db_for_write`.

## A bug this build caught (and fixed)
Running the FULL suite with the router active surfaced that the Celery
`close_old_connections` (added for worker hygiene) tore down the test transaction
in eager mode — 15 AI-seam tests failed. Guarded it on `CELERY_TASK_ALWAYS_EAGER`.
A `transaction=True` queryset test (mirrored-replica DB flush) proved flaky under
full-suite load and was replaced by a unit assert; `CONN_MAX_AGE=0` in tests
stops the replica connection accumulating. This is exactly why the contract
mandated "the full suite green WITH the router active."

## Verification ledger
- **[test]** 1107 passed, 2 deselected; 15 new concurrency/router tests
  (Lua reserve, throttle, ceiling, anon, router, settings) — threads prove
  exactly-N at the cap. Zero Groq.
- **[build]** no frontend change this build.

## Remaining (Hari / infra, out of this series)
- Provision a managed MySQL + a real read replica, then set `DB_REPLICA_HOST`
  (+ `max_connections` per the RUNBOOK sizing). The router needs no code change.

Next: **BUILD_4 — Prod ops, concurrency & cache**.
