# HARI_ATTENTION_NEEDED — agent action `request_feedback` (File F)

**Status:** NOT shipped this run — deliberately. It cannot be cleanly wired to an
existing audited endpoint **for the role the spec asks** (Employee+) without
widening permissions, which iron rule #1 forbids. Decision needed from you.

## What the spec asked (OVERNIGHT_F, action 3)
> `request_feedback` (Employee+): requests feedback from a scoped person (their
> manager or a peer on their team). Reuses existing feedback-request endpoint.

## Why it doesn't wire as an Employee+ action
The only "feedback request" write in the system is a **cycle invitation**:
`POST /api/feedback/cycles/<id>/requests` → `send_feedback_request(cycle, giver,
relationship, actor)`. That view (`CycleRequestListCreateView`) requires
**`MANAGE_FEEDBACK_CYCLE` (Manager+)**, and semantically it *invites a giver to give
feedback about the cycle's subject* — it is not "an employee asks someone to give
them feedback."

- An employee has `GIVE_FEEDBACK` (they can GIVE feedback and see their own
  invitations) but **no capability to REQUEST feedback from others**.
- To "request feedback from my manager," the employee would need a cycle where they
  are the subject — and only a Manager+ can create cycles / add requests.

So there is **no Employee-scoped audited write path** to reuse. Shipping it as
Employee+ would require either a new endpoint + a new capability, or reusing the
Manager+ cycle-invite path (which contradicts the stated role and overlaps the
existing `initiate_360` reviewer-invite step). Both are out of scope for
"reuse the existing endpoint," so per File F's DoD I stopped this action and shipped
the other five.

## Options for you (pick one)
1. **Add a real "request feedback" feature** — a new `FeedbackRequestToSelf` (or a
   lightweight "ask for feedback" model) + endpoint + capability (`REQUEST_FEEDBACK`,
   Employee+, scope = own manager / same-team peers). Then the agent action wires to
   *that* audited endpoint, exactly like the others. (Recommended if the CEO wants
   employee-initiated feedback in the demo.)
2. **Reinterpret as Manager+**: `request_feedback` = a manager invites a named,
   in-scope giver (a peer/manager) into an existing open cycle via
   `send_feedback_request`. Real, cleanly-wired, audited — but it's Manager+, not
   Employee+, and largely duplicates the reviewer-invite half of `initiate_360`.
3. **Drop it** — `initiate_360` already covers the cycle+invite flow for managers.

## Not a blocker
The other five File F actions shipped green on `main`. This is a product/RBAC
decision, not a bug. No permission was widened and nothing was faked to force it.
