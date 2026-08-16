# E_REPORT.md — honest report + how to test

Write `docs/AGENT_V3/REPORT.md`:

- **What was added:** the function-calling architecture — the scoped tool set (list them), the agent loop,
  backend-side math, open-ended question handling, and the eval harness. Explain the design in plain
  terms.
- **What changed per file (A–D)** with commit shas.
- **Before → after** real transcripts for open-ended questions the OLD assistant could not answer:
  "who improved most since last cycle", "who's at risk and why", "how many of my reports are behind pace",
  "who's ready for promotion", "compare my two weakest performers" — showing the tool calls composed and
  the grounded answer.
- **Scope + safety proof:** out-of-scope data refused; injection/social-engineering refused; no fabricated
  numbers (from the eval's hard checks).
- **Eval results:** overall grounded-ness/relevance scores, per-tag breakdown, and confirmation that
  scope-safety + no-fabrication are 100%.
- **Scale:** confirmation it holds on the 5,000-person tenant, with resolution/aggregate query counts and
  latency.
- **What I should test myself** in the morning: exact steps, accounts, the large-tenant seed command, and
  5–10 open-ended questions to try.
- **Honest remaining weaknesses** — stated plainly.

Confirm: no hardcoded names (show grep), no text-to-SQL, model never touches the DB, RBAC/tenant/HITL/
audit intact, write actions still approval-gated, nothing merged to hari/agent-ui-v2 or main, working tree
clean, all tests + eval green.

## Done when
REPORT.md is complete, honest, backed by transcripts + eval results + scale numbers. The run is complete.
