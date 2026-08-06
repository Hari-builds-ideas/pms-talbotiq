# AGENT_REBUILD — report

**Branch:** `hari/agent-intelligence-v2` (nothing merged to `main` or `hari/agent-ui-v2`)
**Status:** all five build files executed, plus follow-ups (§9–§15). Backend
suite **1638 passed**, scale harness **276/276 at 5,000, 25,000 AND 50,000** people, live
HTTP transcript **15/15 on all four tenants** (demo, 5,000, 25,000, 50,000) with the real
Gemini provider. All four actions in the definition of done are proven end to end through
the human-approval gate (§15).

Evidence files next to this one:
- `LIVE_TRANSCRIPT.txt` / `_5000.txt` / `_25000.txt` / `_50000.txt` — real conversations
  over HTTP, real LLM, at four company sizes
- `SCALE_HARNESS_RESULTS.txt` / `_25000.txt` / `_50000.txt` — the behavioural runs
- `PROGRESS.md` — the per-unit log, including the things that went wrong on the way

---

## 1. Root causes

### The one that caused most of it: the LLM was asked to decide routing, first

`chat_answer` classified **every** message with the LLM before doing anything else, and
only messages the model labelled `write` ever reached the planner. The pending-question
slot-filling code lived *inside* the planner.

So when the assistant asked "how are you feeling this week (1–5)?" and the user typed
`5`, the classifier saw a bare number, returned `intent: general`, and the reply went
down the **read** path. The slot was never consulted, the same question came back, and
it did so forever. **The slot-filling logic was not broken — it was unreachable.** That
is why it looked so stupid: the feature existed and could not be reached.

The same ordering explains the "intent misrouting" reports. Plainly imperative commands
that the model didn't happen to label `write` — `start my check-in`, `log my mood`,
`shout out to X` — never reached the planner either, and came back as the capability
blurb.

Reproduced before the fix, with the deterministic classifier standing in for the model
exactly as it does live:

```
_fake("5")            → {"intent": "general"}   # never reaches the planner
"start my check-in"   → no plan at all          # capability blurb
```

### "Do the same for X" lost the action

Nothing recorded what the last task *was*. The message fell through to generic planning,
which re-classified it from scratch — so "do the same" became whatever the words alone
suggested. Later, a second variant of this: when the previous action had stalled on a
question, there was no *completed* action to repeat, and the turn fell through to a data
lookup — answering "you don't have access to their data", an answer to a question nobody
asked.

### Templated answers

The answering code was never the problem. It already resolves people scope-aware,
diagnoses risk/pace/weakest-KPI, compares two people, and refuses out-of-scope data
honestly. The problem was that a **misclassified question never reached it**: the
capability blurb went out the moment the LLM said `general`. Not a bad template — a
premature one.

### Team-scoped person lookup

Largely fixed in earlier work (`docs/AGENT_INTEL/`, increment 25), which introduced the
tenant-wide tiered directory resolver. What remained was the *second* resolver: the data
path had its own name matcher, and the two had drifted. Its tokenizer was ASCII-only and
it discarded tokens under three characters.

### Hardcoding

None found in agent logic. Remaining occurrences of demo names are comments and
docstrings describing the bugs that motivated the code. One user-facing string did name
a seed employee ("e.g. *Priya Nair*") and was replaced with a description of the shape of
the answer, since that example means nothing on any other tenant.

```
$ grep -rnE "display_name\s*==\s*[\"']|== *[\"'](Priya|Vera|Aarav|Mei|Ingrid|Ada) " \
      apps/ai/*.py apps/ai/agents/*.py | grep -v tests
  (no matches)
```

---

## 2. What changed, per build file

| Unit | Commit | Change |
|---|---|---|
| B — conversation state | `8b699a0` | `apps/ai/conversation.py`: deterministic turn routing **before** any LLM call. Typed slots, a retry budget, cancel, escape, "do the same". |
| A — person resolution | `f8b39aa` | Email tier; the scale contract put under test; last seed name removed from user-facing text. |
| C — data & reasoning | `2ed404e` | `_is_answerable_data_question` runs before the capability blurb; the not-found reply names the name. |
| D — scale & harness | `c968a0a` | `seed_scale_tenant` (5,000 people, ~2s) + `scripts/agent_scale_harness.py`. Seven bugs found and fixed. |
| E — report | this commit | Report, live transcript script, resolver unification, dead code removed. |

**Unit B — the state machine.** Whether the user is answering a question, cancelling,
repeating the last action, or issuing a command is now decided in Python from session
state and the action registry — facts we already hold. Order per turn: cancel → new
command → answer the pending slot → topic change → invalid answer (re-ask **once**) →
"do the same for X" → imperative command. The LLM keeps open-ended questions and loses
routing. Clarify steps declare *which* slot they wait on (`mood` / `person` /
`kpi_value` / `role`) so a bare `5` is parsed as a mood and a name is not, and a
`slot=None` dead-end can never arm a slot and swallow the next turn.

