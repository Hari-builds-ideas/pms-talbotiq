# AGENT_REBUILD — progress log

Branch: `hari/agent-intelligence-v2`. Plan: `AGENT_MASTER.md` + `A_…` … `E_…` at repo root.
Each unit: implement → test → commit → log here. **Resume from the last "RESUME HERE".**

Prior related work (a separate, earlier effort) is logged in `docs/AGENT_INTEL/PROGRESS.md`
through increment 25; this file starts the AGENT_REBUILD run.

---

## Unit B — conversation state machine (Bugs 1–4)

### The root cause, which turned out to be ONE ordering mistake

`chat_answer` asked the **LLM to classify every message first**, and only messages the
model labelled `write` ever reached `build_plan`. The pending-question slot-filling code
lived *inside* `build_plan`.

So when the assistant asked "how are you feeling this week (1–5)?" and the user typed
`5`, the classifier saw a bare number, returned `intent: general`, and the reply went
down the **read** path. The slot was never consulted. The user re-asked, got the same
question, forever. The slot-filling logic was not broken — **it was unreachable**.

The same ordering caused the "intent misrouting" reports: plainly imperative commands
the model didn't happen to label `write` (`start my check-in`, `log my mood`,
`shout out to Ada`, `praise X`) never reached the planner either, and came back as the
capability blurb.

Verified before the fix, with the deterministic fake classifier standing in for the
model exactly as it does live:

```
_fake("5")                 → {"intent": "general"}   # never reaches the planner
"start my check-in"        → no plan at all          # capability blurb
```

### What changed

**New `apps/ai/conversation.py`** — a deterministic state machine that runs *before* any
LLM call. Whether the user is answering a question, cancelling, repeating the last
action, or issuing a command is decided in Python from session state + the action
registry — facts we already hold. The model keeps open-ended questions and loses
routing. Per turn, in order: cancel → new command → answer the pending slot → topic
change → invalid answer (re-ask **once**) → "do the same for X" → imperative command.

**Typed slots.** `_clarify(...)` now declares *which* detail it waits on
(`mood` / `person` / `kpi_value` / `role`), so the next message is parsed with the right
parser: a bare `5` answers a mood question, a name answers a "who?" question. `slot=None`
marks a dead-end message so it can never arm a slot and swallow the next turn.

**A retry budget.** One re-ask, stating the expected format, then the slot is abandoned.
The endless re-ask *was* the bug, so the loop is now structurally impossible.

**Planner helpers** — `fill_slot`, `repeat_action`, `persist_clarify`. Scope is never
inherited across turns: each re-runs the propose function, which re-resolves the subject
and re-checks capability + scope from scratch.

### Three further real bugs found while testing

1. **An unresolved pronoun erased the real name.** "praise Ingrid Garcia for **her**
   work" → the subject extractor grabs `her` → doesn't resolve → the pronoun was passed
   on *as a name*, synthesizing "give recognition to her", which resolves to nobody →
   "who would you like to recognise?" It now falls back to the original message, where
   the name still is.
2. **Duplicate steps.** "start my check-in, mood 4" splits on the comma into two clauses
   that both match `open_checkin`, offering the identical step twice. Now de-duplicated
   on (action, resolved params); genuinely different params still produce two steps.
3. **Missing intent triggers.** `shout out`, `shout-out`, `praise`, `props to` now route
   to recognition; `log my mood` routes to the check-in. `thank(s)` is deliberately *not*
   a trigger — a bare "thanks!" is conversation, not a command.

### Before → after

| Turn | Before | After |
|---|---|---|
| "start my check-in" | capability blurb, no plan | asks the mood (routed to `open_checkin`) |
| → "5" | same question again, forever | check-in confirm step, `mood=5` |
| → "banana" | same question again, forever | "I need a number from 1 to 5…", re-asked **once** |
| → "banana" again | same question again, forever | question dropped, user unblocked |
| "make a recognition for Ingrid Garcia" mid-check-in | ignored, question re-asked | check-in abandoned, recognition started |
| "never mind" | ignored | slot cleared, acknowledged |
| recognition → "do the same for Ingrid Garcia" | started a CHECK-IN | recognition for Ingrid |
| "praise Ingrid Garcia for her work" | "who would you like to recognise?" | recognition for Ingrid |
| "shout out to X" / "log my mood" | capability blurb | correct action |

### Tests

`apps/ai/tests/test_conversation_state.py` — 18 tests, all reproducing a live bug first:
pending-slot capture (bare number, worded mood, up-front mood), invalid-answer re-asks
once then gives up, end-to-end check-in creation **only after approve** (HITL intact),
new-command-mid-pending abandons and starts, explicit cancel clears (and really clears),
"do the same for X" repeats the action, "do the same" resolves an out-of-team person,
and 9 parametrized intent-routing cases.

