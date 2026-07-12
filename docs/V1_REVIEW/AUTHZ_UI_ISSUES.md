# AUTHZ_UI_ISSUES — every "visible but unauthorized" control, and the fix

The #1 complaint: users see buttons/pages they aren't allowed to use, click, and hit
"You are not authorized" / "outside your access scope". Audit grounded in code; each item lists the
control, who saw it vs who is actually allowed, and its fix. **All fixed this run** (commits in
FINAL_REPORT.md) except the explicitly-noted by-design/deferred items.

## The architecture fix (single source of truth)
Root cause: the client had **no capability information** — `/api/auth/me` returned only `role`, and the
UI re-derived permissions from a coarse `atLeast(role)` ladder. Action buttons inside "everyday" pages
(reviews, goals, feedback…) each needed a hand-written gate, and the biggest one was missing.

**Fix:** `/me` now returns `capabilities` — computed by `capabilities_for_role()` from the **SAME**
`CAPABILITIES` matrix `HasCapability` enforces (`apps/rbac/matrix.py`; locked by a test that asserts the
payload exactly mirrors `role_has_capability`). `AuthContext` exposes `can(capability)`, and controls are
gated on it — one source of truth, no drift possible. Server-side enforcement is **unchanged** (defense
in depth: hidden in UI AND enforced on the server).

## Findings & fixes

### 1. 🔴 Reviews ActionBar — state-only, NO role gate (the critical one) — FIXED
`frontend/src/features/reviews/ReviewDetailPage.tsx`. Any viewer of a review — including an EMPLOYEE
viewing their own — saw, by state: **Request AI draft** (`run_ai_review_draft`, M+), **Start
editing/Edit/Revise + Save draft/Submit** (`manage_reviews`, M+), **Approve/Reject** (`approve_review`,
M+), **Finalize** (`finalize_review`, M+). All 403 for an employee.
**Fix:** every button is now gated by `can(<its exact server capability>)` via the pure helper
`visibleReviewActions(state, caps)` (unit-tested: an employee sees NO action in any state; capabilities
gate independently). The editor body (`EDITING` state) is read-only without `manage_reviews`. The
advisory `ReviewQualityCheck` now uses `can("manage_reviews")` (its endpoint's capability) instead of
`atLeast("MANAGER")`.

### 2. 🟠 Create-review people picker offered out-of-scope targets — FIXED
`ReviewsListPage.tsx` `CreateReviewDialog` listed the whole directory; a Manager picking someone outside
their subtree hit the create-time `actor_can_access` 403. **Fix:** new shared hook
`useScopedPeople()` (`frontend/src/lib/hooks/useScopedPeople.ts`) mirrors the server's data-scope rule
(HRBP/Admin → all; Manager → self+subtree) — used here and in every scope-checked picker below.

### 3. 🟠 Feedback create-cycle subject picker — FIXED (same pattern)
`FeedbackPage.tsx` `CreateCycleDialog` → `useScopedPeople()`. (The `CycleSheet` **InviteForm is
deliberately unchanged**: the server does NOT scope-restrict the giver — anyone in the tenant can be
invited to give feedback — so the all-people list there is correct.)

### 4. 🟠 Analytics pickers — FIXED (same pattern)
`AnalyticsPage.tsx` Individual "Employee" + Department "Head" selectors → `useScopedPeople()` (the
server confines both to the actor's scope; out-of-scope picks 403/404'd).

### 5. Goals — already fixed earlier this branch; now unified
The New-goal picker was scope-filtered in the BUGS_GOALS fix; it now uses the same `useScopedPeople()`
hook (no duplicated logic to drift).

## Verified-clean surfaces (audited, no action needed)
Employee dashboard cockpit (no manager tiles fetched/rendered) · Goals page (create/approve/record/updates
all correctly gated, incl. the OWN-only Record rule) · Feedback/Check-ins/Recognition tabs · Approvals
RouteSheet (act buttons only on the caller's own pending inbox steps; server re-checks assignee) ·
Admin/Billing/TenantConfig/Integrations (route `min="ADMIN"`) · Audit (route `min="HRBP"`) · Org positions
+ reassign (`atLeast("HRBP")` = the exact capability tier) · JD authoring ActionBar (HRBP+) · nine-box
override (HRBP+) · routes/nav/⌘K (role-filtered consistently).

## By-design / noted (not 403 walls; documented, unchanged)
- **Chat ProposalCard "Approve"** defers entirely to the server's audited execute gate — an Employee can
  be shown a proposal whose execution their role can't perform; the error is handled inline. This is the
  intended HITL "propose → server enforces" pattern (`apps/ai/views.py:90-108`). Unchanged.
- **UI stricter than server** (lost capability, not a wall): org chart + Analytics-individual +
  approvals tracker are nav-gated M+ though the read capabilities are EVERYONE-scoped; `GoalUpdates`
  add is own-only in UI though a manager-in-scope may POST; JD nav is HRBP while the route allows
  Manager (who holds `request_jd`). These widen scope if changed — deliberate v1 conservatism; listed in
  OPEN_QUESTIONS.md for a product decision.
- **Self-approval**: the server permits a Manager with capability + scope to approve a review where they
  are the subject (scope OWN passes). The UI mirrors the server; flagged in OPEN_QUESTIONS.md as a
  governance question (fixing it is a server-side product decision, not a UI patch).
