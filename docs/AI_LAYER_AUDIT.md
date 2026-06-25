# AI_LAYER_AUDIT.md — focused review of the AI subsystem

**Date:** 2026-06-25 · **Scope:** the AI layer only (`apps/ai/`, the billing budget/metering
seam it depends on, and the LLM-related settings). The rest of the system is covered by
`docs/PRODUCT_STATE.md` and `docs/SYSTEM_DESIGN_AND_READINESS.md` and was **not** re-audited.
**Phase:** 1 of 2 (audit, no code changes). Phase 2 (Groq→OpenAI swap) waits for sign-off.

> Note on current state: an `OpenAIProvider` already exists and `LLM_PROVIDER` defaults to it in
> `docker-compose.yml`. This audit traces what is actually in the tree today and reviews the
> **provider seam** that the swap rides on, so Phase 2 is a verification + hardening pass, not a
> green-field build.

---

## 1. The AI request lifecycle (the one gateway)

Every LLM call in the system flows through **`LLMGateway.run`** (`apps/ai/gateway.py:56`). This is
CLAUDE.md rule 6 ("all LLM calls go through the gateway, never a direct SDK call"), and it holds —
no agent or view calls a provider directly. The lifecycle, step → file/function:

| # | Step | Where | Failure result |
|---|------|-------|----------------|
| 1 | Resolve provider from `settings.LLM_PROVIDER` (import string) | `providers.get_llm_provider()` `providers.py:125` | unconfigured → `NOT_CONFIGURED` (`gateway.py:61`) |
| 2 | Reserve per-tenant budget **before** the call (atomic Redis Lua) | `billing.services.check_and_reserve_budget` `services.py:370` → `billing.atomic.reserve` | over budget → `BUDGET_EXCEEDED` (`gateway.py:67`) |
| 3 | PII-scrub the prompt (email-only) | `pii.scrub` `pii.py:23` | — (always runs) |
| 4 | Provider call inside a trace span | `tracing.trace` (no-op) + `provider.generate()` `gateway.py:75` | `LLMNotConfiguredError`→ refund + `NOT_CONFIGURED`; any `Exception`→ refund + `PROVIDER_ERROR` (`gateway.py:77-85`) |
| 5 | Meter usage to the `TokenLedger` | `billing.services.record_usage` `services.py:316` | — |
| 6 | Validate output against the agent's schema | `schemas.validate_shape` `schemas.py:62` | malformed → `SCHEMA_INVALID` (`gateway.py:110`) |
| 7 | Attach confidence + low-confidence flag (`< floor`, default 0.70) | `gateway.py:117` | — → `OK` |

Design properties that are genuinely good here:

- **It never raises to the caller.** Every outcome is a structured `GatewayResult` (`gateway.py:37`).
  A network blow-up or a model returning garbage can never crash an agent or fabricate a draft.
- **Refund-on-failure is correct.** A reservation that never produced real usage is released
  (`gateway.py:79,84`), so a provider error doesn't permanently burn a tenant's daily budget.
- **Meter-before-validate is the right order for paid billing** (`gateway.py:94` then `:108`): a
  `SCHEMA_INVALID` response is still metered because you were still charged for those tokens.

### The two call paths into the gateway

**Async (the five "human-read" agents).** Endpoint → `services.enqueue_agent_job` (`services.py:17`)
creates a tenant-scoped `AIJob` (QUEUED) and fires the Celery task → `tasks.run_agent_job`
(`tasks.py:123`). The task binds the tenant, is **idempotent** (a terminal job is a no-op against
duplicate delivery — `tasks.py:133`), dispatches by `agent_code` to the seam task
(`reviews/feedback/succession/jd/career`), and classifies the seam's result dict
(`tasks._classify` `tasks.py:96`) into `SUCCEEDED | DEGRADED | FAILED`. Each agent runs its nodes
through the in-repo `graph.run_graph` (`graph.py:17`) — an ordered node list standing in for a
LangGraph `StateGraph`; the single LLM node calls `gateway.run`. The seam task locks the artifact
`PENDING_HUMAN_REVIEW` and audits it.

