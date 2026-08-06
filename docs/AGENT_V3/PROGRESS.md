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

**RESUME HERE → Unit B** (`B_AGENT_LOOP.md`): the Gemini function-calling loop. The
groundwork that matters: `LLMGateway.run()` is single-shot (prompt → JSON) and will need a
tool-calling sibling that keeps budget / PII-scrub / trace / metering intact, plus a
provider method that passes `tools` and returns `tool_calls` — Gemini's OpenAI-compatible
`/chat/completions` endpoint supports both. Then C (open-ended), D (eval harness),
E (report).
