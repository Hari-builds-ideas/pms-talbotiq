# System Overview — what was built

## The apps (backend, `apps/<name>/`)
**Foundations**
- `tenancy` — the multi-company engine. Every model inherits `TenantScopedModel`; the tenant-scoped
  manager filters every query by `tenant_id` and **fails closed** (no tenant bound → returns nothing).
- `identity` — users, JWT login (simplejwt), MFA (TOTP, `django-otp`), OIDC/OAuth + SAML 2.0 SSO
  (`apps/identity/saml/`). Email is unique **per tenant**.
- `rbac` — four roles (Employee → Manager → HRBP → Admin) checked **server-side** on every endpoint
  (`apps/rbac/`, `RBACMixin`, capability matrix).
- `audit` — an **append-only** log (insert-only; no update/delete) of every important action.

**Performance**
- `cycles` — performance periods + the deterministic scoring engine (goals + KPI results → a
  cohort-relative T-score + risk band).
- `goals` — weighted goals + KPIs; a person's active goal weights sum to exactly 100.
- `reviews` — review state machine (Draft → AI Drafting → Pending Human Review → Approved → Finalized);
  a review can never finalize without a recorded human approver.
- `feedback` — 360° feedback; anonymised, min-volume-gated; AI summaries pass a human release gate.
- `approvals` — sequential/parallel approval workflows with escalation.

**People & planning** — `org` (org chart), `succession` (+ nine-box; *hidden in v1*), `career`
(roadmaps; *hidden in v1*), `jd` (AI job-description generator + library).

**AI** — `ai`: the LLM gateway + agents (see below).

**Business & ops** — `billing` (feature packs STARTER/FULL_AI, seats, per-tenant AI budgets +
`TokenLedger`), `integrations` (Slack/Jira seams — *scaffolded, not connected*), `analytics`
(trends/cohorts/calibration — calibration *hidden in v1*), `administration` (users, tenant config),
`core` (health `/healthz` `/readyz`, Prometheus `/metrics`, the demo seeder, the `deploy_migrate` command).

## The AI layer (`apps/ai/`) — the heart of the product
- **One gateway.** Every LLM call goes through `apps/ai/gateway.py::LLMGateway.run(...)`. On each call it:
  resolves the configured provider → reserves the per-tenant budget → PII-scrubs the prompt → calls the
  model in a trace span → validates the output against the agent's schema (`schemas.py`) → meters usage →
  attaches a confidence score → returns a structured result (never raises).
- **Provider-agnostic.** `settings.LLM_PROVIDER` picks the class: `apps/ai/openai_provider.py`,
  `apps/ai/groq.py`, or `apps/ai/gemini_provider.py` (all OpenAI-compatible Chat Completions). **Gemini is
  the configured provider for the demo** — it runs a two-model split (`gemini-2.5-pro` for the human-read
  agents, `gemini-2.5-flash` for chat; both env-overridable via `GEMINI_MODEL_BEST`/`_FAST`). Default
  (no key) is `NotConfiguredProvider` → agents return a clean 503 and **never fabricate** until a key is
  set. Hari's whole action is pasting `GEMINI_API_KEY` into `.env` (or the Render dashboard).
- **Agents** (`apps/ai/agents/`): review draft (agent1), KPI nudges (agent2, deterministic — no LLM),
  360 summary (agent3, name-free), succession narrative (agent4, name-free), career roadmap, JD generator,
  meeting summary, review-quality flags, stale-goal nudge, NL search, chat classifier.
- **The agent (plan → approve).** `apps/ai/planner.py` + `apps/ai/actions.py`: the LLM emits an ordered
  list of **action NAMES only**; every parameter is resolved deterministically **server-side** within the
  caller's scope; each step executes only on an explicit human Approve through the audited
  `execute_action` gate. Heavy agents run **async** on Celery (`enqueue_agent_job` → `run_agent_job`).

## Request flow (how a request moves)
```
Browser (React SPA, frontend/)                      Django + DRF (apps/)
  │  JWT in Authorization header                       │
  ▼                                                    ▼
nginx / Vercel proxy ── /api ──► gunicorn (WSGI) ─► RBACMixin (role check, server-side)
                                                    │
                                                    ├─ TenantMiddleware binds tenant_id (fail-closed)
                                                    ├─ view → tenant-scoped manager (tenant filter)
                                                    └─ AI? → LLMGateway.run → provider → schema-validate
                                                              │  heavy → Celery task (AIJob), client polls
                                                              ▼
                                                       result saved PENDING_HUMAN_REVIEW (HITL)
MySQL (tenant-scoped rows) · Redis (broker /0, cache /1, sessions /2) · AuditLog (append-only)
```

## Invariants a newcomer must NOT break (and why)
1. **Tenant isolation, fail-closed** (`apps/tenancy/`) — the manager returns nothing / raises when no
   tenant is bound, and cross-tenant ids 404. *Why: one company must never see another's data — the whole
   multi-tenant promise.*
2. **Server-side RBAC** (`RBACMixin`, `apps/rbac/`) — never trust the frontend; the role is checked on
   every request. *Why: the SPA is untrusted; the server is the boundary.*
3. **HITL gate** — every AI output is saved `PENDING_HUMAN_REVIEW`; a human must approve; a review can't
   finalize without a recorded approver. *Why: AI is advisory, never autonomous — trust + accountability.*
4. **Append-only audit log** (`apps/audit/`) — insert-only, no update/delete. *Why: a tamper-evident trail
   for every consequential action.*
5. **All LLM calls via the one gateway** — never call a provider SDK directly. *Why: budget, PII-scrub,
   schema-validation, metering and the no-fabrication guarantee all live there.*
6. **No fabrication / real data only** — no provider → honest 503; empty data → honest empty state.
   *Why: a PMS that invents performance data is worse than useless.*
7. **The agent emits action names only; params resolve server-side** — the LLM never produces
   parameters, permissions or SQL. *Why: an LLM must not be able to widen scope or forge a write.*