**Sync (the chat assistant).** `ChatView` (`views.py:28`, AI-throttled, capability + entitlement
gated) → `chat_answer` (`agents/chat.py:70`). The gateway **classifies intent only** (write /
performance / capability / general); the actual data fetch is done deterministically against the
caller's own scope (`actor_can_access` + tenant-scoped managers), so the LLM can never widen access.
This is the safety-critical agent and it is correctly built: **classify with the model, fetch with
the caller's RBAC.**

---

## 2. The provider abstraction + the exact swap points

The contract is small and clean (`providers.py:29`):

```python
class LLMProvider(ABC):
    configured: bool = True
    def generate(self, *, agent_code: str, prompt: str, model: str) -> dict: ...
    # returns {"content": dict, "model": str, "prompt_tokens": int,
    #          "completion_tokens": int, "confidence": float}
```

Implementations in the tree:

- `NotConfiguredProvider` (`providers.py:42`) — the **safe default**: `configured=False`, every call
  raises → agents 503, nothing fabricated.
- `FakeLLMProvider` (`providers.py:74`) — deterministic, per-agent output registered via
  `register_fake_output`. **This is how the whole suite runs with no network.**
- `GroqProvider` (`groq.py:50`) and `OpenAIProvider` (`openai_provider.py:52`) — the two real
  adapters. Both are OpenAI-compatible Chat-Completions over `requests` (no vendor SDK dependency),
  JSON mode, Bearer auth, bounded `max_tokens`, 429 `Retry-After` backoff, a process-global call
  ceiling, and a confidence heuristic (flat `0.88`, `0.6` if truncated).
- `HTTPLLMProvider` (`providers.py:96`) — an **inert, now-obsolete scaffold** that predates the real
  providers (raises `NotImplementedError`-style). Dead code today (see Finding L).

**The exact swap points (the entire seam):**

| Knob | Setting | Defined | Compose |
|------|---------|---------|---------|
| Which provider class | `LLM_PROVIDER` (dotted import string) | `base.py:410` | `docker-compose.yml:41` (defaults to `apps.ai.openai_provider.OpenAIProvider`) |
| Per-agent model | `LLM_MODEL_MAP` (logical→model id) | `base.py:438` | per-agent env `LLM_MODEL_*` |
| Key | `OPENAI_API_KEY` → falls back to `LLM_API_KEY` | `base.py:421,425` | `.env` (gitignored) |
| Base URL | `OPENAI_BASE_URL` | `base.py:422` | `docker-compose.yml:39` |
| System prompt | `LLM_SYSTEM_PROMPTS` override → `agent_config.SYSTEM_PROMPTS` | `agent_config.py:140` | env |

Switching provider is genuinely **config-only**: `get_llm_provider()` imports whatever string
`LLM_PROVIDER` holds, and `_model_for()` (in each provider) resolves logical names
(`review/feedback/succession/jd/career/chat/default`) through `LLM_MODEL_MAP`. No agent code knows
the vendor.

### Files / config / dependencies involved

- **Code:** `apps/ai/{gateway,providers,groq,openai_provider,schemas,pii,tracing,exceptions,graph,
  evidence,agent_config,models,services,tasks,views,urls,serializers}.py` + `apps/ai/agents/*`.
- **Billing seam the gateway leans on:** `apps/billing/{services,atomic,packs,models}.py`
  (budget reserve/release, TokenLedger metering, per-pack default caps).
- **Config:** `config/settings/base.py:405-446`, `docker-compose.yml:35-46`, `.env`/`.env.example`.
- **Deps:** `requests==2.32.3` (the only thing the providers need), plus `langgraph`/`langsmith`
  installed but **not yet wired** (`graph.run_graph` is a stand-in; `tracing.trace` is a no-op).
- **Tests:** 14 files under `apps/ai/tests/` incl. `test_gateway.py`, `test_openai_provider.py`
  (8 tests, `requests.post` mocked — no network), `test_async_sweep.py`, `test_chat.py`, and one
  per agent.

---

## 3. Safety layers — where each is actually enforced

