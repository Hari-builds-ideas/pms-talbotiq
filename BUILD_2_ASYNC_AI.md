# BUILD_2 — Move AI workloads to asynchronous Celery workflows

> Read BUILD_0_READ_FIRST.md first. Build 2 of 5. Goal: take AI execution OFF the request thread. Today
> the agent seams (request-ai-draft, feedback close→summarize, succession enrich, JD generate, career
> enrich) call the LLMGateway SYNCHRONOUSLY in the HTTP request, so a slow/recovering Groq call holds a
> gunicorn worker for up to LLM_TIMEOUT(30s)×retries — worker starvation under any AI load. Move them to
> Celery with a poll/callback pattern, WITHOUT weakening HITL, metering, anonymisation, or the graceful
> degradation. This must be fully testable with the FakeLLMProvider — ZERO real Groq calls.

Celery already exists (worker + beat on Redis /0). This build adds AI tasks + a job-status surface.

---

## Phase 2.1 — Design the async AI job model (write to DECISIONS.md first)

- Introduce an `AIJob` concept (a tenant-scoped model): fields for tenant, requesting user, agent_code,
  target object (generic FK or explicit per-agent FK — pick one, justify in DECISIONS.md), status
  (QUEUED → RUNNING → SUCCEEDED → FAILED / DEGRADED), created/started/finished timestamps, the
  GatewayResult summary (confidence, token usage ref to TokenLedger, error_code on failure), and a
  correlation/request id. INSERT/own-scoped reads only; cross-tenant → 404.
- Decide the surfacing pattern (DECISIONS.md): the existing endpoint that used to do the work
  synchronously now ENQUEUES a job and returns `202 Accepted` with a job id (+ the PENDING artifact id if
  one is created up front), and the client POLLS a `GET /api/ai/jobs/<id>` for status/result. (No
  websockets — consistent with the rest of the app, which polls.) Keep it RBAC/scope-bound.
- CRITICAL invariant: the async result MUST land exactly where the sync result did — the AI artifact
  locked PENDING_HUMAN_REVIEW, metered in the TokenLedger, schema-validated, confidence/floor applied,
  anonymised payload for feedback, name-free for succession. The ONLY change is WHEN/WHERE it runs, not
  WHAT it produces or its safety properties.

**Verify [test]:** AIJob model + migration apply/reverse; model-level tenant scoping test. Commit
`BUILD_2 2.1 — AIJob model + async design`.

## Phase 2.2 — The AI Celery task (the core move)

