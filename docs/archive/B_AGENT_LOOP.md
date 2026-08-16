# B_AGENT_LOOP.md — the Gemini function-calling loop

Wire the tools from A into a function-calling loop that composes them to answer questions, does math in
the backend, stays grounded, and coexists with the existing memory and approval-gated write actions.

## The loop
1. Build the request to Gemini: system prompt (role + rules + grounding discipline + few-shot) →
   conversation memory (existing window + entities discussed) → the tool schemas → the user message.
2. Gemini responds with either a final answer OR one/more `function_call`s.
3. For each function_call: run the corresponding tool in the backend WITH the trusted caller context
   (scope enforced inside the tool). Return the structured result (or `denied`) to the model.
4. The model may call more tools (compose: find_people → get_cycle_scores → compute_improvement).
5. When it has enough, it produces the final grounded answer, phrasing the backend-computed values.
6. Cap the tool-call iterations (e.g. ≤6) to bound latency/cost; if exceeded, return a graceful "couldn't
   complete that" rather than looping.

## Scope, passed safely (research §3)
- The caller identity/role/tenant is injected into each tool call server-side from the authenticated
  session — NOT from anything the model emits. The tool schemas do NOT include a "caller" argument the
  model could fill.
- Every tool re-checks scope. A `denied` result is returned to the model as data ("you don't have access
  to that person"), which the model must relay honestly.

## Grounding / "I don't know" (research §4)
- System prompt rule: "Answer ONLY from tool results. Never state a number, name, status, or fact not
  present in a tool result. If tools return no data or a denial, say so plainly. Never estimate or invent."
- Structural guard: if the model's final answer contains a number/claim, it must have come from a tool
  result this turn; add a lightweight check/logging that flags answers with no supporting tool call (for
  the eval harness). Prefer the model citing the computed value from an aggregate tool.
- Empty result → "There's no data on that." Denied → "That's outside what you can see."

## Coexist with memory + reference resolution (already built)
- Feed the existing conversation window + entities-discussed so "he/she/the other one/do the same" still
  resolve. `find_people` handles fresh names; the memory handles references. Don't duplicate or regress
  the existing resolver — call it via the `find_people` tool.

## Coexist with approval-gated WRITE actions (research §5)
- READ tools (A1–A12) compose freely, no approval.
- WRITE/ACTION tools (recognition, check-in, feedback-request, review-draft) keep the EXISTING plan →
  human-approve → commit flow. Represent them so the agent proposes the action and the existing approval
  UI gates it; the model cannot commit a write without the user's confirm step.
- One agent, two tool classes: reads execute immediately (scoped); writes require the human gate. Never
  let a write auto-execute from a model decision.

## Backend math, never the LLM (research §2)
When a question needs ranking/counting/averaging/deltas, the model MUST call the aggregate tool
(rank_team / team_aggregate / compute_improvement) and use its returned numbers. The system prompt
forbids the model from computing these itself. Add a test that "who improved most" routes through
compute_improvement, not model arithmetic.

## Graceful failure
Gemini error/timeout → retry with backoff, then an honest "couldn't generate, try again" — never a dead
spinner, never fabricated content. Keep heavy calls off the request thread per the existing async setup.

## Tests
- A compositional question triggers multiple tool calls and a grounded answer.
- Scope: an out-of-scope person's data question → model relays the denial, no leak.
- Grounding: with tools returning empty, the model says "no data", invents nothing.
- Aggregate questions route through backend compute tools.
- A write action still requires human approval (cannot auto-commit).
- Reference follow-ups still resolve via memory.

## Done when
The function-calling loop composes scoped tools to answer questions, math is backend-only, answers are
grounded or honestly empty, memory + approval-gated writes both work within it, failures degrade
gracefully, tests green. Logged in PROGRESS.md.