| Property | Enforced at | Verdict |
|----------|-------------|---------|
| HITL (output locked PENDING) | seam tasks lock the artifact; gateway never publishes | ✅ solid |
| Graceful degradation (no key → 503) | `provider.configured=False` → `NOT_CONFIGURED` → view 503 (`views.py:46`) | ✅ solid |
| Over-budget → 429 | `check_and_reserve_budget` → `BUDGET_EXCEEDED` → 429 (`views.py:52`) | ✅ for the per-tenant budget; ⚠️ **not** for the global ceiling (Finding A) |
| Per-tenant budget + global ceiling | atomic Lua reserve (`atomic.py`); `_reserve_global` (`openai_provider.py:75`) | ✅ atomic; ⚠️ semantics (Findings A, B) |
| Token metering | `record_usage` → `TokenLedger` (`services.py:316`) | ✅ but call-count budget ≠ spend (Finding B) |
| Anonymised feedback | name-free payload + **post-LLM breach re-scan** (`agents/feedback.py:79`) + HRBP hold | ✅ genuinely defence-in-depth |
| Name-free succession | `evidence.succession_evidence` strips ids/emails (`evidence.py:134`) | ✅ solid |
| Chat read-only / RBAC | classify-then-scoped-fetch; write intent blocked (`agents/chat.py:84`) | ✅ the strongest-designed agent |
| PII scrub | `pii.scrub` — **email-only** (`pii.py:12`) | ⚠️ names deliberately sent for review/JD/career (Finding C) |

---

## 4. Honest review — what's well-designed

1. **The choke-point discipline is real.** One gateway, one contract, every agent through it,
   structured results never exceptions. This is the thing most codebases get wrong and this one
   gets right.
2. **Fail-closed by default.** The production default is `NotConfiguredProvider`; an unset key
   degrades to a loud 503 rather than a silent or fabricated answer. Tests pin it off, so CI can
   never accidentally hit a network.
3. **The chat agent's threat model is correct.** Using the LLM only to classify intent and doing
   the data fetch through the caller's own scoped managers is exactly right — the model cannot
   exfiltrate data the user couldn't already read.
4. **Feedback anonymity is layered**: name-free payload in, plus a post-LLM email re-scan on the
   *generated* text that holds the summary for an HRBP if anything leaks. That second layer is the
   kind of thing a thorough reviewer is happy to find.
5. **The provider seam is honestly provider-agnostic.** Groq and OpenAI differ only by base URL,
   key, model map, and a JSON-mode guard. The swap is config, and that claim survives inspection.
6. **Atomic budget counters.** The Lua `reserve`/`release`/`incr_window` close the check-then-incr
   race across replicas — better than most MVPs bother with.

---

## 5. Honest review — risks, gaps, and what a senior reviewer flags

These are the AI-layer-specific concerns. Two were verified by tracing, not assumed.

- **(A) The global call ceiling misclassifies when it fires.** `_reserve_global` raises
  `LLMProviderError` (`openai_provider.py:85`). The gateway's broad `except Exception`
  (`gateway.py:81`) turns that into `PROVIDER_ERROR`; the seam tasks map any non-budget error to
  `"provider_error"` (`reviews/tasks.py:111-113`), and `run_agent_job` classifies that as
  **FAILED** (`tasks.py:105`). On chat it becomes a **503** (`views.py:57`). So the *primary
  paid-pricing backstop*, when it does its job, looks like a hard crash, not a graceful "limit
  reached." This matters far more on OpenAI (paid) than it did on Groq's free tier, because the
  ceiling is now the thing standing between a runaway loop and a real bill — and it's also the
  most likely "worked in demo, broke in prod" landmine (default is **60 calls per 24h shared
  across the entire deployment**, not per tenant).

- **(B) The per-tenant budget is a *call count*, not spend.** `DEFAULT_AGENT_BUDGETS`
  (`packs.py:93`) caps daily/monthly *calls* (FULL_AI 500/day). On OpenAI `gpt-4o` a human-read
  call is ~$0.01–0.02, so 500 calls ≈ $5–10/tenant/day — fine, but nothing enforces a **token or
  dollar** ceiling. A pathological prompt (or a future longer-context agent) can cost more per call
  with the budget none the wiser. The `TokenLedger` records the truth but isn't an enforcement
  input.

