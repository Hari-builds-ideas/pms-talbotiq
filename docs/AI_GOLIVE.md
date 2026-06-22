# AI_GOLIVE.md — taking the AI agents to production

The single guide for running the AI in production. It consolidates and updates
`NEEDS_HARI_llm_provider.md` (which predates the provider wiring). **The AI runs on
OpenAI** (Groq remains available by config) — this is about hardening it for real use.

## Current state (live)

- **Provider:** `LLM_PROVIDER=apps.ai.openai_provider.OpenAIProvider` (OpenAI Chat Completions, JSON mode). Key in the gitignored backend `.env` as `OPENAI_API_KEY`; base URL `OPENAI_BASE_URL=https://api.openai.com/v1`. Groq (`apps.ai.groq.GroqProvider`) is still wired — switch back by config (see below).
- **Every call** goes through the one `LLMGateway` (CLAUDE.md rule 6): budget reserve → PII-scrub (emails) → provider call (LangSmith span) → **schema-validate** → meter to `TokenLedger` → confidence + low-confidence flag. It never raises to the caller and never fabricates output. The OpenAI provider mirrors the Groq one — same contract, same response shape.
- **Two-model strategy** (`settings.LLM_MODEL_MAP`): **`gpt-4o`** for the human-read agents (review / feedback / succession / JD / career), **`gpt-4o-mini`** for chat + default. Each is overridable per env var (`LLM_MODEL_REVIEW`, `LLM_MODEL_CHAT`, …) — e.g. swap to `gpt-4.1` / `gpt-4.1-mini` without a code change. (Models that use `max_completion_tokens` / no `temperature`, e.g. the o-series, would need a provider tweak — gpt-4o/4o-mini use the same `max_tokens`+`temperature` shape as today.)
- **Paid-pricing guards:** OpenAI bills per token (unlike the Groq free tier), so a process-global call ceiling defaults **ON** — `LLM_MAX_CALLS=60` (Redis-counted, 24h TTL, shared across web+celery) — a hard backstop against a runaway loop / seed smoke. Plus bounded `LLM_MAX_TOKENS=900` and 429 back-off honouring `Retry-After`.
- **JSON mode:** OpenAI requires the literal "json" in the messages for `response_format=json_object`; the agent prompts already say "JSON" and the provider appends a guard line if a custom prompt omits it.
- **Prompts** are centralized + tunable: `apps/ai/agent_config.py` (`SYSTEM_PROMPTS`), overridable per agent from `settings.LLM_SYSTEM_PROMPTS` without a code change.
- **HITL everywhere:** every AI artifact is locked PENDING and a human releases/approves/publishes it. With the key unset, the graceful 503 path holds; over per-tenant budget → 429.

### Switching provider by config (no code change)
- **OpenAI (default):** set `OPENAI_API_KEY` in `.env`. `LLM_PROVIDER` already defaults to the OpenAI provider in compose.
- **Back to Groq:** in `.env` set `LLM_PROVIDER=apps.ai.groq.GroqProvider`, `GROQ_API_KEY=…`, and the Groq model names (`LLM_MODEL_REVIEW=llama-3.3-70b-versatile`, `LLM_MODEL_FEEDBACK=…`, `LLM_MODEL_SUCCESSION=…`, `LLM_MODEL_JD=…`, `LLM_MODEL_CAREER=llama-3.3-70b-versatile`, `LLM_MODEL_CHAT=llama-3.1-8b-instant`, `LLM_MODEL_DEFAULT=llama-3.1-8b-instant`), then restart `web`.

