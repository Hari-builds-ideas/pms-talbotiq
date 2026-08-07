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

**ALL FIVE UNITS COMPLETE.** Final state: full backend **1708 passed**, `apps/ai`
**450 passed**, scale harness **257/257**, eval **PASS** at 106/106 on all three gates
(judge: grounded 1.88/2 over 33 agent-served turns, relevant 1.62/2, reasoned 1.66/2),
and `--replay` green at 37 cases in 1.2 s with no API key.

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

### A plan you approve now says who it is for
The eval's last low score. "Who are my two weakest?" then "give them recognition" produced
a plan headed "Plan to give recognition for their effort this quarter" — every step
underneath named the right person, and the line the approver reads named nobody.

The trigger is not "there is a pronoun": the deterministic planner's own summary is
"Planned the requested steps for your approval", which is just as blind. It is: if the
plan acts on other people and the headline does not name them, name them. A headline that
already names everyone is left alone, and so is a plan about the caller's own records —
"start my check-in" does not want "(for Nikhil Vasquez)" bolted on.

Worth recording what this is NOT. The reproduction showed the pronoun case resolving to a
CLARIFY step — the planner asking which detail is missing — and a clarify has no subject
to name. That is correct behaviour, not a second bug, so the fix stops where the plan
genuinely knows who it means.

Full backend **1700 passed**.

### The whole-team trend was read off a truncated list
The most consequential of the late fixes, because the old answer was not vague — it was
**the opposite of the truth**. "Is my team trending up or down overall?" returned
"trending up", read from the ranked list. But `ranked` is a bounded top-N, and the top of
a list sorted by improvement is all improvers. Five rows of nine said "up" for a team that
was going down.

`compute_improvement` now returns a `summary` computed over EVERY comparable person —
improved, declined, unchanged, mean delta, direction — beside the bounded list, and
`listed` says how much of `compared` the list actually holds. The answer became "trending
down. Out of 9 people compared, 3 improved and 6 declined, with a mean delta of -1.0."
Nothing about the model changed; a number cannot be misread the way a truncated list can.

### The limit the tool boundary cannot close, now measured
Asked "which of them declined the most?", the model calls `compute_improvement` once per
person and picks the largest by eye — still, after the prompt told it not to. Six legal
calls are six legal calls; no schema change forbids it. So the eval **counts** it now, and
prints the offending cases every run (currently one: `deep-05`, five per-person calls).
Reported as a number, not enforced as a gate — the heuristic is good enough to point at,
not to fail a release on.

Then the advice was moved IN-BAND, into the result of the third per-person call, on the
theory that the prompt was simply too far away by then. **It made no difference.** The
next run went from five per-person calls to six: the model saw the note on calls three
through six and carried on. Persuasion has been tried twice and failed twice.

Left open deliberately. The remaining option is enforcement — refusing the fourth call —
and that breaks a legitimate "compare these four people" question to prevent a fault that
has never yet produced a wrong answer (every superlative it answered this way named the
right people, because it had in fact fetched all of them). The mitigation is the
measurement, not a guarantee. Revisit the moment the count rises or an answer is wrong.

### Half the eval now gates a build
`D_EVAL_HARNESS` asks for something CI can run. The live eval cannot be that: an API key,
real money, twenty-five minutes. `--replay` re-executes the calls the model made on a
recorded run — same callers, today's code and data — and re-checks the answers that were
given. Under a second, no model.

Both of its limits were found by *trying*, which is the part worth keeping.

The first version's docstring claimed it caught a widened scope check. It does not.
Disabling `_readable`'s access check left the run green, for a dull reason: none of the
recorded calls were for somebody out of scope, so loosening the check changed nothing
about them. Result-scanning was added and is worth keeping, but it is opportunistic — it
fires only for calls that happen to have been recorded. The systematic proof of that
boundary is `test_tools.py`, which denies every data tool for an out-of-scope person in
one loop and already runs in CI. The claim was corrected rather than the test.