- **(C) Identifiable, sensitive data egresses to a paid US processor — by design, but needs a
  conscious sign-off.** `pii.scrub` only redacts emails (`pii.py:12`), and `evidence._subject_name`
  *intentionally* puts the employee's first name into review/JD/career prompts
  (`evidence.py:24`), with the documented rationale "a name isn't PII for a review of that person."
  Combined with goals, KPI numbers and risk bands, that's identifiable performance data leaving to
  OpenAI. This was defensible on a free tier; on a paid contract it's a DPA / data-residency /
  GDPR question for SME customers. (Feedback and succession are correctly name-free — the gap is
  review/JD/career.)

- **(D) List schemas are shallow — hollow output can pass.** `validate_shape` enforces `NonEmpty`
  on strings but a `list` spec only checks the type (`schemas.py:53`). So career's
  `SCHEMA = {"tiers": list}` (`agents/career.py:21`) accepts `{"tiers": []}`, and JD's
  `responsibilities/must_haves/nice_to_haves` accept `[]` (`agents/jd.py:22`). An empty-but-valid
  roadmap or JD could reach a human as a "successful" draft. Tighten with a non-empty-list / item
  shape marker.

- **(E) Model-family assumption is brittle against the env override.** Both providers hardcode
  `temperature` and `max_tokens` (`openai_provider.py:110-111`). `gpt-4o`/`gpt-4o-mini` accept
  them, but the model map is env-overridable (`base.py:439`), and OpenAI's o-series reject
  `temperature` and require `max_completion_tokens`. Pointing the map at an o-series model via env
  would 400 every call with no guard. Documented in `AI_GOLIVE.md` but it's a live foot-gun.

- **(F) "Confidence" is a flat heuristic, not a model signal.** Providers return `0.88` (`0.6` if
  truncated). The number a human sees is really `0.88 × evidence_sufficiency`
  (`evidence.confidence_with_sufficiency`) — i.e. a relabeled grounding score, not the model's own
  certainty. Honest about evidence, silent about model uncertainty. OpenAI `logprobs` could give a
  real signal if this is meant to gate human attention.

- **(G) The sync chat path can block a worker ~30s on a 429.** `_post_with_backoff` does blocking
  `time.sleep` up to `min(Retry-After, 10s)` × 3 (`openai_provider.py:150-167`). Fine in Celery;
  on the **synchronous** chat route a sustained OpenAI 429 ties up a gunicorn worker. AI throttling
  bounds the blast radius but it's an availability sharp edge under paid-tier rate limits.

- **(H) `AIJob.confidence` is never populated.** `run_agent_job` lists `"confidence"` in
  `update_fields` (`tasks.py:172`) but never assigns `job.confidence`; confidence is only written
  to the *artifact* by the seam (`reviews/tasks.py:128`). The model docstring claims "confidence
  from the GatewayResult on success" — so the field is dead/misleading. Low impact (artifact is
  authoritative) but the poll API returns `null`.

- **(I) TokenLedger→job link is best-effort and racy.** `_link_usage` picks "the most recent ledger
  row for this agent_code" in-tenant (`tasks.py:108`). Two concurrent jobs of the same agent in one
  tenant can cross-link. Explicitly best-effort; the artifact is the source of truth. Low.

- **(J) Stale "tonight / NEEDS_HARI" framing + dead scaffold.** `providers.py` docstrings still say
  the production state is NotConfigured "until Hari wires a key tonight," and `HTTPLLMProvider` is
  an unused, never-called adapter. Two real providers now exist and OpenAI is the default — the
  comments and the dead class will mislead the next reader (and a security skim).

**Test/doc gaps (AI layer):** no test asserts how a *global-ceiling* hit is classified by the
gateway/job (Finding A) — `test_global_ceiling_blocks_runaway` only checks the provider raises;
no test asserts an empty list fails a schema (Finding D); no integration test runs `gateway.run`
end-to-end with `OpenAIProvider` selected (reasonable — Fake covers the graphs). `AI_GOLIVE.md` is
current and good; `NEEDS_HARI_llm_provider.md` is now superseded and should be retired or pointed at
`AI_GOLIVE.md`.

---

## 6. Prioritised list (AI layer only)

No true **Critical** (the system fails closed and never fabricates). The items below are ordered by
production risk on **paid** OpenAI pricing.

### High

