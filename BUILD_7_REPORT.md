# BUILD_7 — Tier-3 features — REPORT

**Status: COMPLETE — both features delivered backend-first, committed, pushed,
green.** Backend grew 1150 → **1171**; frontend tsc + lint + build clean, **43
vitest**; both features verified end-to-end live. Zero LLM calls.

## Feature A — Review section comments

**7.A.1 — ReviewComment model + API** (`7ac0710`)
A tenant-scoped `ReviewComment` (review FK, author FK, self `parent` FK for
one-level replies, optional `section` tag, body, `edited_at`). Endpoints:
`GET/POST /api/reviews/<pk>/comments`, `PATCH/DELETE .../comments/<id>`.
Comments inherit the review's visibility EXACTLY — the views reuse
`VIEW_OWN_REVIEW` + `check_object_scope` (the review-detail gate), so you can only
list/add comments on a review you can already see (out-of-scope → 403,
cross-tenant → 404), and commenting never broadens review visibility. Authorship
server-set; edit/delete author-only (another's → 403); delete is soft-delete.
One-level threading (reply-to-reply → 422 `COMMENT_THREADING_ERROR`; foreign
parent → 404). All mutations audited. **D18** (threading depth; reuse
`VIEW_OWN_REVIEW`, not a new capability; 422 for the threading rule). 11 tests.

**7.A.2 — review comments UI** (`5bdd2d5`)
A Comments panel on the review detail: threaded one-level discussion, a section
tag, a new-comment form, inline replies, author-only edit/delete — all states +
kind-aware errors. Pure tested `threadComments()` (orphan-safe grouping); the MSW
mock gained a mutable comment store. **[live]** create → reply (one level) → list
(real author name, parent set) → edit (edited_at) → out-of-scope employee 403 →
author delete 204.

## Feature B — Nine-box drag-reposition (persisted human override)

**7.B.1 — override endpoint** (`656cf94`)
Override fields on `NineBoxPlacement` (`override_box`/`override_by`/`override_at`/
`override_rationale`) sit ALONGSIDE the computed `box`, which is never rewritten;
the serializer adds `effective_box` (override ?? computed) + `is_overridden`.
`PUT/DELETE /api/succession/nine-box/<id>/override` (set/clear), audited. New
`OVERRIDE_NINE_BOX` capability = **HRBP/Admin only** (tighter than Manager+
`ASSESS_NINE_BOX`): a Manager (has VIEW/ASSESS) → 403; an employee → 404 at the
succession participant gate (the employee-invisible invariant is untouched);
cross-tenant placement → 404. **D19** — the override is DISPLAY-ONLY: it
repositions the grid cell but does NOT alter the deterministic readiness/bench
math, and is fully reversible. 6 tests.

**7.B.2 — drag-reposition UI** (`<this commit>`)
The 9-box grid is now drag-interactive for HRBP/Admin (native HTML5 DnD — **D20**,
no new dependency since react-dnd isn't installed): drag a card to a cell → sets
the override; an override marker ● + a reset-to-computed button; per-chip pending
state. `NineBoxGrid` was generalised to a loose `NineBoxCell` contract so it still
serves the read-only analytics calibration grid. Non-HRBP roles get the grid
read-only (no dead UI). Pure tested `bucketByEffectiveBox`. **[live]** HRBP set
box → computed box PRESERVED, effective=override, is_overridden=true; Manager 403;
employee 404; clear → back to computed.

## Verification
- **[test]** Backend **1171 passed, 2 deselected** (grew 1150→1171: +11 review
  comments, +6 nine-box override, + the rbac matrix entry). Frontend **43 vitest**
  (+6: threadComments, bucketByEffectiveBox). tsc + lint + build clean. Two
  migrations apply + reverse clean (`reviews/0004`, `succession/0002`).
- **[live]** Both features driven end-to-end on the running stack (see above),
  RBAC/scope boundaries asserted (review out-of-scope 403, succession employee 404
  / manager 403, cross-tenant 404).

## Invariants held
HITL untouched; review visibility never broadened (comments inherit it exactly);
the succession employee-404 + the deterministic readiness math both intact (the
override is display-only); audit trail on every mutation; tenant isolation throughout.

## Decisions
- **D18** — review comments: one-level threading; reuse `VIEW_OWN_REVIEW`; 422 for threading.
- **D19** — nine-box override: display-only (not readiness-feeding); HRBP/Admin-only; computed box preserved + reversible.
- **D20** — native HTML5 drag-and-drop (react-dnd not installed); `NineBoxGrid` generalised for both consumers.

## For Hari (manual check)
- Drag a card across the 9-box as HRBP/Admin and confirm the feel + the override
  marker/reset read well (no headless browser this run — API + component verified).
- Confirm review comments read well on the review detail (threading, section tags).

Next: BUILD_8 (mobile foundation).
