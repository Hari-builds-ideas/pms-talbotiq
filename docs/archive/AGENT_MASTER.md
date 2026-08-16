# AGENT_MASTER.md — make the AI Assistant genuinely work, at any company size

Branch: **hari/agent-intelligence-v2** (checkout; never touch hari/agent-ui-v2 or main). Keep backend +
frontend tests green, commit per working unit, log every unit to `docs/AGENT_REBUILD/PROGRESS.md` with a
"resume here" note. Resume from that file if present.

## The goal, stated plainly
The assistant must reliably do the four things it exists to do, for **any person in the company** and at
**any headcount (211 today, 5,000 tomorrow)** — with zero hardcoded names and zero team-only blind spots
for the things that should be company-wide:

1. **Find any person** by name, from the database, across the whole tenant.
2. **Retrieve data** about them (their goals, KPIs, reviews, pace) — within the caller's permission scope.
3. **Take actions** (recognition, check-in, feedback request, review draft) — reliably, with the human
   approval gate, and with follow-up questions that actually work.
4. **Reason & compare** over real data — not templates, not canned lines.

This is NOT a retrieval-system (RAG/vector) problem. The data is in SQL; the fix is correct database
querying + a correct conversation state-machine + correct intent routing. Do not build a vector store.

## What is broken today (all reproduced live — fix every one)
- **Pending-question slot is stuck in a loop.** After the assistant asks a follow-up ("how are you feeling
  this week 1–5?"), NO reply ever fills it — "5", "mood 4", or a new command all just re-ask the same
  question forever. The single worst bug.
- **"Do the same for X" loses the action.** After a recognition, "do the same for Ingrid" starts a
  check-in instead of a recognition.
- **Intent routing is wrong.** "make a recognition for X" can land in a check-in.
- **No escape from a stuck task.** A new command mid-pending is ignored instead of either answering or
  abandoning.
- **Person lookup is team-scoped for actions that should be company-wide.** A manager can only recognise
  their own reports; anyone outside their team is "not found." Breaks completely at real company size.
- **Answers are templated**, not specific to what was asked.

## Execute these build files IN ORDER
1. `A_PERSON_RESOLUTION.md` — one company-wide, DB-backed, scalable person resolver; directory lookup
   separated from data-access; exact-match wins; scales to thousands; no hardcoding.
2. `B_CONVERSATION_STATE.md` — fix the pending-slot loop, "do the same", intent routing, and escape.
3. `C_DATA_AND_REASONING.md` — real data retrieval + reasoned (non-template) answers, scope-safe.
4. `D_SCALE_AND_HARNESS.md` — prove it at 5,000 people with a generated large tenant + an automated
   behavioural harness that exercises every action for many random people, including out-of-team.
5. `E_REPORT.md` — honest report + how to test, live proof.

## Iron rules
- No hardcoded person names or seed-specific special cases anywhere in the agent path. Grep for them and
  remove any that exist.
- Directory resolution (name → person) is COMPANY-WIDE. Data access (goals/reviews/scores) stays
  permission-scoped and is re-checked on every turn. Finding a person never grants access to their data.
- Every action keeps the human-approval (HITL) gate. Read-only stays read-only; actions still require the
  user's confirm step.
- Never weaken RBAC/tenant-isolation/audit. Never fabricate — missing data is stated honestly.
- Everything backed by a test. Commit per unit. Resume-safe.

## Definition of done (the whole run)
On a generated tenant of 5,000 people, as different roles, the assistant: finds arbitrary people by name
(exact match instantly, fuzzy on typo, disambiguates only real duplicates); completes recognition,
check-in, feedback-request and review-draft — including the follow-up questions actually being answered;
handles "do the same for <different person>"; reasons over real data and compares two people; refuses
out-of-scope DATA while still allowing company-wide directory actions; and never uses a hardcoded name.
All tests + the large-scale harness green. End with `docs/AGENT_REBUILD/REPORT.md`.