1. **Classify the global-ceiling hit as graceful, not a hard failure (Finding A).**
   - *Why it matters:* it's the main cost backstop; when it fires it currently reads as FAILED/503,
     so operators will misdiagnose a working safety limit as an outage.
   - *Impact:* high (correct degradation UX + accurate ops signal). *Risk of fix:* low.
   - *Fix:* raise a distinct exception from `_reserve_global` (or catch it in the gateway) and map
     to `BUDGET_EXCEEDED` → DEGRADED / 429, with a "run ceiling reached" message. Add a test.
   - *Complexity:* S. *Now or later:* **now** — it's part of making the OpenAI guard trustworthy.

2. **Decide the per-tenant *spend* story (Finding B).**
   - *Why:* call-count budgets don't bound dollars on paid pricing.
   - *Impact:* high (cost containment). *Risk:* low–medium.
   - *Fix (cheapest):* keep call-count, but right-size `LLM_MAX_CALLS` per real tenant count and
     document the worst-case $/day (largely done in `AI_GOLIVE.md`). *Fix (proper):* add an
     optional monthly **token** budget dimension read from `TokenLedger`.
   - *Complexity:* S (document/right-size) → M (token budget). *Now or later:* **now** for the
     numbers review (the prompt asks for it); token budget can be later.

3. **Get an explicit data-egress sign-off for review/JD/career (Finding C).**
   - *Why:* identifiable performance data → a paid US LLM is a compliance decision, not a code one.
   - *Impact:* high (legal/customer trust). *Risk:* n/a (decision).
   - *Fix:* confirm OpenAI API (no-training-by-default) terms are acceptable; if not, gate names
     behind a per-tenant flag or extend `pii.scrub` to pseudonymise names for these agents too.
   - *Complexity:* S (flag) / decision. *Now or later:* **now** (it rides on the provider switch).

### Medium

4. **Tighten list-schema validation (Finding D).** Add a non-empty-list / item-shape marker so an
   empty `tiers`/`responsibilities` fails as `SCHEMA_INVALID` instead of reaching a human. Add a
   test. *Complexity:* S. *Now or later:* now-ish (verify against one real record so a valid terse
   answer isn't rejected).

5. **Guard the model-family assumption (Finding E).** Detect o-series (or a `LLM_PARAM_STYLE`
   setting) and switch to `max_completion_tokens` / drop `temperature`, **or** assert/document that
   only `gpt-4o`-style models are supported via the map. *Complexity:* S–M. *Later* (only bites if
   the map is repointed).

6. **Bound the sync-chat backoff (Finding G).** Cap chat retries to 1 (or 0) / a short total
   deadline so a 429 can't hold a worker ~30s; let Celery agents keep the fuller backoff.
   *Complexity:* S. *Later.*

### Nice-to-have

7. **Populate or drop `AIJob.confidence` (Finding H).** Either set it from the seam result in
   `run_agent_job` or remove it from `update_fields` + the docstring. *Complexity:* S.

8. **Real confidence signal (Finding F).** Optionally fold OpenAI `logprobs` into the confidence so
   the human-attention gate reflects model uncertainty, not just grounding. *Complexity:* M.

9. **Cleanup (Finding J + I).** Delete `HTTPLLMProvider`, refresh the "tonight/NEEDS_HARI"
   docstrings to point at `AI_GOLIVE.md`, and note the best-effort ledger link's race in the
   docstring (or scope it by `started_at`). *Complexity:* S.

---

## 7. Bottom line + Phase 2 readiness

The AI layer is **well-architected for a swap**: a single gateway, a clean provider contract, a
safe default, layered anonymity, and a chat agent built around the right threat model. The Groq→
OpenAI change is genuinely config + a provider class (which already exists and mirrors Groq
faithfully), so Phase 2 is a **verify-and-harden** pass, not a rebuild.

The concerns are concentrated in the **economics and the degradation UX of running on a paid
provider**, not in correctness of the core path: (A) the cost backstop currently looks like a crash
when it fires, (B) budgets bound calls not dollars, and (C) identifiable data egress needs a
conscious sign-off. I'd fold A, B (right-sizing), and C into Phase 2, and treat the rest as
follow-ups.

**No code was changed in this phase. Awaiting approval before starting Phase 2.**