### Cost note (OpenAI is paid)
The per-tenant budgets (`DEFAULT_AGENT_BUDGETS`) are **call counts**, not dollars: FULL_AI = 500/day, STARTER = 50/day. At `gpt-4o` (~$2.50/1M in, $10/1M out) a human-read call (~2k in + ≤900 out) is roughly **$0.01–0.02**; `gpt-4o-mini` chat is well under **$0.001**. So a FULL_AI tenant's 500-call day is ≈ **$5–10 worst case** (all `gpt-4o`); the 60/run global ceiling caps a single run at **≈ $1**. The call-count budgets are still sensible — **no change required** — but if you want a tighter dollar ceiling, lower `LLM_MAX_CALLS` or the FULL_AI daily cap, or keep more agents on `gpt-4o-mini`.

## To productionise

1. **Pick the production provider + tier.** OpenAI and Groq are both wired and provider-agnostic via the gateway (active = OpenAI). To switch (Gemini / Bedrock / Anthropic): add a provider class implementing `apps.ai.providers.LLMProvider.generate` (mirror `openai_provider.py` / `groq.py`) and point `LLM_PROVIDER` at it. The agents, prompts, schemas, and budgets don't change.
2. **Move the key out of `.env` into a real secret store.** `.env` is fine for dev/demo but production should pull `OPENAI_API_KEY` (or `GROQ_API_KEY`/`LLM_API_KEY`) from a vault (AWS Secrets Manager / GCP Secret Manager / etc.) injected as an env var at runtime. Never commit a key; the staged-diff scan + `.gitignore` already prevent it.
3. **Confirm the per-tenant budgets.** `apps/billing/packs.py::DEFAULT_AGENT_BUDGETS` + `AgentBudget` (Module 11): STARTER vs FULL_AI daily/monthly caps. The gateway reserves against these BEFORE each call and meters usage; over-budget returns a 429-class result with an upgrade hint. Set real numbers for your tier. Pack→agent mapping: STARTER = Agent 2 (KPI nudges) + chat; FULL_AI = Agents 1–5 + JD + career.
4. **Raise the run ceiling for production.** `LLM_MAX_CALLS=60` is a demo safety net; size it to your tier (it's a runaway-loop backstop, not the real budget — that's #3).
5. **(Optional, on-stack) Swap the in-repo graph runner for real LangGraph.** `langgraph` + `langsmith` are installed. Each agent is an ordered list of node functions run by `apps/ai/graph.run_graph` (a faithful `StateGraph` stand-in). The node functions are the real logic and don't change — replace `run_graph` with `StateGraph(...).compile().invoke(state)` per agent. Keeps the locked stack without rewriting agent logic.
6. **Enable LangSmith tracing.** Set `LANGSMITH_API_KEY` (the trace span around every provider call is a no-op until then) for prompt/latency/cost observability.

## Tuning AI output quality (without redeploying logic)

- The biggest lever is the prompt. Edit `apps/ai/agent_config.py::SYSTEM_PROMPTS` (or override via `settings.LLM_SYSTEM_PROMPTS`) — the shared `STYLE_SPEC` enforces: name the person, cite specific goals/KPIs/numbers, concise/concrete, no padding, JSON-only.
- The **evidence** each agent sees is assembled in `apps/ai/evidence.py` (rich review grounding, name-free succession summary). Add/trim fields there to change what the model can ground on.
- **Confidence** is calibrated to evidence sufficiency (`confidence_with_sufficiency`): thin grounding → lower confidence → the yellow warning + a tighter HITL prompt.
- Output **schemas** (`apps/ai/schemas.py`, `NonEmpty`) reject blank/garbage sections — tighten `min_len` per field to demand more substance (verify against one real record so a valid terse answer isn't rejected).

## Safety properties (must always hold)

- AI output is real provider output, metered in the `TokenLedger`, locked PENDING until a human acts.
- Feedback summaries are built from the anonymised payload — **giver identities never enter a prompt**; the gateway also scrubs emails, and Agent 3 runs a post-LLM breach check.
- Succession narratives are fed a **name-free** summary (no candidate ids/emails).
- Chat is read-only, RBAC/scope-bound, and write-blocked.
- Career roadmaps are advisory only (a DB CHECK enforces it) — never an auto-promotion.
