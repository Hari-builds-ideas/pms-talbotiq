# AI_GOLIVE.md — taking the AI agents to production

The single guide for running the AI in production. It consolidates and updates
`NEEDS_HARI_llm_provider.md` (which predates the Groq wiring). **The AI is already
live on Groq** — this is about hardening it for real use.

## Current state (live)

- **Provider:** `LLM_PROVIDER=apps.ai.groq.GroqProvider` (OpenAI-compatible Chat Completions, JSON mode). Key in the gitignored backend `.env` as `GROQ_API_KEY`.
- **Every call** goes through the one `LLMGateway` (CLAUDE.md rule 6): budget reserve → PII-scrub (emails) → provider call (LangSmith span) → **schema-validate** → meter to `TokenLedger` → confidence + low-confidence flag. It never raises to the caller and never fabricates output.
- **Two-model strategy** (`settings.LLM_MODEL_MAP`): `llama-3.3-70b-versatile` for the human-read agents (review / feedback / succession / JD / career), `llama-3.1-8b-instant` for chat + default.
- **Free-tier guards:** a process-global call ceiling (`LLM_MAX_CALLS=60`, Redis-counted, 24h TTL), bounded `LLM_MAX_TOKENS=900`, and 429 back-off honouring `Retry-After`. A 429 is expected under load, not a failure.
- **Prompts** are centralized + tunable: `apps/ai/agent_config.py` (`SYSTEM_PROMPTS`), overridable per agent from `settings.LLM_SYSTEM_PROMPTS` without a code change.
- **HITL everywhere:** every AI artifact is locked PENDING and a human releases/approves/publishes it. With the key unset, the graceful 503 path holds.

## To productionise

1. **Pick the production provider + tier.** Groq is wired and provider-agnostic via the gateway. To stay on Groq: move off the free tier for higher RPM/TPM. To switch (OpenAI / Gemini / Bedrock): add a provider class implementing `apps.ai.providers.LLMProvider.generate` (mirror `groq.py`) and point `LLM_PROVIDER` at it. The agents, prompts, schemas, and budgets don't change.
2. **Move the key out of `.env` into a real secret store.** `.env` is fine for dev/demo but production should pull `GROQ_API_KEY`/`LLM_API_KEY` from a vault (AWS Secrets Manager / GCP Secret Manager / etc.) injected as an env var at runtime. Never commit a key; the staged-diff scan + `.gitignore` already prevent it.
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
