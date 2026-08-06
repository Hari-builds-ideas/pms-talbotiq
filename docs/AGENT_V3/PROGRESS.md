# AGENT_V3 — progress log

Branch: `hari/agent-intelligence-v2`. Plan: `AGENT_V3_MASTER.md` + `A_TOOLS` … `E_REPORT`
at repo root. Each unit: implement → test → land → log here. **Resume from the last
"RESUME HERE".**

The previous run (`docs/AGENT_REBUILD/`) is complete: company-wide person resolution, the
conversation state machine, scoped data answers, and the approval-gated write actions all
work and are proven at 5,000–50,000 people. This run adds the thing that run could not do
— answering questions nobody pre-coded — via Gemini function-calling over scoped tools.

---

## Unit A — the permission-scoped read-tool set

### What this unit is really about
The security model of a function-calling agent is decided entirely by the tool boundary,
so this unit is mostly about what the model **cannot** express.

**Scope is not an argument.** Every handler takes a `ToolContext` built server-side from
the authenticated session. `tool_schemas()` — the only thing the model sees — contains no
caller, tenant, or role field anywhere, so "answer as the admin" is not a sentence the
model can form. There is a test asserting exactly that, because the day someone adds a
convenience `caller_id` parameter is the day the guarantee quietly dies.

**A denial is data, not an exception.** An out-of-scope person returns
`{"denied": true, "reason": …}`. That is what lets the agent say "that's outside what you
can see" rather than either leaking or crashing — the model has to be *told*, in a form it
can relay.

**The backend does every calculation.** `rank_team`, `team_aggregate` and
`compute_improvement` sort, count, average and subtract in Python over scoped rows. The
model receives finished numbers and phrases them. A model doing arithmetic on returned
rows is precisely how invented figures reach an answer, and it is unverifiable afterwards.

### The 12 tools
`find_people` (company-wide identity, delegating to the ONE canonical resolver — a second
name matcher is how the directory and data paths drifted apart in the last run) ·
`get_person_overview` · `get_person_goals` · `get_person_kpis` · `get_person_reviews` ·
`get_cycle_scores` · `get_feedback_summary` · `list_check_ins` · `get_my_team` ·
`rank_team` · `team_aggregate` · `compute_improvement`.

Metric names are **enumerated**, not free-form: letting the model pass an expression we
then evaluate would be text-to-SQL by another route.

### Scale, which is a correctness property here
`insight._subtree_latest_scores` issues one score query **per person** — fine on a
five-person fixture, ruinous on a real org. The team tools resolve every latest score in
a fixed number of queries instead. Asserted as *constant*, not as an exact count: pinning
the number turns a future optimisation into a failure. Verified by reintroducing the N+1
and watching the test fail (7 queries → 64).

Results are bounded at 50 rows, with the true size still reported and a `truncated` flag —
a 200-person team must not become a 200-row tool result, and the aggregate tools exist so
"how many" never needs the list at all.

### Tests
`apps/ai/tests/test_tools.py` — 16. Every data tool denied for an out-of-scope person in
one loop (so a tool added without the check fails immediately, rather than being silently
uncovered); findable-but-unreadable, proving the directory/data split; cross-tenant;
no caller argument in any schema; aggregates and rankings against a hand-checked fixture
(3 at risk, 3 behind, mean 50); improvement as a backend delta; a single score never
reported as improvement; attainment computed by the backend; explicit no-data markers;
unknown tool/bad argument structured rather than raised; constant query count; bounded
results; and review STATE exposed while the draft body is not.

**AI suite: 402 passed.** No production behaviour changed yet — this unit only adds a new
module; nothing calls it until Unit B.

---

## Unit B — the function-calling loop

### Three layers, each with one job
- **`GeminiProvider.generate_with_tools`** — one turn: send messages + tool schemas, get
  back either `tool_calls` or prose. Holds no state, so a retry or a crash can never
  leave half a conversation behind. Deliberately *not* JSON mode: the final answer is
  prose for a person, and the structure we care about arrives as typed `tool_calls`
  rather than as text we would have to parse back.
- **`LLMGateway.run_tools`** — a sibling of `run()`, not a replacement, because rule 6
  says every LLM call goes through the gateway and a tool call is still an LLM call.
  Budget, tracing and metering all still apply.
- **`apps/ai/agent_loop.py`** — the loop, the system prompt, and the record of what it did.

### Two decisions worth stating
**Only user text is PII-scrubbed.** Tool results come from our own scoped queries;
scrubbing them would corrupt the very numbers the answer is built on, and a redacted
score is worse than no score. The PII risk is in what the user types, which is what gets
cleaned.

**The loop terminates by construction.** Two ceilings — 6 rounds and 12 total tool calls.
Exceeding either ends the turn with an honest "I couldn't finish working that out", never
a partial investigation presented as a conclusion. Unbounded rounds are unbounded latency
*and* unbounded spend, since each round reserves budget.

### The system prompt carries the rules the code cannot
Scope and arithmetic are enforced structurally (the tools own both), but *choosing* the
aggregate tool is the model's job, so the prompt is explicit: "how many" → `team_aggregate`,
"who is top" → `rank_team`, "improved" → `compute_improvement`, and "if you find yourself
adding, counting or sorting, stop and call the tool instead". It also states what to say
when a tool returns `{"empty": true}` or `{"denied": true}` — the model needs a *true
thing to say*, or it will find something plausible instead.

### Tests
`apps/ai/tests/test_agent_loop.py` — 10, against a **scripted** model. What is under test
is the loop: that tools run as the trusted caller, that denials arrive as relayable data,
that the cap holds, that failures degrade honestly. Those are properties of our code;
wiring them to a live model would make every assertion depend on what Gemini felt like
doing that minute. Whether it *picks* the right tools is unit D's question.

One test was initially passing for the wrong reason and was split: the impersonation case
asserted `denied OR error`, and the injected `caller`/`role` arguments made it an
*argument* error, so the scope path was never exercised. It now does both — a clean call
refused by scope, and an impersonating call that changes nothing.

**apps/ai + apps/billing: 498 passed.**

**RESUME HERE → Unit C** (`C_OPEN_ENDED.md`). The loop exists but **nothing calls it yet**
— `chat_answer` still routes to the pre-coded paths, so there is no behaviour change in
the product. Unit C wires it in behind the existing flow (the state machine and the
approval-gated writes must keep priority; the agent handles what falls through to the
capability blurb today), adds the composition few-shots, and proves the question classes
in `C_OPEN_ENDED.md`. Then D (eval harness) and E (report).
