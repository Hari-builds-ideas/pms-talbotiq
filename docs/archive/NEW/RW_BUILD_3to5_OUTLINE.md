# RW_BUILD_3 / 4 / 5 — outline (full files written when you reach them)

> These follow RW_BUILD_1 (nav/RBAC) and RW_BUILD_2 (recognition). Each is its own build under the
> BUILD_0 contract (backend-first + tests, real wiring, RBAC/HITL/tenant intact, commit+push per phase,
> verify live). Outlined here so you can start RW_BUILD_1/2 now; ask for the full file when you reach each.

## RW_BUILD_3 — Weekly Check-ins (the core loop piece) — PRODUCT_REWEIGHTING_PLAN Decision 1
Backend: a tenant-scoped `CheckIn` (employee author, period/week, mood 1–5, wins, blockers, learning,
priorities as a small related list each with complete/carry-forward/remove, optional feedback-request)
+ a `ManagerResponse` (comment, react, mark follow-up, add-to-1on1, record-win). Cadence configurable per
tenant; a "due" nudge reusing the existing nudge surface; optional rotating custom questions (15Five
pattern). Goal progress section PULLS the employee's existing goals (reuse the goals engine — show prev%
→ current%; do NOT duplicate goal logic). RBAC: employee writes own; their manager reads/responds; scope-
bound; not anonymous. Feeds review EVIDENCE — do not duplicate review state. AI (HITL): optional
manager-side check-in summary + suggested follow-ups, proposed never auto-saved.
Tests: scope (a manager only sees their reports' check-ins; cross-manager → 404), tenant isolation, the
goal-progress pull is read-only, cadence/nudge. Frontend: the 3–5-min check-in form + the manager review
view + the per-role nav entry. Verify live: an employee submits a check-in; their manager sees + responds;
a non-manager can't see it.

## RW_BUILD_4 — AI assistant: read-only → propose-and-confirm (HITL) — Decision 5
Upgrade the chat assistant so that, in addition to answering (grounded + RBAC-scoped as today), it can
PROPOSE an action and render an inline [Approve]/[Cancel] control in the chat. On Approve, it executes
through the SAME audited, permission-checked endpoints a human uses — never autonomously, never on its own
say-so. Hard rules: the proposal is RBAC/scope-checked at EXECUTION (it can't propose what the user
couldn't do); execution only on explicit human tap; every approved action audited; write intent without
approval still does nothing. Start with 1–2 safe action types (e.g. "approve these N goals",
"nudge the people with no progress in 30 days"), each with a clear confirm card. Tests: a proposed action
is not executed without the tap; an out-of-scope proposal is refused at execution; approved action writes
+ audits exactly once. This is the headline AI upgrade — keep it small and safe first, then extend.

## RW_BUILD_5 — AI quick wins (each reduces admin work) — Decision 6
Incremental, all via the existing LLMGateway (budget→scrub→validate→meter→HITL), all proposing/ drafting
never deciding: (a) AI goal-writer ("improve sales" → a SMART/OKR draft, editable); (b) AI 1-on-1/meeting
summary (notes → summary + action items); (c) review bias/quality flag (recency bias, harsh wording,
missing evidence — assistive, not blocking); (d) stale-goal nudge (no progress in 30 days → suggest a
follow-up); (e) natural-language search ("who hasn't had a 1-on-1 this month / show employees missing
goals" — runs through the caller's scope, returns only what they can see). Build whichever you value most
first; each is a small, self-contained phase with tests + a live check.

## After these: MOBILE
Mobile mirrors the CORRECTED core (the research's employee mobile surface = goals, check-ins, feedback,
recognition, dashboard). Run the mobile builds AFTER the re-weighting so mobile reflects the right product,
not the old one. (MOBILE_BUILD_COE.md already covers 1:1 notes + the engagement hub; revisit its screen
list against the re-weighted nav before running it.)
