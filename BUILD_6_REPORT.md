# BUILD_6 — Stabilize — REPORT

**Status: COMPLETE — all 5 phases delivered, committed, pushed, green.** The
org-chart crash is root-caused and fixed, the not-iterable bug class swept, the
three Q1 large-tenant items closed, and the stabilization sweep found + fixed a
whole class of malformed-input 500s. Backend grew 1130 → **1150**; frontend tsc +
lint + build clean, 37 vitest; the end-to-end smoke is **47/47**. Zero LLM calls
in tests (the one live AI touch is the smoke's single chat query).

## Phases

**6.1 — org-chart crash (".for is not iterable") + not-iterable sweep** (`6921ae0`)
ROOT CAUSE: a type-lie. `OrgTree`/`OrgTreeView` assumed `nodes` was an id→node map
and `edges` were `[id,id]` tuples, but `GET /api/org/tree` returns `nodes` as a
LIST and `edges` as `{from,to}` objects — so `for (const [parent,child] of
tree.edges)` array-destructured plain objects → "not iterable" (and `tree.nodes[id]`
on an array → undefined). FIX: backend node now carries `display`
(= display_name||email); a pure, tested `normalizeOrgTree` converts the raw wire
shape at the boundary (wired in `useOrgTree` AND `useDirectory` — the latter was a
second consumer silently returning "Unknown"). SWEEP: audited every
`for...of`/`.map`/spread + live-probed all 16 bare-array endpoints (all real
arrays) — the OrgTree type-lie was the only runtime crash. Backend wire-shape +
display tests; 5 frontend normalizer tests.

**6.2 — admin users pagination + search** (`f55f046`, Q1 item 1)
`GET /api/admin/users` paginates (`{count,next,previous,results}`) + a server-side
`?search=` (email/display/role, icontains). The manager column + manager dropdowns
moved to the tenant-wide `useDirectory` (the two consumers that relied on the full
array). Debounced search box + page controls + distinct no-users/no-matches states.
DECISION D15 (materialize + paginate, not a lazy queryset, to keep `list_users`
self-contained for its non-request test caller). +3 backend tests.

**6.3 — scoped single-employee score lookup** (`dd7215a`, Q1 item 2)
`GET /api/cycles/<cid>/scores/<employee_id>` — one score, scope-bound
(OWN/TEAM/TENANT), out-of-scope/cross-tenant/no-score → 404. The review
EvidencePanel stopped pulling the whole cohort to `.find` one person. The cohort
endpoint stays for the genuine multi-row consumers (GoalsPage grid + calibration).
+6 backend tests.

**6.4 — org-chart expand-on-demand / lazy-load** (`a7cb383`, Q1 item 3)
`?root=<id>` (subtree) + `?depth=<n>` params, scope-identical (an Employee with
either still sees only their line; out-of-scope root → 404 no-leak). `LazyOrgTreeView`
fetches top levels then children on expand (per-node spinner) for HRBP/Admin;
narrow scopes keep the whole-tree view. DECISION D16. Also fixed a 6.1-introduced
MOCK regression (the MSW `orgTree()` still returned the normalized shape → would
crash dev mode; now raw). +5 backend, +2 frontend tests.

**6.5 — stabilization sweep** (`<this commit>`)
Ran `scripts/smoke.py` (47/47, every surface × every role, RBAC boundaries hold,
AI alive, no 500s) + an extended sweep of the complex/detail endpoints. That sweep
FOUND a bug class: a malformed UUID in a query param filtering a `UUIDField` made
the ORM raise Django's `ValidationError` → a 500 (`/api/ai/jobs?target=`,
`/api/reviews?cycle=`, `/api/goals?cycle=`, `/api/audit/logs?actor=`,
`/api/analytics/{calibration,department}?cycle=`, `/api/succession/nine-box?cycle=`
— 6 endpoints). FIX: a custom DRF exception handler maps DRF-unhandled Django
`ValidationError` → 400 (by definition bad input; genuine server bugs raise other
types and still 500), plus a targeted empty-list guard on the AI-jobs poll.
DECISION D17. Frontend iteration-crash class already swept in 6.1; no nested-array
iterations exist; no frontend changes needed.

## Verification
- **[test]** Backend **1150 passed, 2 deselected** (grew from 1130: +3 admin, +6
  cycles, +5 org/api +2 org/services, +1 ai-jobs, +5 exception-handler). Frontend
  **37 vitest** (+7 across org/normalizer/lazy helpers). tsc + lint + build clean.
- **[live]** `scripts/smoke.py` 47/47 against the running stack; org tree per-role
  walked crash-free (6.1); admin users paginated + searched (6.2); single score
  scoped (6.3); `?depth=1`→5 nodes / `?root=`→subtree / bogus→404 (6.4); the 6
  malformed-UUID endpoints now 400 not 500 (6.5).
- **[build]** prod frontend image rebuilt + redeployed; web restarted; `/readyz` 7/7.

## Decisions / questions / blockers
- DECISIONS: D15 (admin pagination), D16 (org lazy-load + the mock-shape fix),
  D17 (the Django-ValidationError→400 handler). No new QUESTIONS; no BLOCKERs.
- Q1 (the three deferred large-tenant items) is now fully CLOSED (6.2/6.3/6.4).

## For Hari (manual check)
- A browser pass of the org chart as HRBP/Admin to feel the lazy expand (no
  headless browser was available in this run — API-equivalent verified). Confirm
  the admin users search/pagination + the review evidence panel read well.

Next: BUILD_7 (Tier-3 features).
