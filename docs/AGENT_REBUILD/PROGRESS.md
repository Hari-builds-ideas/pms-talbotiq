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
