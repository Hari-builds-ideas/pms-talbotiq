# AI_ROBUSTNESS — PROD_D: production-safe AI under load

Grounded in `apps/ai/gemini_provider.py`, `apps/ai/tasks.py`, `apps/ai/services.py`,
`config/settings/base.py`. Builds on the earlier AI-hang fix (soft/hard job time
limits, FIX-ROUND).

## 1. PROVIDER_ERROR — root cause

`PROVIDER_ERROR` is the gateway's label for any `LLMProviderError` raised by the
provider. In the Gemini path the raises are: a non-JSON body, or a non-2xx HTTP
status. The repeated PROVIDER_ERROR + 10–16 s runtimes point at **transient
transport failures that were NOT being retried**, plus a **read timeout too tight
for the "thinking" (BEST) model**:

- **5xx not retried (the main bug).** `_post_with_backoff` retried connection
  errors and `429`, but a `5xx` (`500/502/503/504` — common under provider load)
  fell through to `raise LLMProviderError` on the **first** occurrence → an
  immediate PROVIDER_ERROR with no second chance.
- **Read timeout = 30 s for a thinking model.** The BEST model (human-read agents)
  runs 10–16 s normally; a spike past 30 s tripped the read timeout → a
  `RequestException` → (previously) a fail. The 10–16 s runtimes are the *slow but
  successful* calls sitting right under that ceiling.
- **Free-tier quota (secondary).** On a free/low tier, concurrent drafts hit the
  provider RPM limit → `429`. That path already retried with `Retry-After`, but
  after the cap still surfaces as PROVIDER_ERROR — a *provisioning* limit, not a
  code bug (size the tier / dollar cap — see §7).
- A missing key is **not** this: no key → `configured=False` → a clean 503, never
  PROVIDER_ERROR (and never fabrication).

## 2. Fixes applied (this build)

- **Retry transient 5xx** with backoff + jitter (`gemini_provider._post_with_backoff`).
- **Jitter on every backoff** (`_sleep`) so many concurrent jobs don't retry in
  lockstep (thundering herd).
- **4xx fails fast** — a `400/401/404` (bad model id, bad key) won't fix on retry,
  so it raises immediately instead of burning the retry budget.
- **Separate, larger read timeout** — new `LLM_READ_TIMEOUT` (default **60 s**,
  env-tunable); connect stays ≤10 s. A slow thinking model no longer times out
  spuriously; the AI-job soft limit (120 s) remains the hard backstop.
- Tests: `apps/ai/tests/test_ai_robustness.py` (6) — 5xx-then-success, 429 +
  Retry-After, give-up-after-cap → LLMProviderError, 4xx fail-fast, connection
  retry, configurable read timeout.

## 3. AI is OFF the request thread (confirmed)

- Heavy agents (review / JD / feedback / succession / career drafts) go through
  `enqueue_agent_job` → creates a tenant-scoped `AIJob` (QUEUED) → `run_agent_job.delay()`
  (Celery). The web request returns immediately; the client polls the job. A slow
  or failing Gemini call can **never** block a gunicorn worker.
- The **only** synchronous LLM call is chat/planner intent classification — it is
  AI-throttled (`AIThrottle`) and timeout-bounded by the same provider transport.

## 4. Model map (reliability + latency)

`GEMINI_MODEL_MAP` (settings) already splits **FAST vs BEST**, all env-overridable:
- **FAST** (`GEMINI_MODEL_FAST`, default `gemini-2.5-flash`) — chat + the lighter,
  most-frequent agents. Picked so normal enterprise volume doesn't rate-limit.
- **BEST** (`GEMINI_MODEL_BEST`, default `gemini-pro-latest`) — ONLY the five
  human-read agents (review/feedback/succession/jd/career), where quality is read
  by a person.
- A single `GEMINI_MODEL` env var forces one model everywhere. Per-agent overrides:
  `LLM_MODEL_REVIEW`, `LLM_MODEL_CHAT`, etc.
- **Go-live note:** confirm the deploy key's project can access the chosen model
  ids (a blocked id → 400 → now a fast, honest failure, not a hang). Swap via env
  if the tier exposes different names.

## 5. Graceful degradation (never a dead spinner, never fabrication)

- Any provider failure → `LLMProviderError` → gateway records **PROVIDER_ERROR** →
  `_classify` marks the job **FAILED/DEGRADED**; the client's `useAIJob` poll
  resolves to the retry banner (`AIJobBanner`), never an infinite spinner.
- A hung socket / starved worker → the **soft time limit** (120 s) fires →
  `run_agent_job` marks the job `FAILED`/`TIMEOUT` honestly.
- An unexpected raise in any seam → caught in `run_agent_job` → `FAILED` (job never
  stranded RUNNING). No fabricated/placeholder content is ever passed off as a real
  draft; the deterministic/manual path still works when AI is down (503).

## 6. Concurrency / load behaviour

- Jobs **queue** in Celery and process at the worker concurrency — a burst of N
  review drafts fans into the worker pool, not the web tier, so `/healthz` and
  every non-AI endpoint stay fast regardless of AI load.
- Budgets/throttles hold **atomically across replicas** (Redis Lua reserve,
  `apps/billing/atomic.py`) — a burst can't overshoot the per-tenant budget or the
  deployment-wide `LLM_MAX_CALLS` ceiling.
- Under a provider brown-out, each job independently retries (jittered) then
  degrades per §5 — the failure is contained per-job, never cascading.

## 7. Honest scale report — code-ready vs needs-provisioning

**Code is ready** (this build + prior): async offload, per-agent model map,
retry/backoff/jitter + Retry-After, separate read timeout, graceful degrade,
atomic cross-replica budgets, soft/hard job limits.

**Needs provisioning (deployment team):**
- **Managed Redis** — broker (`noeviction`, so queued AI jobs never drop) + a
  separate LRU cache instance. The single compose Redis is a dev SPOF.
- **Celery worker autoscaling + separate queues** — isolate AI jobs from
  side-effect tasks so a slow-model burst can't starve notifications. Not automated
  today (HPA / managed autoscaler + a distinct queue).
- **Right LLM tier + a provider-side dollar cap** — set `LLM_MAX_CALLS` to a real
  prod value (the default `500` is a dev/QA number) or `0` + a hard $-cap on the
  key. The app enforces call-count budgets; a true $/token cap from `TokenLedger`
  is a documented follow-up.
- **A load test** at target concurrency before onboarding a 5k–15k-employee tenant.

**Bottom line:** the AI will not freeze, crash, or fabricate under load as built —
failures degrade to an honest retry state. Sustained *throughput* at real scale is
a provisioning exercise (managed Redis + worker autoscaling + the right tier),
not a code gap.
