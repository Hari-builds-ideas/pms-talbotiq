# FINAL2 — pre-deployment pass

Branch `hari/agent-intelligence-v2`. Each unit: implement → test → commit → log here.
**Resume from the last "RESUME HERE".** Testing favours unit tests and the no-API
`--replay` eval; live Gemini is used sparingly and on the small tenant, because spend is
a stated constraint.

---

## Unit 1 — a message is answered as what it ASKS, never as the caller's own status

### The bug, and why it was four bugs wearing one coat
Four unrelated messages all came back as a confident report on the caller's own cycle:
"compare all my teammates", "tell me a joke", "who are you?", and a prompt-injection
line. One root cause — the subject-resolution chain ended in `target = caller`, so
anything the classifier mislabelled `performance` and that resolved no other subject
became a self-status answer.

Reproduced deterministically at zero Gemini spend by pinning the fake classifier to
`performance`, which is the state the live model puts these messages in and the only
state where the fault was reachable.

### Three feeders, all closed
- **The object pronoun.** The first-person test was `\b(my|mine|myself|i|me|i'm)\b`,
  which matches "tell **me** a joke" — where "me" is who is being *spoken to*, not who
  is being *asked about*. `_SELF_QUESTION_RE` now requires possessive "my/mine" (and not
  when it introduces somebody else: "my team", "my manager"), "myself", or a first-person
  question form ("am I", "do I", "I'm").
- **"teammates" was not a team word.** `_TEAM_SUBJECT_RE` knew `team` but `\bteam\b`
  does not match "teammates", so "compare all my teammates" had only a bare "my" to go
  on. It now knows teammates/colleagues/peers, and `_COMPARE_RE` matches "compare|rank
  … my team/teammates" so the ranking is served deterministically — no LLM call at all.
- **The default itself.** The final `else` returned the caller. It now returns the
  honest redirect, marked for the agent, so a message that identified no subject is
  never answered as though it had.

### A fourth, found while fixing the others
"tell me a joke" then became *"I couldn't find anyone named Joke"* — the leftover token
`joke` read as a name. The heuristic cannot tell `joke` from `akhil`; what it *can* tell
is whether the sentence asked after anybody. `_ASKS_ABOUT_PERSON_RE` gates the
name-not-found message on a person-question shape ("how is X", "what about X", "does X
need…"), so a failed *name* lookup is only ever reported for a message that was looking
for a name.

### Naming collision worth recording
The new regex was first called `_SELF_SUBJECT_RE` — a name already taken further down
the module by the comparison-subject pattern. Python bound the later one and the fix
silently did nothing; the repro looked unchanged. Renamed to `_SELF_QUESTION_RE`.

### Tests
`apps/ai/tests/test_no_self_deflection.py` — 15. Each of the six observed messages
asserted never to come back as self-status; the three refusals one message at a time
(out-of-scope leaks nothing and carries no data; an injection is not reported as a failed
name lookup; a SQL request creates no executable step); "compare all my teammates" lands
on a real ranking; small talk gets the ordinary redirect; and four genuine self questions
("how am I doing?", "what are my goals?", "am I on track?", "do I need help this cycle?")
still resolve to the caller — the other side of tightening the first-person test.

**apps/ai: 466 passed.**

**RESUME HERE → Unit 2** (capabilities/help surface), then Unit 3 (usage + cost report),
Unit 4 (~50-prompt test bank), Unit 5 (`READY.md`).

---

## Unit 2 — the capabilities surface

`HowToUse` beside New chat: a plain-language popover of what it CAN do and what it
CAN'T. Role-aware in exactly one place — who you may ask about — because that is the only
limit that genuinely differs between a manager and an employee.

Starter chips in the empty chat that **send on one click** rather than filling the box. A
chip that only fills it makes the user press Enter to find out whether it was a good
question; sending shows them, which is the point of an example. That needed `ask(text)`
instead of `submit()` reading `input`, since state has not landed on the click that sets
it. The chips are role-scoped: an employee is never offered "who's at risk on my team?",
because offering it is a promise the scope rules would refuse.

Server side, "what can you do?" is answered from the role **before any model call**. It
was spending a Gemini classification to learn something already known, and it is the chip
a new user clicks first. Anchored on the whole message, so "what can you do about my
team's goals?" stays a real question. The answer now states the boundaries too.

Two older tests asserted the blurb calls itself "read-only". That stopped being true when
write actions landed as approval-gated plans — it does write, on your click. Both now
assert the substance (it describes itself, and names the approval boundary).

**apps/ai: 477 · frontend: 138.**

---

## Unit 3 — the usage and cost report

`manage.py ai_usage` reads the `TokenLedger` the gateway has been writing all along:
calls, tokens and an estimated bill, by agent, model or tenant, with `--json`.

The cost is an **estimate** and says so every time. Prices live in `settings.LLM_PRICES`
(USD per million tokens, in/out separately), overridable with `LLM_PRICES_JSON`. Model ids
match longest-prefix first so `gemini-2.5-flash-002` is priced like its family; a model
with no price is named in a warning rather than counted as free. Logical tiers (`chat`,
`default`) resolve through `GEMINI_MODEL_MAP` before pricing — not doing so understated
this repo's own ledger by ~15%.

The first version queried across tenants and reported **zero** against a ledger holding
thousands of rows: every manager on a `TenantScopedModel` filters by the ambient tenant,
`all_objects` included — it widens to soft-deleted rows, not to other tenants. It
aggregates per tenant inside each context now, with a test for that regression.

It cannot report per-user spend: the ledger has no user column. Documented rather than
left to be discovered from an empty column.

**apps/billing + apps/ai: 574.** Docs: `docs/FINAL2/AI_USAGE.md`.

---

## Unit 4 — the 59-prompt self-test bank

`docs/FINAL2/test_bank.jsonl`, run by `scripts/agent_selftest.py` (human table) and
`apps/ai/tests/test_prompt_bank.py` (CI). Judging lives in `apps/ai/selftest.py` so the
two cannot drift about what "passed" means. **59/59, 15/15 categories, zero model calls.**

It judges ROUTING, not phrasing — deterministic, so it is free to run. One real bug
caught: "compare my two weakest" still deflected to the caller, because a superlative with
the noun left off matched no team pattern.

Two of its own bugs caught, both a harness grading the right answer wrong: the scope check
called a refusal naming the person you asked about a leak, and a self-deflection tell
("nothing to assess this cycle") fired on the correct third-person answer. Tells are
anchored on a second-person subject now — one that fires on the right answer is worse
than no tell.

**Full backend: 1803 passed.**

---

## Unit 5 — READY.md

`docs/FINAL2/READY.md`: the before/after table for the reported bug, the three refusals
one message at a time, the per-category 59/59 table, the capabilities surface, the usage
numbers, exact merge steps, the one new (optional) env var, and what I would still watch.

**ALL FIVE UNITS COMPLETE.** Full backend **1803**, frontend **138**, prompt bank
**59/59**, replay eval **37/37**, scale harness **257/257**. Ready for testing and
deployment.
