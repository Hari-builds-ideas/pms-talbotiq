# HARI_ATTENTION_NEEDED — backend hardening (E2/E3) — ✅ RESOLVED (File I)

Both deferred items landed in **OVERNIGHT_I** (backend-only, auto-merged to `main` on
green). Nothing outstanding here.

## E2 — controlled migration step ✅
`python manage.py deploy_migrate` (`apps/core/management/commands/deploy_migrate.py`)
wraps `migrate` in a MySQL **advisory lock** (`GET_LOCK`): the first caller migrates;
a concurrent racer finds the lock held and exits 0 (no-op). Idempotent. The prod
compose `migrate` service now runs `deploy_migrate`; web/workers boot WITHOUT
migrating. Tests: `apps/core/tests/test_deploy_migrate.py` (5 — lock/skip/release +
real GET_LOCK round-trip + real idempotent double-run).

## E3 — atomic Redis-Lua budget ✅
The per-tenant budget reserve was already a Redis **Lua** step (`billing/atomic.py`);
this pass added **EVALSHA + EVAL/NOSCRIPT recovery** (survives a Redis restart /
`SCRIPT FLUSH`), a **soft fail-open fallback** when Redis is down (no 500), and a
`pms_ai_budget_total{outcome}` metric (`reserved`/`over`/`redis_down`). Tests
(`apps/billing/tests/test_atomic_budget.py`): 100 concurrent vs a 20-cap → exactly 20
succeed; EVALSHA recovery after `SCRIPT FLUSH`; redis-down soft-degrade + metric;
over-cap metric.

See `docs/SYSTEM_DESIGN_AND_READINESS.md` §3.1 + the Deploys row (both marked BUILT).
