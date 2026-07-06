# BUILD_7 — Tier-3 features: review section comments + nine-box drag-reposition (backend-first)

> Read BUILD_0_READ_FIRST.md first; all its rules apply. Build 2 of the final push. These are the two
> NEW-backend features Hari green-lit. Build BACKEND-FIRST with tests, then the frontend. Do NOT weaken
> RBAC/scope/tenant isolation, HITL, or the audit trail. Almost zero LLM calls.

---

## FEATURE A — Review section comments

A threaded/section comment capability on a performance review, so a reviewer/approver can leave comments
on a review (and, where appropriate, on specific sections) during the DRAFT/PENDING/approval flow.

### 7.A.1 — Backend: the Comment model + endpoints
- Add a tenant-scoped `ReviewComment` model: tenant FK (TenantScopedModel), review FK, author FK,
  optional `section` (which review section it targets — summary/strengths/development/goals/recs, or
  null = general), `body`, created/edited timestamps, and a soft visibility rule. INSERT + own-edit;
  cross-tenant 404.
- Decide threading depth in DECISIONS.md (default: one level — comments + optional replies, not deep
  trees — keep it simple and shippable).
- Endpoints (RBAC-gated, scope-bound to who can see the review): list comments for a review, create a
  comment, edit/delete own comment. Cross-tenant/out-of-scope → 404. Add to the RBAC matrix (a new
  capability or reuse the review-view/edit capability — justify in DECISIONS.md).
- WHO can comment: anyone who can view the review in their scope (reviewer, manager, HRBP, admin) per
  the existing review scope; an employee viewing their own finalized review per existing rules. Do NOT
  broaden review visibility — comments inherit the review's existing scope exactly.
- Tests: create/list/edit/delete; scope (can't comment on a review you can't see → 404); tenant
  isolation; the comment never leaks across the review's existing visibility boundary.

**Verify [test]:** model migration apply/reverse; the endpoint tests green; scope/tenant tests green.
Commit `BUILD_7 7.A.1 — ReviewComment model + API`.

### 7.A.2 — Frontend: comments on the review detail
- On the review detail page, add a comments affordance — general comments + (if section targeting is in)
  a way to comment on a section. Real API wiring, all states (loading/empty/error/own-vs-others), edit/
  delete own. Respect the kind-aware error mapper + the existing review HITL/state treatment.
- Keep it consistent with the design tokens (no new design system — elevation on existing bones).

**Verify [test]+[live]:** comment end-to-end against the running stack (create→list→edit→delete, scoped);
a user who can't see the review can't comment; frontend tests for the comment state; build clean. Commit
`BUILD_7 7.A.2 — review comments UI`.

---

## FEATURE B — Nine-box drag-reposition (persisted human override)

Today the nine-box is read-only / re-assess via a dialog. Add a persisted HUMAN OVERRIDE so an HRBP can
drag a person to a new box and have it stick (an explicit override of the computed placement), audited.

### 7.B.1 — Backend: the persisted-override endpoint
- Add a tenant-scoped persisted override for a nine-box placement: tenant FK, the subject, the overriding
  box (performance×potential cell), who set it, when, optional rationale. It OVERRIDES the computed
  placement for display but never silently rewrites the computed score — keep both (computed vs override),
  so the override is transparent and reversible. INSERT/update own-tenant; cross-tenant 404.
- Endpoint: set/clear the override for a subject (HRBP/Admin only — succession is HRBP-scoped, employees
  never see it; keep the employee→404 invariant absolutely). Audited (AuditLog INSERT). Scope-bound.
- Decide in DECISIONS.md: does the override feed succession readiness/bench, or is it display-only?
  Default: display-only override of the box position, clearly marked as a human override, not altering
  the deterministic readiness math — safest, most transparent.
- Tests: set/clear override; HRBP/Admin only (manager/employee → 403/404 as the existing succession rules
  dictate); tenant isolation; the override is reversible; audit row written.

**Verify [test]:** migration apply/reverse; endpoint + RBAC + scope + audit tests green; employee still
gets nothing from succession. Commit `BUILD_7 7.B.1 — nine-box override endpoint`.

### 7.B.2 — Frontend: drag to reposition
- Make the nine-box grid support drag-to-reposition (the design already has react-dnd available). On drop,
  call the override endpoint; show the box as a human override (a marker/badge distinguishing it from the
  computed placement) with a way to clear it back to computed. All states; optimistic with rollback on
  error. HRBP/Admin only; employees never see succession (unchanged).
- No dead UI: the drag only appears for roles allowed to override; for others the grid stays read-only.

**Verify [test]+[live]:** drag a person → override persists → reload shows it → clear → back to computed;
employee still 404s on succession; frontend tests for the drag/override state; build clean. Commit
`BUILD_7 7.B.2 — nine-box drag-reposition UI`.

---

## End of BUILD_7
Write `BUILD_7_REPORT.md`: the two features as-built (models, endpoints, RBAC/scope/audit, UI), the
DECISIONS entries (threading depth, override-feeds-readiness-or-not), how the succession employee-404 and
review-visibility invariants were preserved, test counts, [test]/[live]/[build] honesty, commit list.
Then proceed to BUILD_8.