**Full suite: 1590 passed, 7 deselected.** No RBAC/HITL/tenant/audit change: every action
is still an inert plan approved step by step, and every propose/execute re-checks
capability and scope.

**RESUME HERE → live verification of Unit B against the running stack, then Unit A**
(resolver hardening: email match, duplicate-name disambiguation, query-count-at-scale),
then C (reasoning), D (5,000-person seed + harness), E (report).

---

## Unit A — one company-wide, DB-backed person resolver

### State on arrival
Increment 25 (earlier effort) had already built `apps/ai/directory.py` with the tiered
resolver, the company-wide directory population for recognition, and the
`(tenant, display_name)` index. This unit closed the remaining gaps in
`A_PERSON_RESOLUTION.md` and put the contract under test.

### What changed
- **Tier 0: exact email.** Email is the one unique handle a person has, so it is now
  checked before anything else and is never ambiguous. This is also what makes a genuine
  duplicate-name disambiguation *actionable* — we list both people with their emails, and
  the user replies with one.
- **No seed person in user-facing text.** The person re-ask said 'e.g. "Priya Nair"',
  which is meaningless on any other tenant. It now asks for the shape of the answer
  ("their full name, or their email address").
- Verified by grep that no person name appears in agent *logic* — remaining occurrences
  are comments and docstrings describing the bug that motivated the code.

### Scale, measured rather than asserted
- `(tenant, email)` and `(tenant, display_name)` indexes both already exist.
- **Query count is constant in headcount** — the same 2 queries resolve an exact full
  name in a 5-person tenant and a 205-person one (parametrized test).
- **Every SELECT carries a LIMIT.** Proven by capturing the SQL for a token shared by
  120 people: the table is never loaded into Python to be ranked. This is the property
  that makes 5,000 and 50,000 behave the same.
- Disambiguation lists are capped at 8 however many match.

### Tests
`apps/ai/tests/test_person_resolution.py` — 14 tests: exact full name out-of-team,
email (settling a real name clash), shared-first-name not drowning out an exact match,
unique first name, typo → right person, real duplicates → disambiguation *with emails*,
unknown name → honest not-found, cross-tenant name never resolves, **directory resolves
company-wide while data stays scoped**, naming a colleague leaks no performance detail
end-to-end, constant query count at two tenant sizes, every query LIMITed, capped
candidate list.

768 passed across ai + recognition + identity + rbac.

**RESUME HERE → Unit C** (real data + reasoned answers; the capability blurb must never
answer an answerable question), then D (5,000-person seed + harness), then E (report).

---

## Unit C — real data, real reasoning, and never the leaflet

### Root cause
The answering code was never the problem — it already resolves people scope-aware,
diagnoses risk/pace/weakest-KPI, compares two people, suggests typo corrections, and
refuses out-of-scope data honestly. The problem was that **a misclassified question
never reached it**. `chat_answer` returned the capability blurb the moment the LLM
labelled a message `general`, so a specific, answerable question got a brochure. That
is the "templated answers" complaint: not a bad template, a *premature* one.

### What changed
- **`_is_answerable_data_question`** runs before the general fallback. Two deterministic
  signals: performance vocabulary, or a QUESTION that names somebody the directory
  knows. If either fires, the message goes down the performance path instead of being
  deflected. The question-form gate matters — a stray word that happens to prefix a
  colleague's name must not turn "what day is today?" into a report on that person.
- Salvaging changes only WHICH path runs. The performance path still resolves the
  person itself and still applies the full scope gate, so this can widen no access —
  asserted by a test where an out-of-scope person's data stays refused after salvage.
- Employee "who on my team…" questions are excluded from salvage, so a demoted team
  search can't be re-routed into a self-report dressed as a team answer.
- **The not-found now names the name.** "I couldn't find anyone by that name" left the
  user unsure whether we misread them; it now echoes what they typed.

### One thing I got wrong first, and fixed
The first version said "I can't find anyone named X **in your company**". Two existing
tests caught it, and the second failure was the more interesting one: on a two-person
comparison the echoed text became "Mona Manager Pax Peer", and the sentence asserted
those people don't exist company-wide — a claim that branch has not checked (they may
simply be out of scope). Now it echoes only 1–3 tokens and never claims non-existence.

### Tests
`apps/ai/tests/test_data_and_reasoning.py` — 9 tests. The key move: a `blind_classifier`
fixture that labels EVERY message `general`, reproducing the live failure exactly, then
asserting a real answer still comes back. Covers: misclassified person question, own-data
question, unknown name answered specifically, genuine small talk still redirected,
capability question still gets the capability answer, two people with different data get
materially different answers (the template detector), comparison returns both, and two
scope-safety tests.

**Full suite: 1613 passed, 7 deselected.**

