# RW_BUILD_1_REPORT — Navigation re-cut + RBAC visibility (per role)

The first re-weighting build: **UI/permissions only, no new backend.** Each role now sees only what it
can use; the enterprise screens are demoted to an HR/Admin "Advanced" area; the employee "dashboard →
no access" dead end is gone. Server-side RBAC is unchanged and re-proven (defense in depth).

All four phases complete, committed, and pushed; backend suite grew and stayed green; frontend
build/tsc/lint/tests clean.

## Phases

| Phase | What | Verify | Commit |
|---|---|---|---|
| 1.1 | `docs/NAV_RBAC_MAP.md` — every route → primary capability → section → who-sees, mismatches flagged | [doc] | `38e4354` |
| 1.2 + 1.3 | Role-gated sidebar via `navForRole(role)`; dropped over-restrictive `RoleGate` on /goals,/reviews,/feedback; intra-screen action gates; **demoted** succession/org/JD/audit to the HRBP+ Advanced group (incl. removing the manager cockpit's succession entry point) | [test]+[build] | `9a6e546` |
| 1.4 | Defense-in-depth test over the **real** endpoints: the demoted/gated surface still 403/404s for lower roles; the newly-exposed employee screens 200 (own scope) | [test] | _this commit_ |

## Per-role navigation as shipped

Driven by `navForRole(role)` in `frontend/src/app/nav.ts` — a pure function of role (the sidebar renders
it; `nav.test.ts` asserts it). `minRole` == backend capability because every capability is granted to an
upward-closed role slice (so the sidebar matches the server exactly).

- **Employee** — **Workspace** only: Home · Goals & KPIs · 360 Feedback · Reviews · Career. Nothing else.
  (Check-ins / Recognition are in the plan's employee set but have no routes yet — RW_BUILD_2/3 add them;
  omitted to avoid dead links.)
- **Manager** — Workspace **+ Team**: Approvals · Team Analytics.
- **HRBP** — the above **+ Advanced** (the demoted enterprise/HR tools): Succession · Org Chart ·
  JD Library · Audit Console.
- **Admin** — the above **+ Administration**: Users & Roles · Tenant Config · Entitlements · Integrations.

## What moved to Advanced (demoted off the everyday surface)

Succession (incl. nine-box), Org Chart, JD Library, Audit Console — now in the HRBP+ "Advanced" group,
absent for employee/manager. Calibration lives inside Analytics and nine-box inside Succession (no
separate routes), so they ride their parent's placement. **The routes and their server-side gates are
unchanged** — nothing was deleted; a manager who deep-links to `/succession` still gets their tier
(backend `VIEW_SUCCESSION` is Manager+). The manager cockpit's succession stat + risk tile were removed
so no manager *entry point* advertises a demoted screen (see Q6 — trivially reversible).

## The core fix (the loud complaint)

Employees got a dashboard whose tiles linked to `/goals`, `/reviews`, `/feedback`, but the sidebar hid
those items **and** the router gated them at `MANAGER` → the NotPermitted screen. The backend already
grants `VIEW_OWN_GOALS` / `VIEW_OWN_REVIEW` / `GIVE_FEEDBACK` to all roles (own scope). RW_BUILD_1 shows
those items in the employee sidebar and removes the over-strict frontend gate — **not** an RBAC weakening
(the server still scopes to own data; the gate was stricter than the server). Manager-only actions inside
those screens (Goals New goal/Recompute, Feedback Cycles tab, Reviews New review) are gated to Manager+ so
an employee never sees a button the server would deny.

## Verification

- **Frontend [test]+[build]:** `nav.test.ts` (+5) asserts the per-role nav set — employee = the 5-item
  Workspace and **none** of the management items; manager/HRBP/admin are strict supersets. Full frontend
  suite **88 passing**; `tsc --noEmit`, `eslint .`, `vite build` all clean.
- **Backend [test]:** `apps/rbac/tests/test_recut_surface_gating.py` (+9) over the real urlconf —
  employee→succession **404**, employee→department-analytics **403**, manager→audit **403**,
  manager→calibration **403**, HRBP→admin-users **403**, HRBP→integrations **403**; and employee→own
  goals/reviews/feedback-requests **200** (the newly-exposed items are real, not dead links). Full
  backend suite **1222 passing, 2 deselected** (was 1213; +9).
- **Live [your device]:** see below — the rendered sidebar per role can only be confirmed by you.

## Your device check (before RW_BUILD_2)

Log in as each role at http://localhost:8080 (hard-refresh / incognito to drop any cached bundle) and
confirm:
- **Employee** (`reza@acme.test`): sidebar shows exactly **Home · Goals · Feedback · Reviews · Career**,
  nothing else; clicking each loads (no "You don't have access"); the dashboard tiles all lead somewhere.
- **Manager** (`ada@acme.test`): the above **+ Team** (Approvals, Team Analytics); **no** Succession /
  Org / JD / Audit / Admin in the sidebar.
- **HRBP** (`priya@acme.test`): **+ Advanced** (Succession, Org, JD, Audit); **no** Administration.
- **Admin** (`admin@acme.test`): **+ Administration** (Users, Tenant Config, Entitlements, Integrations).
- No dead/denied links anywhere in any role's sidebar.

## Decisions & open questions logged

- **D31** — nav visibility = the screen's primary-read capability (`minRole` ≡ capability); the
  employee gate removal is alignment with the backend, not a weakening.
- **Q3** — `PRODUCT_REWEIGHTING_PLAN.md` is referenced but absent; executed from the RW_BUILD_1 spec +
  `PASTE_THIS_RW.md`, cross-checked against the RBAC matrix.
- **Q4** — the plan's "HR set" listed Settings/Integrations, but the backend gates those Admin-only; kept
  Admin-only to avoid dead links (widening to HRBP would be a backend RBAC change, out of scope).
- **Q5** — intra-screen action gating: did the obvious ones on newly-exposed screens; an app-wide sweep
  is a finish-the-web concern.
- **Q6** — removed the manager cockpit's succession entry point per the explicit demote; backend access
  unchanged; trivially reversible if managers should keep coverage visibility.

## Next

RW_BUILD_2 (Recognition) — after your device check confirms the surfaces.
