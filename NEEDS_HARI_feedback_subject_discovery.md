# NEEDS_HARI — an employee subject can't DISCOVER their own 360 cycle id

**Status:** non-blocking. The 360 loop is fully built and verified end-to-end; this
is a UI-reachability gap for one role, with a safe default chosen.

## The gap
The subject's released-summary endpoint is `GET /api/feedback/cycles/<id>/summary`
(capability `VIEW_OWN_FEEDBACK_SUMMARY`) — it requires the **cycle id**. But the only
way to *list* feedback cycles, `GET /api/feedback/cycles`, is gated to
`MANAGE_FEEDBACK_CYCLE` (**Manager+**). An **Employee** subject therefore has no API
path to discover the id of the 360 cycle that is about *them*, so the Admin-Hub UI
can't fetch/show an employee's own released summary by itself.

(The endpoint itself works correctly for the subject role — verified live: an employee
subject gets **403 `SUMMARY_NOT_RELEASED`** before release and **200 RELEASED** after,
with the anonymised, threshold-gated content. The gap is *discovery*, not access.)

## Safe default chosen (and shipped)
- The **My 360** view on `/feedback` shows the subject's released summary for any role
  that can list cycles (Manager / HRBP / Admin subjects) — it filters the cycle list to
  `subject == me` and reads `/cycles/<id>/summary`, handling 403/404 states.
- The **employee cockpit** surfaces the giver side fully (give feedback from the
  "Feedback requests" tile, which uses `/requests/mine`). It does **not** show an
  employee's own released 360 summary, because the id isn't discoverable for that role.
- This is consistent with the product's surface split (employee self-service is the
  separate mobile-web build), so no employee-facing summary view is missing from the
  Admin Hub's intended scope.

## What Hari should decide
Add a small, subject-scoped read so an employee can find their own cycles/summaries —
e.g. `GET /api/feedback/cycles/mine` (cycles where `subject == request.user`, any role)
or `GET /api/feedback/summaries/mine` (the caller's own RELEASED summaries). Either is a
thin, tenant-scoped, read-only view; the mobile-web self-service surface will need it
too. Until then, the employee subject view is reached via that future endpoint (and the
released summary is already correct behind it).