**RESUME HERE → Unit D** (5,000-person seed command + behavioural scale harness), then E.

---

## Unit D — 5,000-person tenant + behavioural scale harness

### What was built
- **`apps/core/management/commands/seed_scale_tenant`** — a synthetic tenant (default
  5,000 people, `--headcount`, `--tenant`, `--reset`). Deterministic, idempotent,
  refuses to touch `acme`/`globex`, and refuses to run with `DEBUG` off without
  `--force`. 5,000 people + 20,000 goal/KPI/score rows in **~2 seconds** (bulk_create
  and one shared password hash — 5,000 Argon2 hashes would dominate the runtime and
  prove nothing). Seeds the awkward cases on purpose: real duplicate names, a first
  name that is someone else's surname, accents, non-Latin script, apostrophes/hyphens,
  very long names, and near-duplicates a typo could land between.
- **`scripts/agent_scale_harness.py`** — exercises the assistant end to end against
  that tenant, as several roles, over MANY randomly chosen people (`--seed` makes any
  run reproducible). It asserts behaviour, not absence of exceptions, and exits
  non-zero on any failure.

### Result: 176/176 checks at 5,000 people (and green on seeds 1337 / 99 / 4242)
Resolution: **1 query, 0.5 ms median** — and *identical* at 500 people, which is the
constancy claim actually measured rather than asserted. No unbounded SELECT.

### Seven real bugs the harness found that the unit tests did not
1. **The resolver was ASCII-only.** `_name_tokens` used an `[a-z]` class, so
   `Zoë Ćirić` and `山田 太郎` matched *nothing* — those people were unreachable by
   the assistant. Now Unicode-aware.
2. **Middle initials were dropped**, so `Sofia A. Menon` never matched her own record
   and a colleague called plain `Sofia Menon` won on the remaining tokens. Tier 1 now
   matches verbatim name-shaped spans, and `A.` is read as an initial, not the article.
3. **A precise query was made ambiguous by its own looser form** — hits were pooled
   across every candidate phrase, so `Sofia A. Menon` (one person) plus its bigram
   `sofia menon` (a different person) looked like an ambiguity the user never created.
   The most specific phrase now wins outright.
4. **The planner truncated names.** Its subject regex took one word plus at most one
   more capitalised word, so `give recognition to Aarav A. Moreau` produced the subject
   `Aarav A` — which then *replaced* the full name, turning an exact match into "which
   Aarav do you mean?". It now reuses the directory's span logic.
5. **"Do the same" lost the action when the previous turn ended in a question.** If the
   earlier recognition stalled on "which one?", `last_action_in_session` found no
   completed action and fell through to a data lookup — answering "you don't have
   access to their data", an answer to a question nobody asked.
6. **The data path had its OWN name matcher** (`_named_candidates`), violating A's "no
   intent may do its own ad-hoc matching". It had drifted: ASCII-only, and it discarded
   tokens under three characters. `_resolve_in_scope` now delegates to the canonical
   directory resolver — twice: over the caller's visible population to answer, then
   identity-only tenant-wide to tell "you can't see them" from "they don't exist".
7. **The harness was measuring nothing.** It captured SQL on the `default` connection,
   but this deployment has a read replica and the router sends resolver SELECTs there —
   so "no unbounded SELECT" passed on zero queries. It now captures across every
   connection and fails if a lookup records no queries at all.