**Unit E — one resolver.** `_resolve_in_scope` now delegates to the canonical directory
resolver, run twice: over the caller's visible population to answer, then identity-only
tenant-wide to tell "you can't see them" from "they don't exist". The old matcher,
`_pick_named` and a legacy copy were deleted; the 7 tests that guarded them now exercise
the real resolver.

---

## 3. Before → after (from `LIVE_TRANSCRIPT.txt`, real HTTP + real LLM)

**A check-in that completes** — the worst bug:

```
user      › start my check-in
assistant ‹ How are you feeling this week (1–5)? e.g. "start my check-in, mood 4".
user      › 5
assistant ‹ Start this week's check-in with mood 5/5? You can add wins & blockers next.
   approve → {"action": "open_checkin", "status": "done", ...}
```
*Before: `5` re-asked the same question, forever.*

**A recognition for someone outside the manager's team** (Ada manages neither):

```
user      › make a recognition for Priya Nair
assistant ‹ Give Priya Nair recognition for Teamwork? It posts to your team feed …
   approve → {"action": "give_recognition", "status": "done", ...}
```

**"Do the same for X"**:

```
user      › give recognition to Priya Nair for mentoring the new joiners
assistant ‹ Give Priya Nair recognition for Teamwork? …
user      › do the same for Ingrid Garcia
assistant ‹ Give Ingrid Garcia recognition for Teamwork? …
```
*Before: this started a check-in.*

**A reasoned answer, grounded in real rows**:

```
user      › how is Akhil Menon doing this cycle?
assistant ‹ Akhil Menon is currently on track and keeping pace this cycle, showing no
            immediate red flags. The main area to watch is 'Roadmap features delivered'
            for the 'Ship the H1 platform roadmap' goal, which is at 90% of its target.
            Overall, Akhil is performing strongly, and no additional support appears
            necessary at this time.

user      › compare Akhil Menon and Mei Patel
assistant ‹ Both … are currently on track … the 'Roadmap features delivered' KPI … with
            Akhil at 90% and Mei at 86% of target …
```

**An out-of-scope data refusal** (Ada can act on Priya company-wide, but not read her data):

```
user      › how is Priya Nair doing?
assistant ‹ You don't have access to Priya Nair's data — only an admin or HR can see
            everyone across the company. You can ask about the people on your team: …
```

**An unknown name, said plainly**:

```
user      › how is Zebediah Quartermain doing?
assistant ‹ I couldn't find anyone named Zebediah Quartermain — try their full name or
            their email address.
```

**Escape and no-loop**:

```
user      › start my check-in       →  How are you feeling this week (1–5)? …
user      › banana                  →  I need a number from 1 to 5 … e.g. "4". (…)
user      › banana                  →  I still didn't catch that, so I've dropped the
                                       question. … Or tell me something else.

user      › start my check-in       →  How are you feeling this week (1–5)? …
user      › never mind              →  Okay — I've cancelled that. What would you like
                                       to do instead?
```

Typo resolution and duplicate-name disambiguation are proven at volume in the harness
(10/10 typos, and every duplicate offered with emails) rather than in this transcript,
because the demo tenant has few of either.

---

## 4. Scale proof

```
docker compose exec web python manage.py seed_scale_tenant --headcount 5000 --reset
docker compose exec web python scripts/agent_scale_harness.py --people 20
```

**176/176 checks passed** at 5,000 people; also green on seeds 99 and 4242, and 164/164
on a 500-person tenant. People are chosen at random from across the whole company each
run — a fixed list would only prove it works for the people I thought to list.

| Measure | 500 people | 5,000 people | 25,000 people | 50,000 people |
|---|---|---|---|---|
| Queries per resolution | 1 | 1 | 1 | 1 |
| Median latency | 0.5 ms | 0.5 ms | 0.5 ms | 0.5 ms |
| p95 latency | 0.6 ms | 0.5 ms | 0.5 ms | 0.5 ms |
| Unbounded SELECTs | 0 | 0 | 0 | 0 |

**Constant cost, measured rather than asserted.** Every SELECT carries a LIMIT, so the
table is never loaded into Python to be ranked — that is the property that makes 5,000
and 50,000 behave the same. The 50,000 column is a measurement, not an extrapolation
(§14). Seeding 5,000 people with 20,000 goal/KPI/score rows takes ~2 seconds.

### Seven real bugs the harness found that the unit tests did not

1. **The resolver was ASCII-only.** `Zoë Ćirić` and `山田 太郎` matched *nothing* — those
   people were unreachable by the assistant.
