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
