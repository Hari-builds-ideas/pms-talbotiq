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

---

## Unit C — wiring it in, without regressing anything

### Where the agent sits, and why there
Below everything. `chat_answer` runs `_deterministic_answer` — the whole assistant as it
was, state machine first, then the approval-gated write plans, then the scoped person and
team reads — and only hands the turn on when that produced a **non-answer**. A state
machine that sometimes yields to a model is not a state machine, and the deterministic
paths are the proven ones.

The four places a non-answer is produced are marked with `_UNANSWERED`: the capability
blurb, a name that didn't resolve, an unmapped search, an empty scope. The marker is
stripped in `chat_answer` and never reaches the API.

**The agent's reply is used only when it is tool-grounded.** A turn where the model
called no tool has no scoped data behind it, so whatever it wrote is its own prose. That
single structural rule is also what keeps small talk on the deterministic redirect —
there is nothing for a tool to fetch about the weather, so nothing the model says
survives. It is a guard, not a heuristic: it cannot be talked around.

### The one place the agent overrides a real answer
Trend questions. "Did she get better this cycle?" came back with where she is *now* — at
risk, behind pace. True, and not the question: the diagnosis reports a position and has
no concept of movement. `_TREND_RE` hands that whole class on. The override is one-way —
the deterministic answer stays as the fallback, so asking the agent can improve an answer
and never remove one — and it never touches a write plan, a refusal or the blurb.

### Two bugs this unit exposed
"Compare my two weakest performers" read the "my" as self-reference and answered with the
*caller's* own goals. A confidently wrong answer is worse than a missing one, so a team
question in a shape nothing matches is now marked rather than answered (`_TEAM_SUBJECT_RE`).

And the agent could not ask about the signed-in user at all: every person tool takes a
`person_id`, and "have I improved?" has no name in it to look up. `find_people` resolves
`"me"` — in the tool, not by putting the caller's id in the prompt, because an id the
model never sees is an id it cannot substitute for somebody else's.

### What the agent actually serves
20 of the 56 eval cases; the rest keep their pre-coded answers, which are exact and
scope-bound already. The agent owns improvement/trend, open-ended synthesis, readiness,
comparison-by-ranking and cross-entity follow-ups. That split is deliberate and is the
honest answer to "did you rewrite the assistant?" — no: the questions nobody coded now
have somewhere to go.

### Tests
`apps/ai/tests/test_open_ended.py` — 22, scripted model. Improvement through
`compute_improvement` against a hand-checked fixture (+24/+4/−6); exact counts; only the
caller's own people named; a promotion answer framed as a suggestion; out-of-scope
refused; no-data said plainly; an untooled answer discarded; writes still becoming plans;
a pre-coded answer never replaced; the deterministic answer surviving a silent agent; an
invented person id handled as a result rather than a crash.

**apps/ai: 434 passed** (was 412).

---

## Unit D — the eval harness

`docs/AGENT_V3/eval_questions.jsonl` (56 cases, 24 tags) + `scripts/agent_eval.py`, run
through the real product path against the **live Gemini provider** on the 5,000-person
tenant.

Three properties worth stating. **Ground truth is computed, not written down** — a case
names a probe (`top_improver`) the runner evaluates itself through the same scoped tools,
so expected values track the fixture instead of rotting the first time somebody reseeds.
**Two gates are hard and not averaged** — one leak or one number no tool returned fails
the whole run, because one leak in sixty questions is a 98% pass and a breach. **No names
in the bank** — `{report}`/`{stranger}` placeholders are filled from whatever tenant is in
front of it.