2. **Middle initials were dropped**, so `Sofia A. Menon` never matched her own record and
   a colleague called plain `Sofia Menon` won on the remaining tokens.
3. **A precise query was made ambiguous by its own looser form** — hits were pooled
   across candidate phrases, so `Sofia A. Menon` plus its bigram `sofia menon` looked
   like an ambiguity the user never created.
4. **The planner truncated names** — `Aarav A. Moreau` became the subject `Aarav A`,
   which then *replaced* the full name.
5. **"Do the same" lost the action** when the previous turn ended in a question.
6. **The data path had its own name matcher**, drifted ASCII-only and dropping short
   tokens.
7. **The harness was measuring nothing** — it captured SQL on `default`, but this
   deployment has a read replica and the router sends resolver SELECTs there, so "no
   unbounded SELECT" was passing on zero queries.

### A leak I introduced, then closed

Delegating the data path to the directory resolver initially handed it *fuzzy* matching
too. A mistyped guess at a colleague's name then "corrected" to the real person and the
refusal spelled their name out — **a typo became an oracle for people you cannot see.**
Two flags now separate the cases, both covered by tests:

- `allow_fuzzy` — typo tolerance may resolve a **directory** action; a **data** question
  offers an explicit, scope-limited "did you mean…?" instead of acting.
- `require_full_name` — a typed multi-word name must match in full, so a manager asking
  about "Hugo O'Brien" is never answered about "Hana O'Brien" on their own team.

---

## 5. Invariants — unchanged

- **HITL.** Every action is still an inert plan approved step by step. The harness
  asserts a recognition/check-in exists only *after* the approve call.
- **RBAC / tenant / audit.** No gate was weakened. Propose *and* execute both re-check
  capability and scope on the real targets, every turn. Cross-tenant names never resolve
  (tested). The append-only audit log is intact — it blocked my own fixture's `--reset`
  at the database level, which is the guarantee working.
- **Directory vs data.** Resolving a name grants nothing. Tested directly: an employee
  can resolve an out-of-team colleague for a recognition and is still refused that
  colleague's performance data.
- **No fabrication.** Missing data is stated. Injection and social-engineering probes
  (7 per harness run) are all refused.

---

## 6. What to test yourself in the morning

Everything below runs against the stack you already have up.

**1. The demo tenant, by hand** — `http://localhost:8090`, log in as
`ada@acme.test` / `Passw0rd!demo` (a MANAGER), then in the assistant panel:

