# QUESTIONS.md — open questions for Hari (never blocking)

> Each entry: the question · why it matters · the default taken to continue ·
> what choosing differently would change. Defaults are recorded in DECISIONS.md.

---

### Q1 (BUILD_1/1.4) — Two list endpoints left unpaginated by design; chart lazy-load deferred

**Question.** Three large-tenant items were scoped OUT of BUILD_1 because the
clean fix is a UI/UX change, not an ORM one — confirm these belong in BUILD_5:
1. `GET /api/admin/users` (admin user table) — paginate + add server-side search
   + page controls (UI work).
2. `GET /api/cycles/<id>/scores` (team scores) — add a scoped single-employee
   score lookup so `ReviewEvidence` doesn't fetch the whole cohort.
3. Org chart expand-on-demand lazy-loading for the HRBP/Admin full-tenant view.

**Why it matters.** For a 2k-employee tenant these three still ship more rows
than strictly needed to the broadest-scope users. None is a correctness or
isolation risk today (the tree is scope-bounded; the dashboard no longer pulls
the user list).

**Default taken (to continue).** Left as-is for BUILD_1; the headline anti-pattern
(dashboard downloading the user list) was fixed server-side. Recorded as BUILD_5
(WEB_UX) candidates. Choosing differently (do them now) would mean UI changes
beyond an ORM build's remit. See DECISIONS.md D3.
