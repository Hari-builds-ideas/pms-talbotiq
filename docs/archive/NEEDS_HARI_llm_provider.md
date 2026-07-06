# NEEDS_HARI — pick & wire the LLM provider to RUN the AI agents

**Status:** non-blocking for the build (everything is green + tested via fakes).
**Blocking to actually RUN agents in production** — by design, agents stay 503 until
you do the three steps below.

## Why agents are 503 in production right now (intended)
Per the overnight contract, NO real LLM key is used tonight. The single
`LLMGateway` (CLAUDE.md rule 6 — all LLM calls go through it) resolves
`settings.LLM_PROVIDER`, which DEFAULTS to `apps.ai.providers.NotConfiguredProvider`.
So every agent surfaces a loud **503** and NEVER fabricates output. The full agent
graphs are exercised in tests + the demo via the deterministic in-repo
`FakeLLMProvider` (no network). Flipping to production is config + a key.

## The three things Hari must do
1. **Pick a provider** (the pending OpenAI / Gemini / Bedrock decision — the
   gateway is provider-agnostic).
2. **Install the libraries + set the key + setting.** Tonight, to avoid risking the
   green build in an unattended run, the heavy LangChain/LangGraph dependency tree
   was **NOT** added and the LLM SDK is **NOT** installed. To go live:
   - `pip install langgraph langsmith <provider-sdk>` (add to `requirements.txt`) and
     rebuild the web + celery images.
   - Implement `apps/ai/providers.HTTPLLMProvider.generate` against the chosen
     provider (it is a documented scaffold, inert without a key), OR add a provider
     class for the chosen SDK.
   - Set `LLM_PROVIDER=apps.ai.providers.HTTPLLMProvider` (or your class),
     `LLM_BASE_URL` + `LLM_API_KEY` (and `LANGSMITH_API_KEY` to enable tracing — it
     is a no-op until then).
   - **Swap the node runner for real LangGraph (optional but on-stack):** each agent
     graph is an ordered list of node functions run by `apps/ai/graph.run_graph`
     (a faithful stand-in for a LangGraph `StateGraph`). The node FUNCTIONS are the
     real logic and do not change; replace `run_graph` with
     `StateGraph(...).compile().invoke(state)` per agent. This keeps the locked
     stack (LangGraph) without rewriting agent logic.
3. **Confirm the per-tenant agent budgets** (Module 11 `AgentBudget` /
   `DEFAULT_AGENT_BUDGETS`): STARTER vs FULL_AI daily/monthly caps. The gateway
   reserves against these BEFORE every call and meters usage to the `TokenLedger`;
   confirm the numbers (`apps/billing/packs.py::DEFAULT_AGENT_BUDGETS`).

## What is already wired (so step 2 is just config)
- The gateway enforces budget → PII-scrubs → calls the provider → validates the
  output schema → meters usage → attaches confidence — on every call.
- Each agent's seam provider's `configured` delegates to the gateway
  (`llm_configured()`), so the existing Module-3/4/6/8/9 seams already 503 in prod
  and run the full graph under the fake in tests — pointing the seam settings at the
  agent providers is safe today.
- See `NEEDS_HARI_pack_mapping.md` for the Agent-1 STARTER-vs-FULL_AI packaging
  question (independent of this).
