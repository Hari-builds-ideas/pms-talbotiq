# DECISIONS.md — non-trivial choices in the build series

> Each entry: the decision · options considered · why · safe-default rationale ·
> the QUESTIONS.md item it resolves (if any).

---

### D1 (BUILD_1/1.2) — Where the N+1 fix lives, and the "bounded" threshold

**Decision.** Add `select_related`/`prefetch_related` at the point that owns the
queryset for each list path: in the **view** when the view builds it inline
(reviews, goals, org, feedback), in the **service** when a service function
returns it (jd `search_jds`, career `list_roadmaps`). The budget guard
(`ScalingResult.is_bounded`) treats an endpoint as bounded when extra rows add
`≤ max(2, extra_rows//4)` queries — i.e. a small constant, not one-per-row.

**Options considered.** (a) one central `.select_related` mixin on pagination —
rejected: the FK set differs per serializer and a blanket join risks pulling
unused tables; (b) `prefetch_related` everywhere — rejected: a forward FK is
cheaper as a JOIN (`select_related`); prefetch is reserved for the one reverse
relation (goals→kpis). (c) per-row caching — rejected: doesn't fix the query.

**Why safe.** Output bytes are identical (only query count changes); no scope,
tenant, or RBAC predicate is touched; the feedback fix select_relates only
`subject` (givers are never on that serializer), so anonymity is unaffected.
Verified by the 6 app suites (354) + the budget module.

### D2 (BUILD_1/1.3) — Two targeted indexes; aggregation left in Python (no-win)

**Indexes ADDED (each serves a real, identified hot query — not speculative):**
- `ix_review_tenant_recent` = `(tenant, -created_at)` on Review. Serves the
  default paginated list for the broad scopes (Manager/HRBP/Admin):
  `WHERE tenant=? ORDER BY -created_at LIMIT page` — eliminates a filesort over
  the full tenant set. Employee-scope filtering is already covered by the
  `(tenant, employee, cycle)` unique-constraint index.
- `ix_goal_emp_recent` = `(tenant, employee, -created_at)` on Goal. Serves the
  hottest Goal read — an employee's own goals / a manager's team goals
  (`WHERE tenant=? AND employee[_id in …] ORDER BY -created_at`). The only
  pre-existing index was `(tenant, cycle, employee)` (cycle-leading), which
  cannot serve an employee filter; this is the only employee-leading index.

Both migrations apply AND reverse cleanly; DDL verified (`… created_at DESC`).

**Considered and REJECTED (honesty — not every audit item yields a change):**
- `.only()`/`.defer()` on list serializers: reviews intentionally serialize
  `draft_body`/`final_body`; JD bodies live on `JDVersion`, not the list row;
  remaining text columns are small. No measurable win, real risk of breaking a
  serializer field. Left alone.
- Push analytics aggregation into the DB (`Avg`, `GROUP BY`): rejected as a
  net-negative. `department_analytics` and `calibration_grid` already
  materialise their result set exactly once (the individual rows are part of the
  output), and MySQL 8 has no clean median aggregate — a DB rollup would add a
  second query, not remove one. The Python aggregation runs over already-fetched
  rows, so it is the optimal shape.
- `person_card`: added `select_related("manager")` (saves one round-trip on a
  hot detail endpoint; covered by existing org tests).

### D3 (BUILD_1/1.4) — Pagination audit; dashboard counts moved server-side

**Audit result.** Every employee-/entity-scaling LIST already paginates
(`StandardResultsSetPagination`) AND the React client already consumes each as
`Paginated<T>` (reviews, goals, org positions, feedback cycles, jd library/
requests, career roadmaps, succession roles/bench/nine-box). The contract's
"some lists treated as arrays" worry was already resolved in the reskin — so the
"one frontend touch" was NOT a pagination-shape fix. The bare-array responses
that remain are per-parent bounded sub-lists (a goal's KPIs, a review's
timeline/assessments, a cycle's requests, a jd's versions, a roadmap's progress,
template/integration libraries) — not employee-scaling, so they stay bare.

**The real large-tenant smell + fix.** Two screens fetched a whole collection
just to derive a few numbers: the admin dashboard tiles pulled the FULL user
list to compute active-count + role distribution (O(users) download to show ~5
numbers). Fixed with a DB-aggregated `GET /api/admin/users/stats` (one GROUP BY)
and rewired the two tiles to it — this IS the one frontend touch. Same class of
fix as the directory: don't ship N rows to the client to count them.

**Considered and chosen NOT to change in BUILD_1 (logged as Q1):**
- `GET /api/admin/users` (the admin user TABLE) stays unpaginated: its remaining
  consumer is the admin table itself, and paginating it needs page controls +
  server-side search to stay usable — a UI change that belongs in BUILD_5, not
  an ORM build. Its dashboard-aggregate consumer is already removed (above).
- `GET /api/cycles/<id>/scores` (team scores) stays unpaginated: consumers
  (`ReviewEvidence`, `useGoals`) fetch the cohort to pick ONE employee's score;
  the clean fix is a scoped single-score lookup, deferred. `/scores/me` already
  exists for the self case.
- Org CHART lazy-loading (expand-on-demand): the tree endpoint is already
  scope-bounded (an Employee gets only their line — now asserted by the
  large-tenant test), so non-admins are safe today. A full org CHART inherently
  needs its structure, so expand-on-demand is a viz/UX feature for BUILD_5, not
  an ORM concern. The directory's per-row name needs are already met by the
  `*_name` payload fields added in 1.2, making the tree a fallback resolver.
