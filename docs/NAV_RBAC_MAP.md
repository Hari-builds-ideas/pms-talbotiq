# NAV_RBAC_MAP.md — navigation surface vs role (RW_BUILD_1 Phase 1.1)

The audit behind the navigation re-cut: every route/nav item → the **backend capability** its
primary (landing) function requires → the **lowest role** that gets a working primary view → which
section it belongs to after the re-weighting. Because every capability in `apps/rbac/matrix.py` is
granted to an **upward-closed** slice of roles (Employee < Manager < HRBP < Admin), a per-item
`minRole` is exactly equivalent to a backend capability check — so the sidebar can stay a pure
function of role and still match the server.

> Principle: a role sees ONLY what it can use. Visibility is driven by the **primary read** each
> screen lands on (not its write actions, which stay server-gated). Hiding a link is UX, never
> security — the server-side RBAC (Phase 1.4) is unchanged.

## Roles → data scope (from `apps/rbac/scope.py`)
- **Employee** → OWN · **Manager** → TEAM (reporting subtree) · **HRBP/Admin** → TENANT.

## Route → capability → section → who sees it

| Route | Screen | Primary landing cap (`matrix.py`) | Holders | Section (new) | Nav `minRole` | Router gate (current → action) |
|---|---|---|---|---|---|---|
| `/` | Dashboard (role-true cockpit) | — (each cockpit self-scopes) | all | Workspace | EMPLOYEE | none — keep |
| `/goals` | Goals & KPIs | `VIEW_OWN_GOALS` | **all (own)** | Workspace | EMPLOYEE | `MANAGER` → **remove gate** (own-scoped) |
| `/feedback` | 360 Feedback | `GIVE_FEEDBACK` (lands on "For me") | **all (own)** | Workspace | EMPLOYEE | `MANAGER` → **remove gate** (own-scoped) |
| `/reviews` | Reviews | `VIEW_OWN_REVIEW` | **all (own)** | Workspace | EMPLOYEE | `MANAGER` → **remove gate** (own-scoped) |
| `/career` | Career roadmap | `VIEW_CAREER_ROADMAP` | all (own) | Workspace | EMPLOYEE | none — keep (BUG-3 fix) |
| `/approvals` | Approvals inbox | `ACT_ON_APPROVAL_STEP` | Manager+ | Team | MANAGER | `MANAGER` — keep |
| `/analytics` | Team Analytics | `VIEW_DEPARTMENT_ANALYTICS` | Manager+ | Team | MANAGER | `MANAGER` — keep |
| `/succession` | Succession (incl. nine-box) | `VIEW_SUCCESSION` | Manager+ | **Advanced** | **HRBP** | `MANAGER` — keep (manager deep-link still works) |
| `/org` | Org chart | `VIEW_ORG_CHART` | all | **Advanced** | **HRBP** | `MANAGER` — keep |
| `/jd` | JD library | `VIEW_JD_LIBRARY` | all | **Advanced** | **HRBP** | `MANAGER` — keep |
| `/audit` | Audit console | `VIEW_AUDIT_CONSOLE` | HRBP+ | **Advanced** | HRBP | `HRBP` — keep |
| `/admin/users` | Users & roles | `MANAGE_USERS_ROLES` | Admin | Administration | ADMIN | `ADMIN` — keep |
| `/admin/tenant` | Tenant config | `MANAGE_TENANT_CONFIG` | Admin | Administration | ADMIN | `ADMIN` — keep |
| `/admin/billing` | Entitlements | `MANAGE_ENTITLEMENTS` | Admin | Administration | ADMIN | `ADMIN` — keep |
| `/admin/integrations` | Integrations | `MANAGE_INTEGRATIONS` | Admin | Administration | ADMIN | `ADMIN` — keep |

Calibration grid (`VIEW_CALIBRATION_GRID`, HRBP+) and the nine-box live **inside** `/analytics` and
`/succession` respectively — no separate routes, so they ride their parent's placement.

## Per-role sidebar after the re-cut

- **Employee:** Home · Goals · Feedback · Reviews · Career — and nothing else. (Check-ins / Recognition
  are in the plan's employee set but have **no routes yet** — RW_BUILD_2/3 add them; omitted now to
  avoid dead links.)
- **Manager:** the Employee set **+** Team { Approvals · Team Analytics }.
- **HRBP:** the Manager set **+** Advanced { Succession · Org Chart · JD Library · Audit Console }.
- **Admin:** the HRBP set **+** Administration { Users & Roles · Tenant Config · Entitlements · Integrations }.

## Current mismatches this re-cut fixes (shown-then-denied today)

1. **Employees get a dashboard then "no access."** The EmployeeCockpit tiles link to `/goals`,
   `/reviews`, `/feedback`, but the sidebar hides them (nav `minRole: MANAGER`) **and** the router
   `RoleGate min="MANAGER"` rejects them with the NotPermitted screen — even though the backend grants
   `VIEW_OWN_GOALS` / `VIEW_OWN_REVIEW` / `GIVE_FEEDBACK` to everyone (own scope). **Fix:** show these in
   the employee sidebar and drop the over-restrictive frontend gate (the backend still scopes to own
   data — no RBAC weakening).
2. **Managers see enterprise tools they shouldn't carry day-to-day.** Succession, Org, JD sit on primary
   nav at `minRole: MANAGER`. **Fix:** demote to the Advanced (HRBP+) group; routes/backend unchanged.
3. **Dashboard "Home" hidden from employees** (nav `minRole: MANAGER`) though the index route renders for
   everyone. **Fix:** Home at `minRole: EMPLOYEE`.

## Intra-screen follow-ups (Phase 1.2, minimal — to avoid shown-then-denied *within* a newly-exposed screen)
- **Goals:** gate the "New goal" + "Recompute scores" actions to Manager+ (they need `MANAGE_REPORTS_GOALS`
  / cycle management); the own-goals read + own-actuals entry stay for employees.
- **Feedback:** gate the "Cycles" tab to Manager+ (`MANAGE_FEEDBACK_CYCLE`); "For me" / "My 360" stay for all.
- **Reviews:** the create/transition actions are already capability-gated server-side; confirm no
  employee-facing create entry point (verify when touched).

Deeper intra-screen action gating across all screens is a finish-the-web concern (logged in QUESTIONS),
not RW_BUILD_1.
