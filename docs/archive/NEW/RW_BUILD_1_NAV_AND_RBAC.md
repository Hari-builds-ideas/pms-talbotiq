# RW_BUILD_1 — Navigation re-cut + RBAC visibility (per role)

> Read BUILD_0_READ_FIRST.md and PRODUCT_REWEIGHTING_PLAN.md (Decisions 3 & 4) IN FULL first; all BUILD_0
> rules apply (real wiring, tests grow + stay green, never weaken RBAC/scope/tenant isolation/HITL,
> frontend build/tsc/lint clean, commit+push per phase, .env never staged, update PROGRESS/DECISIONS/
> QUESTIONS). This is the highest-value, lowest-risk re-weighting build: it fixes the loudest complaint
> (roles see things they can't use; employees see a dashboard then get "no access") with NO new backend.

The goal: a role sees ONLY what it can use. Items a role cannot access must NOT appear in its sidebar or
dashboard at all — never shown-then-denied. Keep server-side route protection (defense in depth); the UI
must simply stop advertising what it will deny.

## Phase 1.1 — Audit the current nav/route surface vs role
- Enumerate every sidebar nav item, every dashboard tile/card, and every route, and record which role(s)
  can actually use each (cross-check the backend RBAC capability the route requires). Write the map to
  `docs/NAV_RBAC_MAP.md`: item → required capability → roles that should SEE it.
- Flag every current mismatch (shown to a role that gets 403/404 on click — e.g. the employee Career link
  that rejected, succession visible to non-HRBP, admin items to managers).

**Verify:** the map is complete and matches the backend capabilities. Commit `RW_BUILD_1 1.1 — nav/RBAC
audit map`.

## Phase 1.2 — Gate sidebar + dashboard VISIBILITY by role
Implement the per-role navigation from PRODUCT_REWEIGHTING_PLAN.md Decision 4:
- **Employee:** Home · Goals · Check-ins · Feedback · Recognition · Reviews · Career. NOTHING else in the
  sidebar (no succession, nine-box, analytics, admin, integrations, audit, tenant config). (Check-ins /
  Recognition routes may not exist yet — if so, omit them now; RW_BUILD_2/3 add them. Do NOT create dead
  links.)
- **Manager:** Team · Check-ins · 1-on-1 · Goals · Feedback · Recognition · Reviews · Team Analytics.
- **HR/HRBP:** People · Review Cycles · Templates · Reports/Analytics · Recognition · Settings · an
  "Advanced" group (succession, calibration, nine-box, org chart, JD library, audit, integrations, tenant
  config).
- **Admin:** the HR set + system administration.
- Drive visibility from the existing role/capability helpers (the same source the backend uses), so the
  sidebar is a function of role — not a hardcoded list. An item with no capability for the current role is
  not rendered.
- Dashboard tiles follow the same rule: a tile a role can't act on isn't shown to that role.

**Verify [test]+[live]:** add frontend tests asserting the rendered nav set per role (employee sees the
minimal set and NONE of the management items; manager/HRBP/admin see theirs). Live: log in as each of the
4 roles and confirm the sidebar shows only its set and has zero dead/denied links. Commit `RW_BUILD_1 1.2
— role-gated sidebar + dashboard visibility`.

## Phase 1.3 — Demote the enterprise screens into "Advanced / HR Tools"
Per Decision 3: succession, nine-box, calibration, JD library, org chart, audit, integrations, tenant
config move OFF primary nav into an Advanced/HR area visible to HR/Admin only. The routes still exist and
work (nothing deleted) — they're just not on the everyday surface, and not visible to employee/manager.
- Confirm no employee/manager entry point references them; confirm HR/Admin can still reach them via the
  Advanced area.

**Verify [test]+[live]:** the enterprise screens are reachable by HR/Admin via Advanced, absent for
employee/manager; routes still load for the authorized roles. Commit `RW_BUILD_1 1.3 — demote enterprise
screens to Advanced`.

## Phase 1.4 — Server-side defense-in-depth check
Confirm (don't weaken) that every route hidden in the UI is STILL protected server-side — hiding a link is
UX, not security. Add/confirm a test that a role calling a capability it lacks gets the correct 403/404
(this should already hold from the existing RBAC; just prove it for the re-cut surface).

**Verify [test]:** RBAC denial tests green for the re-cut surface; full backend suite + frontend build/
tsc/lint clean. Commit `RW_BUILD_1 1.4 — confirm server-side gating (defense in depth)`.

---
## End of RW_BUILD_1
Write `RW_BUILD_1_REPORT.md`: the nav/RBAC map, the per-role nav as shipped, what moved to Advanced, the
visibility tests per role, and live confirmation that each role sees only its surface with no dead links.
Then proceed to RW_BUILD_2 (Recognition).
