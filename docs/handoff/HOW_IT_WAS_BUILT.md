# How it was built — decisions & testing

The "why" behind the shape of the system, so you can extend it without relearning by trial and error.

## Key decisions (and the reasoning)
- **Shared-DB multi-tenancy, fail-closed.** One database; every row carries `tenant_id`; a tenant-scoped
  model manager filters every query and returns nothing when no tenant is bound (`apps/tenancy/`). Chosen
  over DB-per-tenant for operational simplicity at SME scale; "fail-closed" (not fail-open) means a bug
  leaks *nothing* rather than everything. Tenant is bound by middleware from the JWT.
- **The agent emits action NAMES only; parameters resolve server-side.** `apps/ai/planner.py` asks the
  LLM for an ordered list of allowed action names + a subject hint — never parameters, permissions or SQL.
  Each name maps to a `propose_*` function (`apps/ai/actions.py`) that resolves the real target within the
  caller's scope, and executes only through the same audited `execute_action` gate a human uses.
  *Why: an LLM must never be able to widen scope, invent a target, or forge a write.* Deletion is not a
  registered action at all — a bulk-destructive request is explicitly refused (`apps/ai/agents/chat.py`).
- **One LLM gateway, provider-agnostic.** `apps/ai/gateway.py` is the sole choke point (budget, PII-scrub,
  schema-validation, metering, confidence, no-fabrication). Providers are interchangeable
  (`openai_provider.py` / `groq.py` / `gemini_provider.py`) via `settings.LLM_PROVIDER`, all speaking
  OpenAI-compatible Chat Completions. *Why: swap vendors by config; keep every safety guarantee in one place.*
- **Budget/metering by call-count, atomic across replicas.** Per-tenant `AgentBudget`
  (`apps/billing/packs.py::DEFAULT_AGENT_BUDGETS`) + append-only `TokenLedger` + a deployment-wide
  `LLM_MAX_CALLS` ceiling, reserved atomically via a Redis Lua script (`apps/billing/atomic.py`, EVALSHA +
  fail-open-on-Redis-down). *Why: cap cost per tenant and across the fleet without a race between replicas.*
  (A true $/token cap is a documented follow-up — see `OPEN_QUESTIONS.md`.)
- **HITL everywhere.** Every AI artifact is saved `PENDING_HUMAN_REVIEW`; async agents write an `AIJob`
  the client polls (`apps/ai/services.py`, `apps/ai/tasks.py`). *Why: AI is advisory, and a human is
  accountable for every consequential change.*
- **Async off the request thread.** Heavy AI (review draft, JD, enrich) runs on Celery so a slow model
  never holds a gunicorn worker; chat/planner intent-classification is the only synchronous LLM call, and
  it's AI-throttled + budgeted.
- **Read/write DB router, replica-ready.** `apps/core/dbrouter.py` routes reads→`replica`, writes→
  `default`, falling back to the primary when no replica is provisioned — so adding a real replica later
  is config-only.
- **v1 simplicity as a first-class concern.** Enterprise features are hidden behind one product switch
  (`frontend/src/app/v1.ts`) rather than deleted — see `V1_VS_V2.md`.

## Testing (what protects what, and how to run it)
- **Backend suite** — `pytest-django` + `factory_boy`. Run: `docker compose run --rm web pytest -q`
  (full suite green; a few live-AI-marked tests are deselected by default). Covers models, RBAC, the
  tenant-isolation invariants, the review/approval state machines, the scoring engine, and the AI layer.
- **AI safety / injection matrix** — `apps/ai/tests/test_agent_safety_matrix.py`: capability + scope
  refusals, injection resistance (SQL-in-a-name, hostile session labels), plan-level safety (unknown
  action dropped, LLM params ignored, >5 steps truncated, approve-twice = once), session isolation. Every
  write row asserts the audit log. *This is the guard that the agent can't be talked past.*
- **Provider unit tests** — `apps/ai/tests/test_openai_provider.py`, `test_gemini_provider.py`,
  `test_gateway.py`: parse the provider response shape with `requests.post` mocked (no network); prove
  the 503/degrade path, JSON-mode, error handling, and the global ceiling.
- **Query-budget guards** — `apps/core/tests/test_query_budgets.py` + `apps/testsupport/query_budget.py`:
  every paginated list must be O(1) in rows (no N+1). A `-m large_tenant` test seeds ~1.2k employees.
- **Frontend** — `vitest` (run: `cd frontend && npm test`; ~118 tests) incl. an axe WCAG 2.1 AA guard
  over the Admin Hub screens, the nav-per-role invariant (`app/nav.test.ts`), and the agent plan UI.
  Type-check with `cd frontend && npx tsc --noEmit`.
- **End-to-end smoke** — `scripts/smoke.py` (run via `./scripts/demo_ready.sh`): the six-step journey per
  role + the agent plan→approve flow + the injection refusal beat, over real HTTP.

**Golden rule:** keep both suites green and commit per change. `demo_ready.sh` is the one command that
recreates the backend, seeds, and runs the E2E smoke to a green/red verdict.