- Create a Celery task (e.g. `apps/ai/tasks.py::run_agent_job`) that takes a job id, loads it
  tenant-scoped, sets RUNNING, calls the EXISTING LLMGateway (unchanged — the gateway already does
  budget→scrub→provider→validate→meter→confidence→PENDING), writes the result onto the target artifact +
  the AIJob, and sets SUCCEEDED/FAILED/DEGRADED. The task must:
  - bind the tenant context inside the worker (the worker has no request — set the tenant contextvar from
    the job's tenant before any ORM access; add a helper + a test that a task CANNOT touch another
    tenant's data),
  - be idempotent / safe to retry (a retried task must not double-meter the TokenLedger or create a
    second artifact — guard with the job status / a dedupe key),
  - honour the existing global ceiling + per-tenant budget reserve + Groq 429 back-off (the gateway does
    this; ensure the reserve happens in the task, and an over-budget/ceiling/NOT_CONFIGURED result lands
    the job as DEGRADED with the structured error, NOT a crash, NOT a fabricated artifact),
  - on hard failure leave the artifact in its pre-AI state (no half-written draft) and the job FAILED.
- Wire Celery retry policy sanely (limited retries with backoff for transient provider errors; NO retry
  for NOT_CONFIGURED/over-budget — those are terminal DEGRADED).

**Verify [test]:** with FakeLLMProvider — a job runs through QUEUED→RUNNING→SUCCEEDED and the artifact is
PENDING + metered; a forced provider error → FAILED + artifact untouched; a NOT_CONFIGURED → DEGRADED +
503-equivalent surfaced; a cross-tenant guard test; a retry-idempotency test (no double meter). Run
Celery in eager mode for the deterministic tests. Commit `BUILD_2 2.2 — run_agent_job Celery task`.

## Phase 2.3 — Convert each AI seam to enqueue (one at a time, each verified)

Convert these from sync to enqueue-and-poll, IN THIS ORDER, each its own commit, suite green between:
1. Reviews `request-ai-draft` (Agent 1).
2. Feedback `close→summarize` (Agent 3) — preserve the anonymised payload + breach check + HRBP_HOLD.
3. Succession `enrich` (Agent 4) — name-free evidence.
4. JD `generate` (JD agent).
5. Career `enrich` (career agent) — advisory-only invariant.
(Agent 2 nudges are deterministic / chat is interactive-read — see 2.5 for whether chat stays sync.)

For each: the endpoint now creates the PENDING placeholder (if applicable) + an AIJob, enqueues the task,
returns 202 + ids; the existing UI flow continues to work because the artifact still ends PENDING for the
human gate. Update the relevant tests from "sync result" to "job enqueued → (eager) → artifact PENDING".

**Verify [test] per seam:** each converted seam: endpoint returns 202 + job id; the (eager) task lands
the artifact PENDING + metered; HITL/anonymity/advisory invariants asserted by a test. Commit per seam,
e.g. `BUILD_2 2.3a — reviews AI draft async`, `…2.3b — feedback summary async`, etc.

## Phase 2.4 — The job-status API + frontend polling

- Add `GET /api/ai/jobs/<id>` (own/scope-bound, tenant-scoped, 404 cross-tenant) returning status +
  result summary + the artifact id; and optionally `GET /api/ai/jobs?target=<id>` to find the latest job
  for an artifact. Add to the RBAC matrix if a new capability is cleaner; else reuse + document.
- Frontend: where the UI used to block on the sync AI call, switch to: fire the request → get 202 →
  show a clear "AI is working…" state → poll the job endpoint (React Query polling/refetchInterval) →
  on SUCCEEDED show the PENDING draft in its HITL gate; on DEGRADED show the calm "AI unavailable / over
  budget — try again / upgrade" state; on FAILED show a recoverable error. This also FIXES the
  "async/janky" review AI UX the redesign audit flagged — make it feel intentional (skeleton/spinner +
  status, not a frozen button).
- Keep the manual/deterministic path always available (AI is assistive, never required).

**Verify [test]+[live]:** job endpoint RBAC/scope tests; frontend build/tsc/lint clean; live-check the
review draft flow end-to-end against the running stack using ONE seeded record (or the FakeLLMProvider
path if you want zero Groq) — fire → 202 → poll → PENDING draft in HITL. Capture in PROGRESS.md. Commit
`BUILD_2 2.4 — AI job-status API + frontend polling UX`.

## Phase 2.5 — Chat decision + cleanup

- Decide (DECISIONS.md) whether AI CHAT stays synchronous (it's short, interactive, 8B, low-latency) or
  also moves async. Default: keep chat SYNCHRONOUS but with a tight timeout + the same graceful
  degradation, since an async chat UX is worse; document the reasoning. Either way it stays read-only,
  RBAC-bound, write-blocked.
- Remove now-dead synchronous AI code paths (or clearly mark them as the deterministic fallback). Ensure
  no endpoint still blocks the worker on a long Groq call except the deliberately-sync chat.
- Confirm the whole AI surface degrades correctly with no key (NOT_CONFIGURED → jobs land DEGRADED / 503
  on chat; deterministic paths work).

**Verify [test]:** a sweep test that no converted seam executes the gateway in-request (e.g. the endpoint
returns before the provider is called — assert via the eager/non-eager distinction or a spy). Commit
`BUILD_2 2.5 — chat decision + sync-path cleanup`.

---

## End of BUILD_2
Write `BUILD_2_REPORT.md`: the async design, each seam converted, the job API + polling UX, the chat
decision, how HITL/metering/anonymity/degradation were preserved (with the asserting tests), Groq usage
(should be ~0 — FakeLLMProvider), QUESTIONS/DECISIONS/BLOCKER entries, test count after. Then proceed to
BUILD_3.
