# AGENT_REBUILD — report

**Branch:** `hari/agent-intelligence-v2` (nothing merged to `main` or `hari/agent-ui-v2`)
**Status:** all five build files executed, plus follow-ups (§9–§12). Backend
suite **1628 passed**, scale harness **220/220 at 5,000** and **210/210 at 25,000**
people, live HTTP transcript **15/15 on all three tenants** (demo, 5,000, 25,000) with
the real Gemini provider.

Evidence files next to this one:
- `LIVE_TRANSCRIPT.txt` / `_5000.txt` / `_25000.txt` — real conversations over HTTP,
  real LLM, at three company sizes
- `SCALE_HARNESS_RESULTS.txt` / `_25000.txt` — the behavioural runs
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

| Measure | 500 people | 5,000 people | 25,000 people |
|---|---|---|---|
| Queries per resolution | 1 | 1 | 1 |
| Median latency | 0.5 ms | 0.5 ms | 0.5 ms |
| p95 latency | 0.6 ms | 0.5 ms | 0.5 ms |
| Unbounded SELECTs | 0 | 0 | 0 |

**Constant cost, measured rather than asserted.** Every SELECT carries a LIMIT, so the
table is never loaded into Python to be ranked — that is the property that makes 5,000
and 50,000 behave the same. Seeding 5,000 people with 20,000 goal/KPI/score rows takes
~2 seconds.

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
docker compose exec web pytest -q                      # expect 1624 passed

# 5,000-person behavioural harness
docker compose exec web python manage.py seed_scale_tenant --headcount 5000 --reset
docker compose exec web python scripts/agent_scale_harness.py --people 20
                                                       # expect 176/176, exit 0

# live HTTP against the demo tenant, real LLM
python3 scripts/agent_live_transcript.py               # expect 15/15
```

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
