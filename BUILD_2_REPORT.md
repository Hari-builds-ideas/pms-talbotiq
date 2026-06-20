# BUILD_2 — Async AI — REPORT

**Status: COMPLETE.** All 5 phases implemented, verified, committed, and pushed to
`main`. The five AI seams now run OFF the request thread via Celery; the LLM
never holds a gunicorn worker again. Backend suite **1092 passed, 2 deselected**
(grew from 1090 by the sweep tests); frontend `tsc` + `lint` + `build` clean.
**Zero Groq calls in tests** (FakeLLMProvider throughout); one successful live
call during the end-to-end check.

## The move

The seams already had `@shared_task` workers (they bound the tenant, ran the
gateway, locked the artifact PENDING). What was missing was off-request
orchestration + a pollable status. BUILD_2 added an `AIJob`, a `run_agent_job`
dispatcher, flipped each view from a synchronous call to enqueue-and-202, and a
React polling UX. **WHAT each seam produces and its safety properties are
unchanged — only WHEN/WHERE it runs.**

## Phase-by-phase

**2.1 — AIJob model + async design** (`88fe8c3`)
`AIJob(TenantScopedModel)` — status QUEUED→RUNNING→SUCCEEDED|DEGRADED|FAILED,
loose `target_type`/`target_id` (a correlation record, not a GenericFK — D4),
`requested_by`, `agent_code`, `confidence`, `token_ledger`, `error_code`. 5
tenant-scoping tests. Migration applies/reverses.

**2.2 — run_agent_job dispatcher** (`6ff8fa2`)
Binds the job's tenant in the worker, idempotent terminal-guard, RUNNING →
dispatch by `agent_code` → classify the seam result onto the job. Added
`AgentUnavailable(gateway_status)` so the 5 seams distinguish over-budget
(→ DEGRADED) from a hard provider error (→ FAILED). `AIJob.params` for career's
`target_ref`. 6 tests (FakeLLM): SUCCEEDED+metered-once, provider_error→FAILED
(artifact unpublished), NOT_CONFIGURED→DEGRADED, over-budget→DEGRADED,
cross-tenant→no-op, idempotent (no double-meter).

**2.3a–e — convert each seam** (`5764baf`, `b4c42d5`, `61d835a`, `c2dae33`, `9634b2c`)
Reviews draft, feedback close+summarize (anonymise/breach/HRBP_HOLD preserved in
the worker), succession enrich (deterministic plan intact, name-free), JD generate
(sync 422 inputs check kept), career enrich (advisory). Each view: sync
precondition checks (scope/state/inputs) → enqueue → `202` + job. `run_agent_job`
got a defensive FAILED-catch so an uncaught seam error can't strand a job RUNNING.

**2.4a — job-status API** (`a6d2388`)
`GET /api/ai/jobs/<id>` (own + tenant-scoped, cross-user/cross-tenant → 404) and
`GET /api/ai/jobs?target=<id>`. 5 RBAC/scope tests.

**2.4b — result_id + frontend polling** (`db20b46`)
`AIJob.result_id` (the produced artifact — equals `target_id` for mutate-in-place
seams, the NEW plan/roadmap for create-new). Frontend: `useAIJob` (poll to
terminal) + `useAIAction` (fire→poll→react) + `<AIJobBanner>` (working / calm
DEGRADED / recoverable FAILED), wired across all 5 seam UIs. Fixes the janky
review AI UX the redesign flagged.

**2.5 — chat decision + cleanup** (`<this commit>`)
Chat stays SYNCHRONOUS (D6 — short/interactive; async chat UX is worse), still
RBAC-bound + write-blocked + 503/429-graceful. Sweep test proves no converted
seam runs the gateway in-request (EAGER=False → 202 with the artifact untouched +
nothing metered). Stale "SYNCHRONOUSLY" docstrings updated.

## Invariants preserved (asserted, not assumed)
- **HITL** — every success still locks the artifact PENDING_HUMAN_REVIEW (worker).
- **Metering** — exactly one TokenLedger row per run; a retry/re-run double-meters
  nothing (idempotency test + the seams' own state guards).
- **360 anonymity** — the anonymised payload + breach guard + HRBP_HOLD all run in
  the worker; a breach → DEGRADED (ANONYMITY_HOLD), the summary held.
- **Graceful degradation** — no key → DEGRADED (NOT_CONFIGURED); over budget →
  DEGRADED (BUDGET_EXCEEDED); never a crash, never a fabricated artifact.
- **Deterministic fallback** — baseline plans/roadmaps and the manual paths are
  untouched and always available.

## Verification ledger
- **[test]** 1092 passed, 2 deselected; 13 new AI tests across model/dispatcher/
  job-API/sweep, all on FakeLLMProvider (zero Groq).
- **[build]** frontend tsc + lint + production build clean.
- **[live]** running stack (after `restart web celery-worker`): a DRAFT review
  fired → `202` QUEUED (gunicorn returned immediately) → Celery worker →
  SUCCEEDED → review PENDING_HUMAN_REVIEW (HITL intact). Job-status API + org
  tree + reviews list all live-verified.

## Notes / follow-ups
- Dev stack: gunicorn + celery-worker don't autoreload — a deploy restart picks up
  task code (not a code issue).
- Groq remains on the free tier; production needs the key plugged in (Hari's
  action) — async then keeps a slow/recovering Groq off the request thread.

Next: **BUILD_3 — Atomic limits & DB router**.
