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

---

### Q2 (WEB_COE/W1) — Should a tenant's SAML IdP be allowed to drive (sync) the user's role?

**Question.** When a tenant configures a SAML `role_map`, the SP maps the IdP's
role/group attribute to one of our Roles and **JIT-syncs it onto the user's DB role**
(RBAC enforces the DB role, so this is what makes the mapping actually take effect),
writing an `identity.saml.role_synced` audit row. Do you want IdP-driven role sync at
all, and if so should the synced role be **capped so it can never exceed** the
admin-provisioned role (no IdP-driven privilege escalation)?

**Why it matters.** It's the federation trade-off: IdP-authoritative roles are standard
enterprise SSO, but they let a (tenant-administered) IdP attribute elevate someone to
Admin. RBAC enforcement itself is unchanged either way; this is only about where the
*role value* originates.

**Default taken (to continue).** Conservative + opt-in: with an **empty `role_map`
(the default) the IdP drives NO roles** — the Admin Hub stays authoritative, identical
to the OIDC path. Sync only happens when a tenant explicitly fills `role_map`, and an
absent/unknown attribute never escalates. See DECISIONS.md D25; proven in
`apps/identity/tests/test_saml.py`.

**Choosing differently** (e.g. add a rank-cap so a mapped role can't exceed the
provisioned one, or disable DB sync entirely and keep role mapping advisory) is a small,
localised change in `apps/identity/saml/service.py::_resolve_and_sync_role`.

**✅ RESOLVED (2026-06-22).** Hari: keep sync opt-in (empty role_map = no sync) **and add
the rank-cap** so a synced role can NEVER exceed the admin-provisioned role — no
IdP-driven privilege escalation. Implemented + tested; see DECISIONS.md D27.