What it does catch is demonstrated, not asserted: adding 3.0 to the cycle-over-cycle
delta fails 8 of 16 cases instantly — every answer quoting a number the backend no longer
produces. That is the backend-math contract under regression test in a second.

Recording gained the tool ARGUMENTS and the actor id, which is all replay needs. Results
are deliberately not recorded; recomputing them is the whole point.

### Ten-turn conversations, and two holes they found in the harness
Three ten-turn cases were added because "conversation memory kept working" is a plan
requirement and the bank's deepest case was five. The conversations themselves hold: 3/3
on every gate, relevance 2.00, and on turn nine "summarise everything you've told me
about them" still answers about the right person with real numbers.

What they found was in the harness, twice.

**The scope gate only looked at the last answer.** In a ten-turn case a leak on turn three
would have gone straight past the one check that exists to catch it. Every turn is checked
now, and a failure names which one. Quality is still judged on the final answer — that is
what the conversation was building toward — but safety is not a property of the last thing
you said.

**The judge was hiding its own scores.** A run printed "LLM judge: SKIPPED" when the judge
had plainly just run: grounded-ness is scored only on agent-served turns, that selection
had none, and the empty mean pulled the whole judge line into the skipped branch —
discarding the relevance and reasoning scores it had produced. They were 2.00 and 2.00. A
summary that hides its own data is worse than a missing one.

### One product gap the long conversations exposed
Nine turns of real work, then "remind me who we've been talking about" → the capability
leaflet. The session knew the answer the whole time and nothing asked it. The agent could
not rescue it either: the question needs no tool, so its reply was discarded by the
tool-grounded rule. That rule is right — it cannot tell a good untooled answer from an
invented one — which means a question answerable from memory alone has to be answered
BEFORE the agent, not by it. It now is, from `people_in_order`, the same access-rechecked
resolver everything else uses; somebody reassigned out of the caller's subtree
mid-conversation drops out of the recap, and a test reassigns one to prove it.

### Proven over HTTP, which found two more things
Everything up to here was proven in-process. Exercised as a real signed-in manager
against the running stack instead, and it immediately paid for itself twice.

**The stack serves stale code until `web` restarts.** The container mounts the repo but
the server process does not reload, so a stack up since before this branch answered "who
improved most since last cycle?" with "I couldn't find anyone named Improved Most Since"
— the exact failure this run replaced. A null `tools` field is the tell. It is now the
second line of the morning checklist, because anyone who skips it will reasonably
conclude none of this works.

**An unparseable message was reported as a failed NAME lookup.** The injection came back
as "I couldn't find anyone by that name". Nothing leaked and nothing was obeyed, but the
reply describes a failure that never happened, and on an impersonation attempt it reads
like an assistant that half went along. The code already knew better — it refuses to echo
more than three leftover tokens precisely because that is not a name — it just said
"name" anyway. It deflects generally now; one to three tokens still echoes, because that
is what tells a user whether we misread them or they misremembered the person.

And the write gate, proven where it matters rather than only in the suite: propose "give
recognition to <report>" → status `plan`, one confirm step, headline naming the person,
recognitions in the database still **0**. Approve the step → **1**.

**RESUME HERE → nothing is blocking.** The plan is executed and every unit is landed,
tested and logged. What is left is in REPORT.md's "Honest remaining weaknesses", and
none of it is a defect — it is the work after this work:

1. **A working state in the chat panel.** An agent turn takes 4–13 s and the panel shows
   nothing while it does, so a slow answer reads as a hang. The most visible problem
   left, and the only one a user would notice unprompted. Frontend, so outside this
   plan's scope; it needs Hari's call on whether to do it here or on the UI branch.
2. **Conversations past ten turns.** Three ten-turn cases now pass every gate. Twenty
   and beyond, where the history window starts dropping things in earnest, are not
   measured.
3. **Model-side ranking.** Deliberately left open — see the section above. Persuasion
   failed twice; enforcement would break legitimate questions to prevent a fault that
   has not yet produced a wrong answer. The eval counts it every run. Revisit if the
   count rises or an answer is ever wrong.
