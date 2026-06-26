# AI quick win 5 — a 2nd assistant action: approve_reviews (report + UI follow-up spec)

Built overnight, **backend-only + additive** (D36). This extends the RW_BUILD_4 propose-and-confirm
registry (Q9) with a **second** safe action: a manager can ask the assistant to clear the reviews
pending their sign-off, get an **inert proposal**, and only a deliberate Approve tap executes it. The
point of this win was less the new verb and more proving the registry takes a 2nd action **without
loosening the safety contract** — and that a write action can reuse an existing state machine verbatim
rather than re-implementing the rules.

## The safety contract (unchanged from RW_BUILD_4)

- A **proposal is inert** — proposing approves nothing. Only an explicit human Approve calls
  `execute_action`, which is the one and only write path.
- **Execute re-checks capability + object scope on the REAL targets** — it can never do what the user
  couldn't do via the normal endpoint. Out-of-scope / wrong-state targets are **skipped, never forced**.
- Each effect is **audited exactly as the human endpoint audits it** (`review.approved`), exactly once;
  an idempotent re-run skips.
- A user **without the capability** (`APPROVE_REVIEW`) gets **no proposal** and **cannot execute** (403).

## What shipped (backend) — `apps/ai/actions.py` only

- `_pending_reviews_in_scope(user)` — the `PENDING_HUMAN_REVIEW` reviews in the caller's reporting
  subtree (tenant-scoped, bounded by `_MAX_TARGETS = 50`).
- `_propose_approve_reviews(user, _msg)` — requires `APPROVE_REVIEW` up front; returns `None` (no card)
  if the user lacks it or nothing is pending. Otherwise a proposal `{action, summary, preview, params}`.
- `_execute_approve_reviews(user, params)` — for each id, calls **`state_machine.approve(review, user)`** —
  the *same* call `ReviewApproveView` (the human path) makes. That call re-checks `APPROVE_REVIEW` + row
  scope + the HITL state, stamps `human_reviewer`, and writes the `review.approved` audit. Anything out
  of scope / in the wrong state raises → we catch and record it as `skipped`, never forcing the write.
- Registry entry `"approve_reviews"` with a deterministic match (`"approve" in m and "review" in m`).
  **No new view or route** — `POST /api/ai/actions/execute` (RW_BUILD_4) already dispatches by action key,
  so QW5 is a registry-only change. No auth/SSO/shared/deploy/nav/RBAC-matrix change.

### Why reuse the state machine instead of mirroring it (as `approve_goals` does)

`approve_goals` mirrors `GoalApproveView`'s checks inline because goal approval is a single field stamp.
Review approval has a **state machine** (`apps/reviews/state_machine.py`) that owns legality
(`PENDING_HUMAN_REVIEW` only), the RBAC check, the reviewer stamp, and the audit in one place. Calling it
directly means the assistant path and the human path **cannot drift** — there's exactly one
implementation of "approve a review", and the assistant is just another caller of it.

## Verification

- **[test]** `apps/ai/tests/test_actions.py` (+4, 10 total in file):
  - `test_review_proposal_is_inert` — a manager's proposal lists the pending review id; the review stays
    `PENDING_HUMAN_REVIEW` (proposing wrote nothing).
  - `test_execute_approves_reviews_and_is_idempotent` — execute → `APPROVED`, `human_reviewer` = the
    manager, exactly one `review.approved` audit; a re-run approves 0 / skips and adds no second audit.
  - `test_review_out_of_scope_refused_at_execution` — a manager handed a peer's review id (peer reports
    to HRBP) approves 0 / skips; the review is untouched.
  - `test_employee_no_review_proposal_or_execute` — an employee gets `None` from propose and
    `PermissionDenied` from execute; the review is untouched.
- Full backend suite green; frontend untouched + tsc/lint/build green. **No live OpenAI.**

## UI follow-up (for review — NOT built overnight)

The execute endpoint and the chat write-intent path already exist (RW_BUILD_4). To surface this action:

1. No new API call needed — the assistant already POSTs `/ai/chat`; when the message is a write intent it
   returns a proposal card, and the existing **Approve** button POSTs `/ai/actions/execute`. Because the
   registry now contains `approve_reviews`, "approve my team's reviews" already yields a review proposal
   card with **no frontend change**. Worth a manual click-through once you're at a device.
2. Optionally add a one-tap **"Approve pending reviews"** affordance on the Reviews inbox that seeds the
   same proposal (reuses the existing confirm card), so managers don't have to phrase it. Touches an
   existing surface → your review.
3. Extend the registry further the same way (each new action must map to an existing audited,
   permission-checked endpoint or state-machine call, and ship its own inert-proposal + scope-refusal
   tests).
