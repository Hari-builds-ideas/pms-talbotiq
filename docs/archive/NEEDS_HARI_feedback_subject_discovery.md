# NEEDS_HARI — an employee subject can't DISCOVER their own 360 cycle id

**Status: RESOLVED (Finish-web Phase A1).** A subject-scoped discovery endpoint
now exists and is wired into "My 360"; the one open *product* call below has a
safe default chosen.

## The gap (original)
The subject's released-summary endpoint is `GET /api/feedback/cycles/<id>/summary`
(capability `VIEW_OWN_FEEDBACK_SUMMARY`) — it requires the **cycle id**. But the
only way to *list* feedback cycles, `GET /api/feedback/cycles`, was gated to
`MANAGE_FEEDBACK_CYCLE` (**Manager+**). An **Employee** subject therefore had no
API path to discover the id of the 360 cycle that is about *them*.

## What was built (A1)
- **`GET /api/feedback/my-cycles`** — returns ONLY the cycles whose `subject` is
  the caller (any role), tenant-scoped, own-subject-only. Each row carries the
  public cycle shape **plus** `summary_id`, `summary_status`, `summary_released`
  — just enough to decide whether to fetch the released summary. It egresses **no
  giver identities** and **no summary content**; the content stays gated behind
  `/cycles/<id>/summary` (RELEASED-only). Reuses the existing
  `VIEW_OWN_FEEDBACK_SUMMARY` capability (held by everyone, OWN scope) — the same
  capability that already governs the subject's summary read, so no new matrix
  entry was needed. Backend tests added: subject sees only their own; a different
  employee never sees another's; cross-tenant rows never appear; released vs
  pending discovery + the still-gated content.
- **Frontend "My 360"** now calls `my-cycles` (no Manager+ list, no pasted id):
  it auto-discovers the caller's cycles and shows the released summary, the
  "being reviewed" state for a not-yet-released summary, and "no summary yet"
  otherwise.
- **Verified live over HTTP:** an EMPLOYEE subject (`reza@acme.test`) calls
  `/my-cycles` → 200, discovers her own cycle (`summary_released: true`), follows
  the id to `/cycles/<id>/summary` → 200 RELEASED with real sections; a MANAGER
  subject (`ada@acme.test`) sees only her own cycle (no overlap with reza's).

## The one remaining product decision (safe default chosen)
The **Admin Hub is a Manager+ desktop/management tool** — every route is gated
`min="MANAGER"` by design, and the agreed surface split is that **employee
self-service lives in the separate mobile-web build** (see MOBILE_BUILD_PLAN.md).
So this run did **not** add an employee entry point to the Admin Hub (that would
be a one-item hub for employees and a scope expansion). The `my-cycles` endpoint
is the exact read the **mobile** "My 360 summary" screen will call — it is listed
in the mobile reuse map. **If Hari wants employees to reach their 360 summary in
the *web* app before mobile ships,** lower the `/feedback` route gate to allow
all roles and render only the "For me" + "My 360" tabs for employees (the page is
already role-aware for the Manager+/HRBP tabs). Until then the endpoint is built,
tested, and consumed by the Admin Hub's own (Manager+) subjects.
