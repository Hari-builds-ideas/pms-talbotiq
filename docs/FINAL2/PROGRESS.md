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
