# BUILD_6 — Stabilize: fix the crashes + close the Q1 large-tenant gaps

> Read BUILD_0_READ_FIRST.md (the original contract) IN FULL first — all its rules still apply
> (code-only, no infra; never weaken RBAC/scope/tenant isolation, HITL, anonymisation; backend suite
> never regresses + grows; frontend build/tsc/lint clean; commit+push per phase; .env never staged;
> PROGRESS/DECISIONS/QUESTIONS updated continuously; almost zero LLM calls — use FakeLLMProvider).
> This is the FIRST build of the final push. A crash beats any feature, so stabilization goes first.

---

## Phase 6.1 — Fix the org-chart crash ".for is not iterable" (root-cause, not patch)

Symptom: the org chart screen throws and the ErrorBoundary catches it ("This screen hit an unexpected
error… `.for is not iterable`"). This is a frontend type mismatch: code is iterating a value that is
NOT an array at runtime — almost certainly a response that is a paginated object `{count,next,previous,
results}` being treated as an array, OR a tree/children field that is null/undefined, OR an object where
an array was expected.

- REPRODUCE first: run the stack, log in (check seed_demo for the demo creds + workspace), open the org
  chart as the role that crashes (try HRBP/Admin — the full-tenant tree is the likely trigger). Capture
  the exact failing call/line.
- ROOT-CAUSE it: find where the org tree/positions/children data is iterated (`.map`/`for...of`/spread)
  and confirm what the API actually returns vs what the client assumes. Check `features/org/*`, the
  org API client methods, and the tree-building code. The `?person=<id>` deep-link path (added in 5.5b)
  is a prime suspect — verify it handles "person not found / empty / paginated" without assuming an
  array.
- FIX defensively + correctly: normalize the shape at the API/hook boundary (a paginated response →
  `.results`; a nullable children/tree → default `[]`), and make the render tolerant of empty/loading/
  error. Do NOT just `?.` it away — fix where the wrong shape enters, and guard the render.
- SWEEP the same class of bug everywhere: grep the frontend for places that iterate an API result that
  could be paginated-or-array or nullable (`.map(`, `for (`, `...`) over org/list/tree data, and fix any
  other latent "not iterable" crash. List every spot found in PROGRESS.md.

**Verify [live]+[build]:** the org chart loads for every role with no crash (capture each); the deep-link
`?person=<id>` works and degrades gracefully for a missing/again id; add a Vitest test for the shape-
normalization helper so it can't regress; tsc+lint+build clean. Commit `BUILD_6 6.1 — org-chart crash +
not-iterable sweep`.

## Phase 6.2 — Q1 item 1: paginate the admin users table (UI + server)

The admin user table (`GET /api/admin/users`) is unpaginated. Add server-side pagination + search +
page controls so a large tenant doesn't ship every user row.
- Backend: paginate the endpoint (StandardResultsSetPagination) + a `search` query param (name/email/
  role, tenant-scoped, server-side). Keep the existing `/users/stats` aggregate (added in 1.4) for the
  counts. Add tests (paginated shape; search filters; scope/RBAC unchanged; cross-tenant 404).
- Frontend: the admin users screen consumes the paginated shape, adds page controls + a search box
  (debounced), all states (loading/empty/error). Confirm no other consumer relied on the full array.

**Verify [test]+[live]:** the table paginates + searches against the running stack at a large seed; tests
green; build clean. Commit `BUILD_6 6.2 — admin users pagination + search`.

## Phase 6.3 — Q1 item 2: scoped single-employee score lookup

`GET /api/cycles/<id>/scores` returns the whole cohort; `ReviewEvidence`/`useGoals` fetch it just to pick
ONE employee's score. Add a scoped single-employee score lookup so the client fetches one, not the cohort.
- Backend: a scoped read (e.g. `GET /api/cycles/<id>/scores/<employee_id>` or a `?employee=` filter)
  returning just that employee's score, scope-bound (own/team/tenant per role), cross-tenant 404. Reuse
  the existing `/scores/me` pattern. Tests for scope + 404.
- Frontend: `ReviewEvidence` (and any other single-score consumer) calls the scoped lookup, not the
  cohort fetch. Keep the cohort endpoint for the calibration grid (which genuinely needs all rows).

**Verify [test]+[live]:** the single-score lookup returns one scoped row; the review evidence panel uses
it; tests green. Commit `BUILD_6 6.3 — scoped single-employee score lookup`.

## Phase 6.4 — Q1 item 3: org-chart expand-on-demand (lazy-load) for the full-tenant view

For HRBP/Admin the full org tree can be large. Add expand-on-demand so the chart loads a node's children
on expand rather than the entire tree up front.
- Backend: ensure the tree endpoint supports fetching a subtree / a node's direct reports (a `?root=<id>`
  or `?parent=<id>` param), scope-bound (an Employee still only ever sees their line — keep that), tested.
- Frontend: the org chart renders top levels and lazy-loads children on expand (loading state per node),
  for the broad-scope roles. Keep the existing scoped behaviour for non-admins.

**Verify [test]+[live]:** the chart lazy-loads children on expand at a large seed without pulling the
whole tree; scope still holds (employee sees only their line); tests green. Commit `BUILD_6 6.4 — org
chart lazy-load`.

## Phase 6.5 — Stabilization sweep

- Click/exercise every major screen as each role against the running stack (reuse scripts/smoke.py +
  manual-equivalent API hits) and FIX any other runtime crash or dead path you find (same discipline as
  6.1 — root-cause, guard, test). Do not redesign; just make nothing crash.
- Confirm the full backend suite + frontend build/tsc/lint are green; smoke passes.

**Verify [test]+[live]:** no screen crashes for any role; suite + smoke green. Commit `BUILD_6 6.5 —
stabilization sweep`.

---

## End of BUILD_6
Write `BUILD_6_REPORT.md`: the org-chart root cause + the not-iterable spots found/fixed, the three Q1
items closed, the stabilization sweep findings, test counts, [test]/[live]/[build] honesty, commit list.
Then proceed to BUILD_7.