| Type this | Expect |
|---|---|
| `start my check-in` | it asks for a mood 1–5 |
| `5` | a confirm card, "mood 5/5" — **this is the headline fix** |
| *(approve it)* | the check-in appears on `/checkins` |
| `make a recognition for Priya Nair` | a recognition card (Priya is **not** on Ada's team) |
| `do the same for Ingrid Garcia` | a recognition for **Ingrid**, not a check-in |
| `how is Akhil Menon doing this cycle?` | real numbers, no "I'm a read-only assistant…" |
| `how is Priya Nair doing?` | honest refusal — resolvable for actions, not for data |
| `how is Zebediah Quartermain doing?` | "I couldn't find anyone named Zebediah Quartermain" |
| `start my check-in` then `banana` twice | explains the format once, then lets go |
| `start my check-in` then `never mind` | "Okay — I've cancelled that." |

*Note:* the check-in is once per week by design, so re-testing it in the same week shows
"you already have this week's check-in". To repeat the test, delete it on `/checkins`
first (the transcript script does this automatically).

**2. Re-run my proofs:**

```bash
# unit + integration
docker compose exec web pytest -q                      # expect 1638 passed

# 5,000-person behavioural harness
docker compose exec web python manage.py seed_scale_tenant --headcount 5000 --reset
docker compose exec web python scripts/agent_scale_harness.py --tenant scale
                                                       # expect 276/276, exit 0

# the same, at 25,000 and 50,000 (already seeded as 'scale25' / 'scale50')
docker compose exec web python scripts/agent_scale_harness.py --tenant scale25
docker compose exec web python scripts/agent_scale_harness.py --tenant scale50

# live HTTP, real LLM — the tenant's cast is discovered from the DB, not hardcoded
python3 scripts/agent_live_transcript.py               # expect 15/15
python3 scripts/agent_live_transcript.py --tenant scale50
```

Two traps if you re-run these. `docker compose exec web pytest` runs **inside the web
container**, so a harness or transcript run at the same time is competing for the same
CPU — it inflates the latency numbers and nothing else. And the `ai` throttle bucket is
**per minute** (20/min on a STARTER tenant), so back-to-back transcript runs against the
*same* tenant will 429 partway through; the failures read exactly like logic bugs. Leave
a minute between them.

The scale tenant is separate (`scale`), logs in with `Passw0rd!scale`, and the command
**refuses** to touch `acme`. If you restart the web container, note that gunicorn does
**not** auto-reload — `docker compose restart web` after any code change, or you'll be
testing the old build (this cost me a confusing half hour).

---

## 7. Honest remaining weaknesses

1. ~~**Recognition loses the user's own wording.**~~ **Fixed** after the first draft of
   this report — see §9. It now reads "Give Priya Nair recognition for *mentoring the
   new joiners* (filed under Teamwork)?" and the posted note carries their words.
2. ~~**Real-LLM behaviour is only proven at demo scale.**~~ **Closed** — see §10. The
   live transcript now runs against the 5,000-person tenant too, with the real LLM:
   **15/15**. (The *harness* still uses the deterministic classifier, deliberately —
   the routing it tests is deterministic by design, and 5,000 people × every category
   would be a great deal of quota for no extra signal.)
3. **`--reset` on the scale tenant cannot delete audit-referenced users.** The
   append-only audit log PROTECTs its actors, so a few dozen users per run are *retired*
   (deactivated and renamed out of the way) rather than deleted. Correct, but the table
   grows slowly across resets.
4. ~~**Near-duplicate names are resolved by closeness, not by asking.**~~ **Fixed** —
   see §10. A fuzzy winner must now beat the runner-up by a clear margin; a genuine
   coin toss between "Jon Smith" and "Jon Smyth" is offered as a choice instead of
   guessed.
5. **One re-ask, then the question is dropped.** This is the deliberate cure for the
   infinite loop, but a user who mistypes twice has to restate the whole request. If
   that proves annoying in practice, the budget is one constant (`_MAX_REASKS`).
6. **Intent routing is registry-driven, so an unrecognised phrasing still falls back to
   the LLM.** Now *measured* rather than guessed — see §11: 27 natural phrasings across
   7 actions all route deterministically, and 8 question forms are correctly left alone.
   A phrasing nobody has said yet still relies on the classifier, but the deterministic
   path only ever *adds* correct routing (it never steals a question, asserted), so the
   residual failure mode is the old one, not a new one.

---

## 8. Housekeeping

- Branch `hari/agent-intelligence-v2` only. `main` and `hari/agent-ui-v2` untouched.
- Working tree clean at the final commit; the plan files (`AGENT_MASTER.md`, `A_`…`E_`)
  remain untracked at the repo root as you left them.
- New files: `apps/ai/conversation.py`,
  `apps/core/management/commands/seed_scale_tenant.py`,
  `scripts/agent_scale_harness.py`, `scripts/agent_live_transcript.py`,
  `apps/ai/tests/test_conversation_state.py`, `apps/ai/tests/test_data_and_reasoning.py`,
  `apps/ai/tests/test_person_resolution.py`, and this directory.
- Deleted: `_named_candidates`, `_pick_named` and a legacy resolver copy in
  `apps/ai/agents/chat.py` — orphaned by the resolver unification.

---

## 9. Follow-up: recognition keeps the reason the user gave

Weakness 1 above, fixed rather than left in the list.

**Two causes, not one.** The category must be a configured company value, so "for
mentoring the new joiners" can only ever be filed under Teamwork — correct for
reporting, but the posted note then said "Recognised for Teamwork." and the reason was
gone. Underneath that, the reason never even reached the proposer: the planner's
template `"give recognition to {s}"` can only express verb-plus-name, so the message
arrived as "give recognition to Ingrid Garcia" with everything after the name discarded.

**The fix.** When the user's own message already names the subject, it beats the
template — the template exists to *inject* a subject the message lacks (a resolved
pronoun, a slot answer), not to replace a message that is already complete. Applied to
single-action plans only: in a multi-step ask the full message names other people too,
and each step must stay pinned to its own subject. The reason is then extracted as the
clause after "for" (unless that clause is just the person's name, as in "make a
recognition for Ingrid Garcia") and used as the note, with the value shown as the
category it's filed under. The note is DATA — stored verbatim and approved by the human
first, exactly like a note typed on the Recognition screen.

Live, after the fix:

```
user      › give recognition to Priya Nair for mentoring the new joiners
assistant ‹ Give Priya Nair recognition for mentoring the new joiners (filed under
            Teamwork)? It posts to your team feed — edit the note first if you like.
```

Two tests added. **Full suite 1626 passed; harness still 176/176; live still 15/15.**

---

## 10. Follow-up: a coin toss is offered, and the live proof now runs at 5,000

### Weakness 4 — a near-tie is no longer guessed

Exact fuzzy ties already asked, but a *near* tie (0.94 vs 0.92) silently picked the
winner. With two colleagues whose names differ by a letter — "Jon Smith" and
"Jon Smyth", both seeded on purpose — that is a coin toss deciding who receives
someone's recognition. A fuzzy winner must now beat the runner-up by a margin
(`_FUZZY_MARGIN = 0.05`); everything inside the margin is offered as a choice.

The margin is deliberately small. A real typo lands well clear of everyone else
(0.10+), so this only catches genuine coin tosses — "Priya Niar" → Priya Nair still
resolves outright, and the harness's 10/10 typo checks still pass.

### Weakness 2 — the live transcript runs against the 5,000-person tenant

`agent_live_transcript.py` was demo-only in two ways: the tenant was hardcoded, and so
were the people ("Priya Nair", "Akhil Menon"). The second is exactly what this run's
own rules forbid. It now **discovers its cast from the database** — a manager who
actually has reports, two of those reports, and two people outside their team — so the
same scenarios replay against any tenant:

```bash
python3 scripts/agent_live_transcript.py                  # demo tenant  → 15/15
python3 scripts/agent_live_transcript.py --tenant scale   # 5,000 people → 15/15
```

Both pass with the real Gemini provider. On the 5,000-person run the randomly-chosen
out-of-team recipient was **"Maximilian Alexander Fitzgerald-Montgomery III"** — a
45-character five-part name, resolved and recognised without a hitch, which is a better
test than anything I would have written by hand.

Two things this flushed out:

- **Cast selection has to avoid the deliberate duplicates.** The first run cast
  "Priya Nair" (seeded three times) as both outsiders, so "do the same for X" exercised
  the disambiguation path instead of the one under test. Discovery now prefers unique
  names.
- **The budget has to be reset per scenario, not per run.** Each turn costs several
  metered LLM calls, so a full pass tripped the per-window ceiling partway through and
  every later scenario "failed" with a budget refusal that looked exactly like a logic
  bug. Nine assertions failed for that reason before I spotted it; run in isolation
  they passed 3/3. Worth remembering when reading any failing live run.

Transcripts: `LIVE_TRANSCRIPT.txt` (demo) and `LIVE_TRANSCRIPT_5000.txt` (scale).

**Full suite 1628 passed. Harness 176/176 (seeds 1337/99/4242). Live 15/15 on both
tenants.**

---

## 11. Follow-up: intent phrasing, measured

Weakness 6 said unusual phrasings "still depend on the LLM" without saying how many.
That's an admission, not a finding, so the harness now probes it: **27 natural phrasings
across 7 actions**, plus **8 question forms** that must *not* be claimed.

Both directions matter. Routing a command deterministically is the fix; but if the
router ever claimed a question, "how many goals should I approve?" would become an
approval instead of an answer — a far worse failure than the misrouting it replaced.

The probe immediately found one: **"do my weekly check-in" was classified as a
question.** The question-lead pattern treated any leading `do` as interrogative, so an
imperative starting with "do" was handed to the classifier instead of going straight to
the planner. Only "do *you/i/we/they/he/she/it*" counts now.

While fixing it I removed a duplicate: the same pattern existed in both
`conversation.py` and `chat.py`. Two copies of "what a question looks like" is precisely
how the two name matchers drifted apart, so there is now one definition and `chat.py`
imports it.

**27/27 phrasings route deterministically; 8/8 questions are left alone.** Harness total
is now **211/211** (seeds 1337/99/4242: 211, 210, 208 — the count varies because typo
checks skip near-duplicate names).

---

## 12. Follow-up: the constant-cost claim, tested at 25,000

§4 asserted that "5,000 and 50,000 behave the same". That was an inference from the
query plan, not a measurement, so I built a 25,000-person tenant and measured it.

**It holds.** 1 query and 0.5 ms median at 500, 5,000 and 25,000 people — flat, with no
unbounded SELECT at any size. Seeding 25,000 people with 100,000 performance rows takes
12 seconds. The harness passes **210/210** there and **220/220** at 5,000, and the live
HTTP transcript passes **15/15** against all three tenants with the real LLM.

### The harness was quietly covering nothing

At 25,000 people the typo category **silently vanished** — and still showed green. The
fixture's name pool (50 × 114 = 5,700 pairs) can't fill 25,000 people uniquely, so
almost everyone acquires a near-duplicate variant, and the check skips those by design
(a typo legitimately lands on the closer name). Every candidate was skipped, so the
category ran zero checks and simply disappeared from the output.

A check that tests nothing is worse than one that fails, so two things changed: typos are
now also probed against names that are unique **by construction** (the edge-case names,
whose first names appear in no generated combination), and the harness **states its own
coverage** — "typo tolerance exercised on 5 name(s); 10 skipped as near-duplicates". If
it ever covers nothing again, that is now a failure with an explanation.

A related artefact fixed at the same time: the rival-detection scan filtered on first
name only and truncated at 200, which at 25,000 people (500 people share a first name)
cut off before reaching the variants — so 6 typo checks failed demanding an exact
identity that a near-duplicate makes impossible. It filters on both names now.

### Roles: the two widest scopes were untested

Every scenario had acted as a manager, leaving HRBP and admin — the roles with the
*most* data access — unproven at scale. Added: each gets a real answer for someone
company-wide, and the same person asked about by an employee is still refused. A wide
role existing must not widen anyone else's scope.

Also fixed: the fixture put the deliberately-triplicated "Priya Nair" at index 0, so the
**admin account was one of three people with that name** and every harness line printing
the actor read like a bug. Leadership slots now get ordinary generated names and the
edge cases start after them.

---

## 13. Follow-up: four resolver bugs that only appear above ~10,000 people

§12 restored the typo category at 25,000 by giving the fixture realistic distinct names
(a hyphenated second surname rather than a middle initial, which sat a hair from the base
name). With that category actually running, it failed — and the failures were real.

1. **Truncated token scans decided the winner by row order.** Scoring a candidate per
   matched token is only sound while no token's match set is cut off. At 25,000 people
   ~500 share a forename, past the scan cap, so "Ibrahim Kaminski-Mancini" could miss its
   own forename credit, score 1 instead of 2, and lose to "Ibrahim Kaminski" — which
   happened to fall inside the cap. Replaced with a **SQL intersection tier**: match all
   the words of a typed name at once, then drop words from the end (where typos live).
   A handful of rows, no cap needed, and cheaper than what it replaced.
2. **A surname-only fragment reached a different person.** The first version intersected
   *adjacent pairs*, which for a three-word query also tries the surname pair — so
   "how is Lucia Dubois-Reyes doing?" resolved to the caller, "Leon Dubois-Reyes". Subsets
   are now always a **prefix**, so the forename stays anchored. Same class of mistake as
   answering about "Hana O'Brien" when asked about "Hugo O'Brien".
3. **A subset of the typed name counted as an exact match.** The stop-word bigram of
   "Ibrahim Kaminski-Manciin" is "ibrahim kaminski", which exactly matched a shorter
   colleague and won in tier 1 before anything else ran. Bigrams are now only offered when
   the name IS two words.
4. **Similarity normalised one side only** — the candidate lost its hyphens, the query
   kept them — so punctuation decided which person was meant.

Two more surfaced in the same pass: the probe budget was consumed by junk word-runs
("but tell", "nothing but tell") before reaching the actual name, and `"my manager is off
sick, is X at risk?"` opened with the **caller's own** risk and pace, because a bare "my"
counted as a claim on their own data.

### One thing I got wrong, and what it taught me

My first full-name rule returned early whenever two or more significant words were typed.
That broke five comparison tests, because `"compare"` is a word but not a name. The fix is
to ask the **directory** which typed words are actually somebody's name — "compare"
belongs to nobody, "Lucia" belongs to someone — rather than assuming every token is one.
A stop-list has to guess, and guessing wrong breaks it in both directions: treat "compare"
as a name and comparisons stop working; ignore the forename and the wrong person is
matched.

### A false alarm worth remembering

A full-suite run killed mid-flight left the *reused* test database corrupt, and the next
run reported **176 failures and 679 errors** that had nothing to do with any code change —
including basic tenancy tests. `pytest --create-db` restored it (1628 passed). If you ever
see mass failures across unrelated apps, rule that out before reading a single traceback.

Injection probes also widened from 7 to 19, grouped by the trick each one tries:
instruction override, false authority, social engineering, role-play, exfiltration
framing, destructive, code/markup injection, and an instruction hidden inside a data field.

4 regression tests added. **Harness 232/232 at both 5,000 and 25,000; live 15/15 on all
three tenants; full suite 1628 passed.**

---

## 14. Follow-up: a typo stops being a coin toss, and the proof extends to 50,000

### The metric was measuring the wrong thing

Similarity was a whole-string `difflib` ratio. A shared forename is *half of a two-word
name*, so it dominated the score and drowned out the half where the user actually made
the mistake. Measured over typo pairs and each one's nearest wrong colleague:

| | worst TRUE match | best IMPOSTOR | separated? |
|---|---|---|---|
| difflib (whole string) | 0.900 | 0.905 | **no — overlapping** |
| word-by-word Damerau | 0.817 | 0.833 | yes |

Overlapping distributions is not a threshold that needs tuning, it is a metric that
cannot answer the question. In practice "nora lauretn" scored 0.917 against the Nora
Laurent meant and 0.870 against an unrelated Nora Larsen — inside the tie-break margin,
so one transposed letter came back as "which of these did you mean?".

What replaced it:

- **Damerau edit distance, not shared subsequence.** difflib's ratio is generous on short
  words to the point of uselessness: "lauretn" scores 0.77 against "larsen", a completely
  different surname, purely for sharing l/a/r/e/n *in order*. Adjacent letters SWAPPED
  count as one mistake rather than two, because a transposition is the most common way a
  name gets mistyped.
- **Word paired with word**, one-to-one and scored both ways, so a name with a part
  MISSING is penalised rather than rewarded — otherwise "Lucas Cardoso" beats "Lucas
  Cardoso-Ismail" on a query naming all three.
- **A shortlist, then the careful comparison.** A shared forename ties a thousand people;
  the blunt ratio is good enough to say which forty are worth looking at properly and
  never good enough to decide.
- **Disambiguation lists rank by closeness, not alphabetically.** Asked about "Nora
  Lauretn" the eight names offered back were Nora Abbott through Nora Abbott-Hartmann —
  the Nora Laurent she meant was not among them. A list that cannot contain the answer is
  worse than no list.

### The calibration I nearly missed

The rewrite broke an existing typo test, and the failure was right. `_FUZZY_MIN = 0.82`
was calibrated for difflib; the same names simply score lower on the new metric. "akil
menonn" → Akhil Menon — a mistake in *each* word — scores 0.817, so the assistant
answered **"no such person" to an obvious typo**. The floor is now 0.78, which on this
metric reads as "about one mistyped character per word". This is not a loosening: what
stops a wrong name being ACTED on is the runner-up margin, not the floor, and the floor
only decides whether the best guess is worth considering at all.

### Two properties measured rather than asserted

- **The intersection cap has headroom.** Over 300 random people in the 50,000-person
  tenant, the largest full-name intersection is **17 rows** against a cap of 60.
- **The shortlist never drops the answer.** In the worst cohort — 1,003 people sharing
  the forename "Priya" — a transposed-letter surname typo ranks the true person **first**
  in 40/40 trials. It orders candidates; it does not discard them.

### A false reading worth recording, twice in one session

Run *concurrently with the full test suite*, the harness showed resolution latency rising
0.5 → 1.3 → 1.6 ms across 5k/25k/50k, and I was ready to report the flat-cost claim as
broken. Measured without contention it is **0.5 ms median at every size**. Minutes later
a live-transcript capture came back 6/15 — HTTP 429 on the `ai` bucket, because the
passing run and the capture fell inside the same per-minute window. Both readings look
exactly like logic failures and neither was. Measure the machine you think you are
measuring; §13 records the same lesson about a corrupt reused test database.

2 regression tests added, 33 in `test_person_resolution.py`. **Harness 239/239 at 5,000,
25,000 AND 50,000** — 1 query per lookup, 0.5 ms median, no unbounded SELECT at any size,
typo tolerance 17/17 with none skipped. **Live 15/15 on all four tenants** with the real
LLM. **Full suite 1635 passed**, 7 deselected.

---

## 15. Follow-up: the other two actions end to end — and Agent-1 had never worked

### The gap in my own proof

The definition of done names four actions. Two of them — recognition and the check-in —
were proven all the way to a created row. The other two were proven only at the **routing
level**: that "start a 360 for X" is *recognised* as a 360. That is the easy half, and I
had been reporting it as coverage. It says nothing about whether the right person ends up
on the cycle, whether the human gate holds, or whether the scope check survives at 50,000
people.

Both are now end to end, and both assert **each half of the HITL gate separately** —
proposing must create nothing, approving must create exactly one thing. Checking only the
second half would pass just as well if the plan had already written the row.

The 360 also asserts the refusal, because unlike recognition it is **data-scoped**: you
may recognise anyone in the company, but you may not open a feedback cycle on somebody
you cannot see. The person used for that check is outside the manager's whole reporting
*subtree* — a report-of-a-report is in scope, so using one would have asserted the
opposite of what the check means.

**The new checks were mutation-tested.** A check that passes the first time has not been
shown to work. Sabotaged to ask about the wrong person, "the 360 names the right subject"
went 6/6 → **0/6** and "the draft picks the named person's review" → **1/3** — the single
pass being the case where the wrong person happens to be the right one.

### What it found within minutes: Agent-1 had never once succeeded

Covering the execute seam meant real Agent-1 jobs got queued, and **every one failed**
with `PROVIDER_ERROR`. Not something tonight broke: the demo tenant showed 2/2 failed from
well before. In product terms — a manager asks for a review draft, approves it, and
nothing ever lands; the review sits in `AI_DRAFTING` indefinitely.

The chain is worth reading in order, because each link individually looks fine:

1. `config/settings/base.py` sets `LLM_MAX_TOKENS = 4096`, with a comment explaining that
   900 truncates a Gemini "thinking" model — it spends output tokens reasoning before it
   emits the JSON. **So this was already known and already fixed.**
2. `docker-compose.yml`, `docker-compose.prod.yml` and `.env` all pinned **900**. The fix
   was silently overridden by the deployment — in the production compose too.
3. The provider called the result **"Gemini returned non-JSON content."** It reads
   `finish_reason` already, but only to lower a confidence score, and the JSON parse
   throws before that. So the only message anyone ever saw blamed the model and the
   prompt, when the cause was our own ceiling cutting a valid response mid-string.

Step 3 is why steps 1–2 survived. A wrong diagnosis is more expensive than no diagnosis:
the two causes need opposite fixes, and the message pointed firmly at the wrong one.

All three are fixed — compose defaults raised to match settings, and both providers (the
OpenAI sibling had the identical defect) now distinguish truncation from a broken model.

**Verified against the live provider, not a mock:** one Agent-1 job on the 5,000-person
tenant returned `JOB SUCCEEDED`, moved the review to **`PENDING_HUMAN_REVIEW`** — the HITL
gate intact, nothing auto-applied — and wrote 957 characters of grounded prose citing that
person's real 74% attainment and AT_RISK band.

### The guard matters more than the fix

A settings fix that a deployment overrides is not a fix, and nothing in the suite compared
the two numbers. `test_compose_never_pins_the_token_budget_below_the_settings_default`
parses both compose files and fails if either pins below `settings.LLM_MAX_TOKENS`.
Confirmed by re-pinning 900 and watching it fail (`assert 900 >= 4096`) before reverting.

3 tests added. **Harness 276/276 at 5,000, 25,000 and 50,000. Full suite 1638 passed.**

One honest limit: the harness asserts the job is *queued* by the approval, not that the
worker later succeeds. That last step was verified by hand against the live provider,
because the harness runs on the deterministic fake on purpose — what it tests is routing
and retrieval, which must not depend on a model's mood.

---

## 16. Follow-up: the other two agent jobs the assistant can start

Having found that Agent-1 had never once succeeded, the obvious question was what else the
assistant can start. It enqueues **three** kinds of agent job — `agent1` (review),
`career_roadmap`, `agent4` (succession) — and only the first had any run history at all.
An action that says "requested" and never delivers is the same defect whichever agent sits
behind it.

- **`agent4` (succession)** — SUCCEEDED. The token-ceiling fix generalised, as expected.
- **`career_roadmap`** — FAILED `EMPLOYEE_NOT_FOUND`. A different bug, and a total one.

### The career agent could never have worked

The seam is `generate_roadmap(tenant_id, employee_id, target_ref, …)`. The assistant's
`_execute_career_enrich` enqueued the **roadmap's own id** as the job's target and set no
params at all. So the worker looked up a `User` by a roadmap's id — which misses every
time — and even given the right employee would then have skipped with "target not found".
Two mismatches in one call, in the only code path that produces this job from chat.

### I fixed it in the wrong place first, and that was the useful part

My first fix taught the dispatcher to translate a roadmap id into an employee. It broke
`test_enrich_enqueues_job_degraded_and_roadmap_unchanged`, which revealed a **second
caller**: `RoadmapEnrichView` has been sending the correct shape all along —
`target_id=roadmap.employee_id`, with `target_ref` in params. The contract was never
ambiguous and the dispatcher was never wrong. The assistant simply did not follow the
contract that its own comment claims to mirror.

Reverted, and fixed at the enqueue site instead: one contract, one place. Had I only run
the tests I thought were relevant, I would have shipped a dispatcher that quietly accepted
two incompatible meanings for the same field.

Live result: **SUCCEEDED**, a new `source=AI`, `status=DRAFT` roadmap with 3 tiers and
`advisory=True`; the deterministic baseline untouched and adoption still a human step.

### Why the suite never caught it

The seam's own tests call `generate_roadmap` directly with the right arguments. The two
`career_enrich` action tests stopped at "a job was enqueued" — and **asserted the broken
shape** (`target_id == rm.id`), so the bug had test coverage confirming it. The seam was
covered, the enqueue was covered, and the join between them was covered by nothing.

That is the shape of both of tonight's product bugs: each piece correct in isolation, the
join assumed. A settings default and the compose pin that silently overrides it (§15); a
seam and the caller that feeds it (here). Both were found by extending a test to the next
link in the chain rather than by reading code.

The two misleading tests now assert the real contract, and a new one runs the assistant's
own job through the real dispatcher to a finished draft — the check whose absence let a
total failure sit unnoticed. The other four seams each take their own artifact's id, which
is what the dispatcher passes; checked rather than assumed.

**Full suite 1639 passed.**