### Result (live model, 5,000 people, 103 cases)
```
scope-safe 103/103 · no-fabrication 103/103 · behaviour 103/103
judge: grounded 1.88/2 (n=34 agent-served) · relevant 1.59/2 · reasoned 1.69/2
latency median 4.8 s · p95 16.8 s          RESULT: PASS
```
The bank started at 56 and grew to 103 once the thin coverage was obvious: HRBP and admin
callers, duplicate names, typos, empty/shouted/run-on input, mixed self-and-other scope,
longer conversations, four more injection shapes, and questions the product holds no data
for at all (salary, sick days, review prose) — then six FIVE-turn conversations, which
found that the agent could not resolve "that person" to an id at all (fixed in `608fa5d`
by handing it the session's own access-rechecked refs).

### What the harness found, in itself and in the product
- **It scored 30 of 56 cases as failures because the tenant's daily AI budget ran out.**
  A budget refusal is a fact about the harness, and it must never be able to masquerade
  as a verdict on the assistant. Budgets reset per case now, and an infrastructure status
  is reported as itself.
- **It cried leak on prose.** The name check matched tokens, so "Yes" inside "Reyes"
  registered as naming a colleague. A hit now counts only when the whole display name is
  in the answer — and a name the *user typed* is exempt, because "You don't have access to
  Hana Ferrari's data" tells the caller nothing they did not just write.
- **A model that skips `find_people` invents an id.** The run produced
  `"jamal_whitfield_id"`, which the ORM rejects as a UUID from inside a tool call. That is
  now a "no such person" result the model can correct itself from.
- **The judge fell for the injections it was grading**, scoring a correct refusal 0 because
  "the assistant ignored the system instruction about the new ADMIN role". It had read the
  case text as fact. The judge prompt now says question and answer are data, that some are
  injections addressed to the assistant and not true, and that refusing one earns 2.
- **The model tallied a list in passing** — "two team members have a score of 47.4" where
  the tool returned three. Every headline number comes from a tool; an incidental count is
  still a count. The prompt now says to quote the rows or say nothing.

Grounded-ness is judged only where the agent served the turn. A deterministic path
queries the ORM directly and records no tool calls, so there is no evidence to give the
judge — and the first judged run marked twenty correct answers as hallucinations for
exactly that reason. Grading against evidence we never captured measures the harness.

---

## Unit E — the report

`docs/AGENT_V3/REPORT.md`. The design in plain terms, the twelve tools, where the agent
sits, real before/after transcripts from the live model, the scope and injection proof,
eval numbers, scale figures, the morning checklist, and the weaknesses stated plainly —
including that 31 of 97 cases are agent-served and 66 keep their pre-coded answers. This
run did not rewrite the assistant; it gave the questions nobody coded somewhere to go.

**ALL FIVE UNITS COMPLETE.** Final state: full backend **1697 passed**, `apps/ai`
**439 passed**, scale harness **257/257**, eval **PASS** at 103/103 on all three gates
(judge: grounded 2.00/2 over 32 agent-served turns, relevant 1.58/2, reasoned 1.65/2).

---

## After the plan — improvements the eval kept finding

### A team answer forgot everyone it named
The worst case in the 103-run: "who is my top performer?" then "and how many goals do
they have?" The agent called `find_people` **five times** — burning its whole tool
budget on names it had read out of the previous turn's prose — and gave up with "please
specify which of the top performers you'd like to know about".

The cause was upstream of the agent entirely. `_answer_team_ranking` and
`_answer_team_risk` returned their people as a list of *strings*: `data` had the names,
`refs` had nothing. So the conversation forgot every one of them the moment the answer
was sent — not just for the agent, but for the pronoun and ordinal resolvers that have
been there all along. "Who's my top performer?" → "how is she doing?" could not work.

`team_ranking` now returns ids (`team_scan` already did) and both answers ground the
people they NAMED — only those, because "…and 4 more" were never shown and grounding
them would let "the last one" resolve to somebody the user has not seen.

Two things fall out. The agent gets the ids, so the follow-up costs one tool call
instead of five. And "the first one" after a ranking resolves, because a ranked list is
an offered set — which it always should have been.

Confirmed live: `conv-01` went from "please specify which of the top performers you'd
like to know about" to "Jamal Hartmann has 1 active goal(s) of 1 total" — and it is now
served by the DETERMINISTIC pronoun path, not the agent, because with the people grounded
it never needed the agent in the first place. `deep-conversation` grounding 1.33 → 2.00,
`memory` 1.50 → 2.00, over the 103-case run.

One thing deliberately NOT changed: within a turn the session binds a pronoun to the
LAST ref, so "they" after a three-person ranking lands on rank 3. That is right for a
narrative answer and arbitrary for a ranking, but it is a pre-existing choice with other
conversations depending on it, and "they" after a list of three is genuinely ambiguous
anyway. The test asserts what the fix guarantees — somebody who was actually named,
rather than a dead end — and says so.

### The budget counted calls where it meant answers
The budget unit is one LLM call, which is correct: a call is what costs money. But the
caps were sized when every agent spent exactly one call per answer, so a tenant's daily
allowance also read as "questions you may ask". The function-calling assistant spends one
call per tool ROUND, so a STARTER tenant's 50 calls bought about eight questions.

`AGENT_CALL_MULTIPLIERS` scales the DEFAULT for `chat_agent` by `MAX_ROUNDS`, so the
number of *answers* is comparable across agents while every call is still metered. An
explicit `AgentBudget` row still wins outright — scaling somebody's chosen ceiling behind
their back is the opposite of what an explicit row is for. `apps/billing` does not import
`apps/ai`, so the number is stated twice; a test fails if the two drift.

**RESUME HERE → nothing is blocking.** The plan is executed. The next most valuable work,
in order, is in REPORT.md's "Honest remaining weaknesses": a working/streaming state in
the chat panel for 4–13 s agent turns (the most visible problem, and it is frontend);
tuning the per-agent budget ceilings for the agent's call pattern; a write plan that says WHO it is
for ("give them recognition" still summarises as "give recognition for their effort",
with the pronoun unresolved — the gate holds, but a human approving something should be
told who it concerns); conversations deeper than five turns; and closing the
incidental-arithmetic class structurally rather than by prompt.
