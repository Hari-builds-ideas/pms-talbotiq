# PROD_D_AI_ROBUSTNESS.md — make the AI production-safe under real load

**Goal:** the AI must not break the product under real concurrent users. The logs show repeated Gemini
`PROVIDER_ERROR` and 10–16s runtimes. Diagnose, harden, and prove it degrades gracefully and stays
responsive under load. It must never freeze the app, never crash, never fabricate.

## 1. Diagnose PROVIDER_ERROR (root cause first)
- Investigate why Gemini returns PROVIDER_ERROR in the run_agent_job logs: is the model id valid for this
  key/tier? rate-limit/quota (429)? timeout too tight for a "thinking" model? bad payload/JSON mode?
  Report the actual cause with evidence.

## 2. Confirm AI is fully off the request thread
- Verify heavy AI (review/JD/feedback/succession/career drafts, summaries) runs in Celery workers, not in
  the web request — so a slow/failing Gemini call can NEVER block a gunicorn worker. Confirm which calls
  are synchronous (chat/planner intent classification) and that they are AI-throttled + timeout-bounded.
  Report the finding.

## 3. Right model for the job (reliability + latency)
- Configure the model map for production sanity: a FAST model (e.g. a Gemini flash model) for chat and the
  lighter/most-frequent agents; a stronger model ONLY where output quality truly needs it. Make every
  model id env-overridable (existing LLM_MODEL_* / GEMINI_MODEL_* pattern). Pick defaults that don't
  rate-limit on a normal enterprise tier. Document the choice.

## 4. Retry + backoff + rate-limit handling
- On transient Gemini errors (timeouts, 5xx, 429): retry with exponential backoff, honoring any
  Retry-After. Cap retries; after the cap, fail gracefully (below). Make sure retries don't stack up and
  exhaust workers.

## 5. Graceful degradation (never a dead spinner, never fabrication)
- Any AI failure returns a clean, honest state to the UI: a "couldn't generate — try again" message with
  the retry affordance, never an infinite spinner, never a crash, never fabricated/placeholder content
  passed off as a real draft. Confirm the job polling resolves to a visible FAILED state and the UI shows
  it. The deterministic/manual path must still work when AI is down.

## 6. Concurrency / load check
- Add a check that fires many AI jobs concurrently (e.g. N review drafts at once) and assert: the web tier
  stays responsive (health/other endpoints still fast), jobs QUEUE and process through workers rather than
  crashing or blocking, budgets/throttles hold atomically, and failures degrade per #5. Report the result.

## 7. Honest scale report
- State plainly whether it will hold under real load as-is, and what INFRA is still needed for true scale:
  managed Redis (broker noeviction + cache), Celery worker autoscaling + separate queues (AI vs side
  effects), and the per-tenant budget/provider dollar-cap. Distinguish "code is ready" from "needs
  provisioning" (this is the deployment team's part).

## Rules
- Never weaken HITL/budgets/throttles. Never fabricate on failure. Keep tests green; add tests for retry,
  graceful-fail, and the concurrency behavior.

## Done when
- PROVIDER_ERROR root cause found + addressed; AI confirmed off the request thread; sensible per-agent
  model defaults (configurable); retry/backoff + rate-limit handling; guaranteed graceful degrade;
  a passing concurrency check; and an honest scale/infra report. Logged in PROD_PROGRESS.md.