### And one leak I introduced, then closed
Delegating the data path to the directory resolver initially handed it *fuzzy* matching
too — so a mistyped guess at a colleague's name "corrected" to the real person and the
refusal spelled their name out. A typo became an oracle for people you cannot see. Two
flags now separate the cases, and both are covered by tests:
- `allow_fuzzy` — typo tolerance resolves a DIRECTORY action ("post a kudos to the
  person you obviously meant"); a DATA question offers an explicit, scope-limited
  "did you mean…?" instead of acting.
- `require_full_name` — a typed multi-word name must match in full, so a manager asking
  about "Hugo O'Brien" is never answered about "Hana O'Brien" on their own team.

### A fixture bug worth recording
The first 5,000-person tenant made ~3,000 people accidental duplicates: the surname
stride (351) shared a factor with the pool size (114), so each first+last pair recurred
every 38 blocks. Everything then "correctly" disambiguated and the harness could not
tell a resolver bug from a fixture artefact. The pairing is now a bijection, and the
seed *fails loudly* if it ever produces more duplicates than EDGE_NAMES intended.

### Tests
10 more in `test_person_resolution.py` (non-ASCII names, middle initials, precise-vs-
loose, fuzzy on directory but not data, the typo-oracle leak end to end, full-name
matching), and the query-cost tests now compare 5 vs 505 people rather than pinning an
exact number — the contract is "constant and small", and pinning the count turned a
genuine optimisation (2 queries → 1) into a failure.

**Full suite: 1624 passed. Harness: 176/176 at 5,000 people, 164/164 at 500.**

**RESUME HERE → Unit E** (REPORT.md + live proof against the demo tenant over HTTP).

---

## Unit E — report, live proof, and one resolver for real

### Live proof
`scripts/agent_live_transcript.py` — real HTTP to localhost:8090, real logged-in user,
real Gemini provider, demo tenant. **15/15 assertions**, transcripts captured verbatim in
`LIVE_TRANSCRIPT.txt`. Every headline fix demonstrated end to end, including approving
the answered check-in and the out-of-team recognition (both `status: done`).

Two things this flushed out that in-process testing could not:
- **gunicorn does not auto-reload.** The first live run tested a two-hour-old build and
  showed the old broken behaviour. `docker compose restart web` after code changes.
- **The API does not serialize step params** (they're internal), so live assertions read
  the step's action/feel/summary — which is all the SPA and the user ever see anyway.

### Finished the "one resolver" requirement
`_resolve_named_person` — a test-only entry point — was still calling the old bespoke
matcher, which meant 7 tests were guarding code production no longer used. It now
delegates to the canonical resolver on the same strict settings the data path uses, and
`_named_candidates`, `_pick_named` and the legacy `_resolve_in_scope` copy are deleted.
All 7 tests still pass, now against the real thing.

Bounding fell out of that: the injection test ("really " × 80 + a name) would otherwise
have produced an 80-word exact-match phrase and, under `require_full_name`, demanded all
80 words appear in someone's name. Long runs now emit short trailing windows instead,
and the exact tier probes at most 8 phrases per turn — so a rambling message can't turn
into a long series of queries.

### Final state
- Backend suite **1624 passed**, 7 deselected.
- Scale harness **176/176** at 5,000 people (also 164/164 at 500; green on seeds 1337 /
  99 / 4242).
- Live transcript **15/15**.
- `docs/AGENT_REBUILD/REPORT.md` written, including six honest remaining weaknesses.

**RUN COMPLETE.** Nothing merged to `main` or `hari/agent-ui-v2`.

---

## Follow-up 1 — recognition keeps the reason the user gave

First of the documented weaknesses, fixed rather than left in the list.

**Two causes.** The category must be a configured company value, so "for mentoring the
new joiners" files under Teamwork and the note read "Recognised for Teamwork." — the
reason discarded. Underneath that, the reason never reached the proposer at all: the
planner's template `"give recognition to {s}"` expresses verb-plus-name and nothing
else, so the message arrived as "give recognition to Ingrid Garcia".

**Fix.** When the user's own message already names the subject, prefer it over the
template — the template exists to *inject* a subject the message lacks (a resolved
pronoun, a slot answer), not to replace a complete message. Single-action plans only: a
multi-step ask names other people in the same string, and each step must stay pinned to
its own subject. The reason is the clause after "for" unless that clause is just the
person's name ("make a recognition for Ingrid Garcia"), and it becomes the note; the
value is shown as what it's filed under. The note is DATA — stored verbatim, human
approves first.

Live: "Give Priya Nair recognition for mentoring the new joiners (filed under Teamwork)?"

2 tests. Full suite **1626 passed**, harness **176/176**, live **15/15**.

**RESUME HERE → remaining documented weaknesses in REPORT.md §7**, most valuable first:
(2) a real-LLM run at larger scale, (4) near-duplicate typo handling, (6) more intent
phrasings. None is blocking; the run's stated goals are all met.

---

## Follow-up 2 — near-tie disambiguation + live proof at 5,000

**Weakness 4 (fixed).** Exact fuzzy ties already asked; a *near* tie (0.94 vs 0.92)
silently picked a winner. Between "Jon Smith" and "Jon Smyth" that is a coin toss
deciding who receives someone's recognition. A fuzzy winner must now clear the
runner-up by `_FUZZY_MARGIN = 0.05`; anything inside the margin is offered as a choice.
Small on purpose — a real typo lands 0.10+ clear, so ordinary typo tolerance is
unaffected (harness still 10/10 on typos). 2 tests.

**Weakness 2 (closed).** `agent_live_transcript.py` hardcoded both the tenant and the
people — the latter being exactly what this run's rules forbid. It now discovers its
cast from the DB (a manager with real reports, two of them, two people outside the
team) and takes `--tenant` / `--password`, so the same scenarios replay anywhere:

    python3 scripts/agent_live_transcript.py                  # acme  → 15/15
    python3 scripts/agent_live_transcript.py --tenant scale   # 5,000 → 15/15

Both with the real Gemini provider. The 5,000-person run happened to cast
"Maximilian Alexander Fitzgerald-Montgomery III" as the out-of-team recipient — a
five-part 45-character name, resolved and recognised correctly.

Two traps found while doing it:
- cast selection must avoid the deliberately-duplicated names, or "do the same for X"
  tests the disambiguation path instead of the one intended;
- the LLM budget must be reset per SCENARIO, not per run. Nine assertions failed on the
  first full scale pass purely because the per-window ceiling tripped partway through;
  the same scenarios passed 3/3 in isolation. A budget refusal reads exactly like a
  logic bug — worth remembering.

Full suite **1628 passed**; harness **176/176** on three seeds; live **15/15** on both
tenants.

**RESUME HERE → remaining weaknesses are REPORT.md §7 items 3, 5, 6** — all minor and
deliberate (retired audit-referenced users, the one-retry budget, and intent phrasings
that still fall back to the classifier). The plan's stated goals are met and proven.

---

## Follow-up 3 — intent phrasing, measured rather than assumed

Weakness 6 claimed unusual phrasings "still depend on the LLM" without quantifying it.
The harness now probes both directions: **27 natural phrasings across 7 actions** must
route deterministically, and **8 question forms** must NOT be claimed by the router
(if it ever claimed one, "how many goals should I approve?" would become an approval —
worse than the misrouting it replaced).

It found one immediately: **"do my weekly check-in" was treated as a question**, because
the question-lead pattern matched any leading `do`. Imperatives starting with "do" were
therefore handed to the classifier instead of going straight to the planner. Only
"do you/i/we/they/he/she/it" is interrogative now.

Also de-duplicated: the same pattern existed in `conversation.py` and `chat.py`. Two
copies of "what a question looks like" is how the two name matchers drifted apart, so
there's one definition now and `chat.py` imports it.

27/27 phrasings, 8/8 questions. Full suite **1628 passed**; harness **211/211** (seeds
1337/99/4242 → 211/210/208; the count varies because typo checks skip near-duplicates);
live **15/15** on both the demo and 5,000-person tenants.

**RESUME HERE → REPORT.md §7 items 3 and 5 only** — retired audit-referenced users
(correct, minor) and the deliberate one-retry budget. Both are design choices rather
than defects. The plan's goals are met, proven, and documented.

---

## Follow-up 4 — constant cost tested at 25,000, and a harness that was testing nothing

**The claim, measured.** §4 asserted 5,000 and 50,000 "behave the same" from the query
plan rather than from a measurement. Built a 25,000-person tenant (12s to seed, 100k
performance rows) and measured: **1 query, 0.5 ms median at 500 / 5,000 / 25,000** —
flat, no unbounded SELECT at any size. Harness **210/210** at 25,000, **220/220** at
5,000, live HTTP **15/15** on all three tenants with the real LLM.

**The harness was silently covering nothing.** At 25,000 the typo category *disappeared*
and still showed green: the fixture's 5,700 unique name pairs can't fill 25,000 people,
so nearly everyone gains a near-duplicate variant and the check skips those by design.
Every candidate was skipped → zero checks → category gone from the output. Fixed two
ways: typos are also probed against names unique BY CONSTRUCTION (edge-case names, whose
first names appear in no generated combination), and the harness now states its own
coverage ("exercised on 5 name(s); 10 skipped as near-duplicates"), so covering nothing
is a failure rather than an absence.

Related artefact: rival detection scanned by first name only, capped at 200 — at 25,000
people 500 share a first name, so the cap cut off before the variants and 6 typo checks
failed demanding an identity a near-duplicate makes impossible. Filters on both names now.

**Roles.** Every scenario had acted as a manager; HRBP and admin — the widest data scopes
— were unproven. Added: each gets a real answer company-wide, and the same person asked
about by an employee is still refused.

**Fixture wart.** The deliberately-triplicated "Priya Nair" sat at index 0, so the ADMIN
account was one of three people with that name and every harness line printing the actor
read like a bug. Leadership slots now take ordinary generated names.

Full suite **1628 passed**.

**RESUME HERE → nothing substantive is outstanding.** REPORT.md §7 leaves only items 3
and 5, both deliberate design choices (retired audit-referenced users; the one-retry
budget). Further iterations would be polish: more phrasings, more injection probes, or a
larger fixture name pool so typo coverage is full at 25,000+ rather than partial.

---

## Follow-up 5 — full typo coverage at 25,000, and four scale-only resolver bugs

**Fixture.** The collision fallback was a middle initial ("Aarav A. Sharma"), unique but
a hair from "Aarav Sharma" — so at 25,000 people almost everyone had a near-twin and the
typo check (which must skip near-twins) covered nothing. It's now a hyphenated second
surname ("Theo Kim-Muller"): unique AND well separated. Near-duplicate families dropped
from ~20,000 people to **5** — only the deliberate EDGE_NAMES ones. Typo coverage is now
15/15 at both sizes.

**Injection probes** widened from 7 to 19, grouped by the trick each tries: instruction
override, false authority, social engineering, role-play, exfiltration framing,
destructive, code/markup injection, and an instruction hidden inside a data field.

**Four resolver bugs, all invisible below ~10,000 people:**

1. **Truncated token scans biased the winner.** Per-token scoring is only sound while no
   token's match set is truncated; at 25,000 ~500 share a forename, past the cap, so
   "Ibrahim Kaminski-Mancini" could miss its own "ibrahim" credit and lose to "Ibrahim
   Kaminski" — decided by arbitrary row order. Replaced by a SQL intersection tier
   (match all the words of a typed name at once, then drop words from the end), which
   returns a handful of rows and needs no cap.
2. **A surname-only fragment picked a different person.** The first version intersected
   *adjacent pairs*, which for a three-word query includes the surname pair — so "how is
   Lucia Dubois-Reyes doing?" resolved to the caller, who was "Leon Dubois-Reyes". Subsets
   are now always a PREFIX, anchoring the forename.
3. **A subset of the typed name counted as an exact match.** The stop-word bigram of
   "Ibrahim Kaminski-Manciin" is "ibrahim kaminski", which exactly matched a shorter
   colleague and won outright in tier 1. Bigrams are now only offered when the name IS
   two words.
4. **Similarity normalised one side only.** The candidate lost its hyphens, the query
   kept them, so a typo scored better against the shorter name than the person meant.

**Two more, found in the same pass:**
- The probe budget was consumed by junk spans ("but tell", "nothing but tell") before
  reaching the real name. Spans containing a capitalised word are tried first; wholly
  lowercase input is unaffected.
- **`_SELF_MINE_RE` treated "my manager" as a claim on the caller's own data**, so
  "my manager is off sick, is X at risk?" opened with the CALLER's risk and pace. "my"
  followed by a person-noun no longer counts as self-reference.

**The full-name requirement is now data-driven.** The first attempt returned early
whenever ≥2 significant tokens were typed, which broke five comparison tests — "compare"
counted as a name word. It now asks the directory which typed words are actually
somebody's name (one bounded probe each, identity only): "compare" belongs to nobody,
"Lucia" belongs to someone. A stop-list would have to guess, and guessing wrong breaks it
in both directions.

**Also worth recording:** a full-suite run killed mid-flight left the reused test database
corrupt, and the next run reported 176 failures / 679 errors that had nothing to do with
the code. `pytest --create-db` restored it. Don't debug a mass failure without ruling
that out first.

4 regression tests added (31 in `test_person_resolution.py`).
Full suite **1628 passed**; harness **232/232 at BOTH 5,000 and 25,000**; live **15/15**
on all three tenants.

**RESUME HERE → nothing outstanding.** REPORT.md §7 leaves items 3 and 5, both deliberate
design choices. Further work is optional polish.

---

## Follow-up 6 — a typo stops being a coin toss, and the proof extends to 50,000

### The measurement that motivated it
Similarity was a whole-string `difflib` ratio, and a shared forename is half of a
two-word name — so it dominated the score and drowned out the half where the user
actually made the mistake. Measured over typo pairs and each one's nearest wrong
colleague, difflib put the **worst true match at 0.900 and the best impostor at 0.905**.
The distributions overlap, so a one-letter slip landed inside `_TIEBREAK_MARGIN` and came
back as "which of these did you mean?" — offering eight people to someone who had typed
the right name with two letters swapped.

### What changed
- **`_edit_ratio`** — Damerau (optimal string alignment) rather than difflib's shared
  subsequence, which on short words is generous to the point of uselessness ("lauretn"
  scores 0.77 against "larsen", an entirely different surname, purely for sharing
  l/a/r/e/n in order). Adjacent letters SWAPPED cost one mistake, not two: a
  transposition is the most common way a name gets mistyped.
- **`_similarity` pairs word with word**, one-to-one and scored both ways, so a name with
  a part MISSING is penalised rather than rewarded — otherwise "Lucas Cardoso" beats
  "Lucas Cardoso-Ismail" on a query naming all three. Same sets now separate **0.817
  against 0.833**.
- **`_ranked`** shortlists with the blunt ratio and decides with the careful one, because
  a shared forename ties a thousand people and reordering names never in contention
  costs milliseconds for nothing.
- **`suggest_candidates` ranks within each band by closeness**, not alphabetically. Asked
  about "Nora Lauretn" the eight names offered back were Nora Abbott through Nora
  Abbott-Hartmann; the Nora Laurent she meant was not among them. A list that cannot
  contain the answer is worse than no list.
- **`_MAX_INTERSECT = 60`** — the intersection tier ranked an arbitrary
  `_MAX_CANDIDATES + 1` rows, so where a common first+last pair has relatives (sixteen
  people are "Amara Haddad-…") the person meant fell outside the window and a
  transposition came back ambiguous.
- **`AMBIGUOUS` is a named sentinel** so a harness line reads `AMBIGUOUS` rather than
  `<object object at 0xffff8f5a0870>`.

### The calibration I nearly missed
The rewrite broke `test_typo_in_a_name_still_resolves_by_fuzzy`, and the failure was
right: `_FUZZY_MIN = 0.82` was calibrated for difflib, and the same names simply score
lower now. "akil menonn" → Akhil Menon (a mistake in *each* word) scores 0.817 and was
rejected outright — the assistant answered "no such person" to an obvious typo. The floor
is now **0.78**, which on this metric reads as "about one mistyped character per word".
It is not a loosening: what stops a wrong name being ACTED on is `_FUZZY_MARGIN`, not the
floor, and the floor only decides whether the best guess is worth considering at all.

### Two properties measured rather than asserted
- **The cap has headroom.** Over 300 random people in the 50,000-person tenant the
  largest full-name intersection is **17 rows** against a cap of 60.
- **The blunt shortlist never drops the answer.** In the worst cohort — 1,003 people
  sharing the forename "Priya" — a transposed-letter surname typo ranks the true person
  **first** in 40/40 trials. It orders; it does not discard.

### A false reading worth recording, twice over
Running the harness *concurrently with the full test suite* showed resolution latency
rising 0.5 → 1.3 → 1.6 ms across 5k/25k/50k, and I was about to report the flat-cost
claim as broken. Measured without contention it is **0.5 ms median at all three sizes**.
Then the live transcript capture came back 6/15 — HTTP 429 on the `ai` bucket, because
the passing run and the capture fell in the same per-minute window. Both readings look
exactly like logic failures. Measure the machine you think you are measuring.

### Tests
2 added to `test_person_resolution.py` (33 total): the Nora Laurent/Larsen near-tie that
motivated the metric and was never covered, and the two-typo name that pins the floor to
the new scale.

Full suite **1635 passed**, 7 deselected. Harness **239/239 at 5,000, 25,000 AND 50,000**
— 1 query per lookup, 0.5 ms median, no unbounded SELECT at any size, typo tolerance
17/17 with none skipped. Live HTTP **15/15 on all four tenants** with the real LLM.

**RESUME HERE → still nothing substantive outstanding.** REPORT.md §7 items 3 and 5
remain deliberate design choices. The 50,000-person tenant is now a standing artefact
(`SCALE_HARNESS_RESULTS_50000.txt`, `LIVE_TRANSCRIPT_50000.txt`) if a future change needs
re-proving at that size.

---

## Follow-up 7 — the other two actions, end to end, and the bug that fell out

### The gap
AGENT_MASTER's definition of done names four actions. Recognition and the check-in were
proven all the way to a created row; **`draft_review` and `initiate_360` were only ever
proven at the ROUTING level** — that "start a 360 for X" is *recognised* as a 360. That
is the easy half. It says nothing about whether the right person ends up on it, whether
the human gate holds, or whether the scope check survives at 50,000 people.

### What was added to the harness
- **360, end to end**: prepared for a team member → the confirm step carries that
  person's `subject_id` → **proposing creates nothing** → approving creates a DRAFT cycle
  with `opened_by` set server-side. Asserting only the last of those would pass equally
  well if the plan had already written the row, which is the failure worth catching.
- **The scope half**: unlike recognition, a 360 is DATA-scoped — you may recognise
  anyone in the company but not open a cycle on someone you cannot see. A person outside
  the manager's whole reporting **subtree** (not merely not a direct report — a
  report-of-a-report is in scope, and using one would assert the opposite of what is
  meant) must never produce an armed confirm step.
- **Review draft, end to end**: every draft is created *before* the first question, so
  each turn must pick one person's review out of several. Building them as it went made
  the first iteration a one-candidate walkover that would pass even if the name were
  ignored entirely.

**Mutation-tested rather than trusted.** A new check that passes first time has not been
shown to work. Sabotaged to ask about the wrong person, "the 360 names the right subject"
went 6/6 → **0/6** and "the draft picks the named person's review" → **1/3** (the one pass
being the case where the wrong person *is* the right person). Then reverted.

### The bug it found: Agent-1 had never once succeeded
Extending coverage to the execute seam meant real Agent-1 jobs were queued — and every
one **FAILED with PROVIDER_ERROR**. Not a new break: the demo tenant showed 2/2 failed
from long before tonight. A user could ask for a review draft, approve it, and get
nothing, with the review stranded in `AI_DRAFTING`.

The chain, which is worth reading in order:
1. `config/settings/base.py` sets `LLM_MAX_TOKENS = 4096` **with a comment explaining
   that 900 truncates a Gemini "thinking" model**, which spends output tokens reasoning
   before it emits the JSON. So this was known and fixed.
2. `docker-compose.yml`, `docker-compose.prod.yml` and `.env` all pinned **900**. The fix
   was overridden by the deployment — in prod as well as dev.
3. The provider reported the result as **"Gemini returned non-JSON content."** It reads
   `finish_reason` already, but only to lower confidence, and the JSON parse throws
   first. So the one message anybody saw pointed at the model and the prompt, when the
   cause was our own ceiling cutting a valid response mid-string.

Fixed all three: compose defaults raised to match settings, and both providers (the
OpenAI sibling had the identical defect — two copies of one behaviour, the drift this log
has already recorded twice) now say "cut off at the N-token ceiling … raise
LLM_MAX_TOKENS" when `finish_reason == "length"`.

**Verified for real, not just in a mock.** One Agent-1 job against the 5,000-person
tenant with the live Gemini provider: `JOB SUCCEEDED`, review moved to
**`PENDING_HUMAN_REVIEW`** (the HITL gate intact — not auto-applied), 957 characters of
grounded prose citing that person's actual 74% attainment and AT_RISK band.

### The guard that matters more than the fix
A settings fix a deployment silently overrides is not a fix, and nothing compared the
two. `test_compose_never_pins_the_token_budget_below_the_settings_default` parses both
compose files and fails if either pins below `settings.LLM_MAX_TOKENS`. Verified by
re-pinning 900 and watching it fail (`assert 900 >= 4096`), then reverting.

### Tests
3 added: the truncation diagnosis in each provider, and the compose-pin guard.

Harness **276/276 at 5,000, 25,000 and 50,000**. Full suite **1638 passed**.

**RESUME HERE → all four actions in the definition of done are now proven end to end,
through the HITL gate, at three company sizes.** The harness asserts the job is *queued*
by the approval; that the worker then succeeds was verified by hand against the live
provider (above) rather than automated, because the harness deliberately runs on the
deterministic fake and must not depend on a model's mood.

---

## Follow-up 8 — the other two agent jobs the assistant can start

### Why look
Follow-up 7 found Agent-1 had never succeeded. The assistant enqueues **three** kinds of
agent job — `agent1` (review), `career_roadmap`, `agent4` (succession) — and only the
first had any run history at all. An action that tells the user "requested" and then
silently never delivers is the same defect whichever agent it is.

Exercised both against the live provider:
- **`agent4` (succession) → SUCCEEDED.** The token-ceiling fix generalised, as expected.
- **`career_roadmap` → FAILED `EMPLOYEE_NOT_FOUND`** — a different bug entirely.

### The career agent could never have worked
The seam is `generate_roadmap(tenant_id, employee_id, target_ref, …)`. The assistant's
`_execute_career_enrich` enqueued the **roadmap's own id** as the job target and set no
params at all — so the worker looked up a `User` by a roadmap's id (misses every time)
and, even given the right employee, would then have skipped with "target not found".

**I fixed this in the wrong place first, and the suite caught it.** I changed the
dispatcher to translate a roadmap id into an employee — which broke
`test_enrich_enqueues_job_degraded_and_roadmap_unchanged`, and that failure was the
useful bit: there is a **second caller**, `RoadmapEnrichView`, which has been sending the
right shape all along (`target_id=roadmap.employee_id`, `params={"target_ref": …}`). So
the contract was never ambiguous, and the dispatcher was never wrong — the assistant
simply did not follow the contract its own comment claims to mirror. Reverted, and fixed
at the enqueue site instead. One contract, one place.

Live: **SUCCEEDED**, producing a new `source=AI`, `status=DRAFT` roadmap with 3 tiers and
`advisory=True` — the deterministic baseline untouched, adoption still a human step.

**Why nothing caught it.** The seam's own tests call `generate_roadmap` directly with the
correct arguments. The two `career_enrich` action tests stopped at "a job was enqueued" —
and, worse, **asserted the broken shape** (`target_id == rm.id`). So the seam was covered,
the enqueue was covered, and the join between them was covered by nothing. That is the
shape of this whole evening twice over: each piece tested in isolation, the join assumed.

The other four seams (`agent1`, `agent3`, `agent4`, `jd_generator`) all take their own
artifact's id, which is exactly what the dispatcher passes — checked, not assumed.

### Tests
The two tests that asserted the broken shape now assert the real contract, and a new one
runs the assistant's own job through the real dispatcher: right employee, DRAFT status,
`advisory=True`, deterministic baseline untouched. That last one is the check whose
absence let a total failure sit there — every existing test stopped at "enqueued".

Full suite **1639 passed**.

**RESUME HERE → every agent job the assistant can start now completes.** Remaining
REPORT.md §7 items 3 and 5 are still deliberate design choices.
