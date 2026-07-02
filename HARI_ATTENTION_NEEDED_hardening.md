# HARI_ATTENTION_NEEDED — backend hardening items deferred (File E)

Two File E items were **not attempted** this overnight run — deliberately, to protect the "never push
red" rule under the run's time cap after Files A + B + E4/E5 landed. Neither is blocked; both are
backend-only and testable. They want a careful, dedicated pass (not a tired end-of-run change to the
metering / deploy hot paths).

## E2 — controlled migration step
- **Goal:** run migrations as a one-shot deploy job / management command, NOT on every worker boot
  (N replicas racing `migrate`).
- **Why deferred:** touches boot/deploy behavior; wants its own idempotency test + a compose doc.
- **Next step:** a `deploy_migrate` management command invoked once per deploy; workers boot with
  `--no-migrate`; test: workers boot without migrating + migrate is idempotent.

## E3 — atomic budget/throttle across replicas
- **Goal:** move per-tenant/per-user AI budgets to Redis-atomic counters (Lua) so multi-replica
  deploys don't drift past the budget.
- **Why deferred:** touches the metering hot path (`apps/billing/services.check_and_reserve_budget`);
  a subtle change wants a focused review + a 100-concurrent test (can't exceed the budget by >0).
- **Next step:** a Lua reserve-or-reject script; test with concurrent requests asserting the ceiling
  holds exactly.

## What DID land in File E
- E4: `apps/core/tests/test_seed_demo_rich.py` (idempotency, weights=100, Akhil On Track, ACME-only).
- E5: `PROD_READINESS_STATUS.md`.
- E1 (N+1) was found already enforced by the existing `[query-budget] … [BOUNDED]` tests + existing
  `select_related` in list views — marked DONE with reference, not re-done.
