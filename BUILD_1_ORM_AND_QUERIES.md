# BUILD_1 — N+1 elimination, ORM optimization & the query foundation

> Read BUILD_0_READ_FIRST.md IN FULL first. This is build 1 of 5. Goal: make the data layer fast and
> correct under load — kill the N+1s (especially the ones the name-resolution work introduced), add the
> missing query optimizations, and establish a reusable, test-enforced pattern so N+1s can't silently
> come back. This is the foundation everything else sits on, so it goes first.

This build needs ZERO LLM calls. Use the FakeLLMProvider in any test that touches an AI seam.

---

## Phase 1.1 — Inventory the query cost (measure before you change)

- Add a dev/test utility to COUNT queries per endpoint: a pytest helper using
  `django.test.utils.CaptureQueriesContext` (or `assertNumQueries`) so every list/detail endpoint can be
  asserted. Put it in `apps/testsupport/` (or wherever test helpers live).
- Write a "query budget" test module that hits each major LIST endpoint (reviews, feedback cycles,
  approvals inbox + tracker, goals/KPIs, org people, succession bench, JD library, audit console,
  analytics lists, career roadmaps) with a seeded dataset of ~30–50 rows per list, and RECORDS the
  current query count for each. Commit this as the BASELINE (the numbers go in PROGRESS.md).
- Identify every endpoint whose query count scales with row count (the N+1 signature: queries ≈ rows ×
  k). The system-design doc already flags the prime suspects: the `*_name` / `*_title`
  SerializerMethodFields added for the UUID→name fix dereference person/entity FKs per row on paginated
  lists that don't `select_related`. Confirm which lists actually exhibit it.

**Verify [test]:** the query-budget tests run and produce a baseline table. Commit
`BUILD_1 1.1 — query-count harness + N+1 baseline`.

## Phase 1.2 — Fix the name/title resolution N+1 (the big one)

- For every serializer that exposes a resolved `*_name`/`*_title` (reviewer_name, subject_name,
  employee_name, manager_name, actor_name, target_name, goal_title, cycle_name, jd_title, candidate
  labels, etc.), make the LIST queryset eager-load the underlying FK:
  - `select_related(...)` for forward FK / one-to-one (the common case for a person/owner/subject).
  - `prefetch_related(...)` for reverse / many relations (e.g. a review's KPIs, a cycle's invitations,
    a goal's KPIs, an approval's steps).
- Apply at the VIEW/queryset level (`get_queryset`) so it covers list + detail. Prefer a single,
  explicit `.select_related(...).prefetch_related(...)` per viewset over scattered fixes.
- Where a `*_name` resolves through the directory/user, ensure the join is to the user table once, not
  per row. If a serializer resolves names via a separate lookup dict, build that dict ONCE per request
  (bulk fetch), not per row.
- Re-run the query-budget tests: each fixed list's query count must become ~CONSTANT (independent of row
  count) — assert this in the tests (e.g. `assertNumQueries(<=N)` with N not scaling with rows).

**Verify [test]:** the previously-scaling lists now have bounded, near-constant query counts; full suite
green; the anonymity rules still hold (feedback list must NOT start eager-loading giver identities — keep
the anonymised path; add a test asserting no giver identity is reachable through the new joins).
Commit `BUILD_1 1.2 — eliminate name/title N+1 via select/prefetch_related`.

## Phase 1.3 — Broader ORM optimization

- Audit `.only()` / `.defer()` opportunities on heavy serializers (don't over-fetch wide rows for a list
  that shows 5 columns) — apply where it measurably helps without breaking a serializer field.
- Ensure every hot multi-tenant query is index-covered: cross-check the 17 existing composite indexes
  (all tenant-leading) against the actual `WHERE`/`ORDER BY` of the hot list/detail querysets. Where a
  hot query orders/filters on a column not covered by a tenant-leading composite index, ADD the index
  (a migration) — but only where a real query needs it; don't speculatively index. Document each added
  index in DECISIONS.md with the query it serves.
- Find any `.count()` + slice patterns or `len(queryset)` that force full evaluation where pagination
  should bound it; fix to use proper pagination/`exists()`.
- Check for aggregation done in Python over a queryset that the DB should do (`annotate`/`aggregate`) —
  e.g. headcount/vacancy rollups, analytics aggregates, KPI weight sums — and push them into the ORM
  where it's a clear win and keeps the result identical (add a test asserting equality of old vs new
  result on seeded data before replacing).

**Verify [test]:** new index migrations apply cleanly + reverse; aggregation refactors are covered by an
equality test vs the prior result; suite green. Commit `BUILD_1 1.3 — ORM optimization + targeted indexes`.

## Phase 1.4 — Pagination & large-tenant correctness

- Confirm EVERY list endpoint paginates (default page size sane, e.g. 50) and that the frontend client
  treats paginated responses correctly (the contract notes some lists were treated as arrays). Where the
  client mishandles a paginated shape, fix the client (this is the one frontend touch in BUILD_1).
- For the org directory specifically (the system-design doc flags `useDirectory` loading the whole tree):
  ensure the backend supports a bounded/lazy fetch (paginated or subtree-scoped) and that the client
  doesn't pull 10k rows at once. If a new bounded endpoint/param is the clean fix, add it (scoped,
  tested); otherwise paginate the existing one and lazy-load on the client. Log the approach in
  DECISIONS.md.
- Add a "large tenant" test: seed a tenant with ~1–2k employees (idempotent, gated behind a marker so it
  doesn't slow every run) and assert the hot lists stay bounded in queries and paginate correctly.

**Verify [test]+[live]:** the large-tenant test passes; live-check one heavy list against the running
stack and capture the response time/shape in PROGRESS.md. Commit `BUILD_1 1.4 — pagination + large-tenant
correctness`.

## Phase 1.5 — Lock it in (regression guard)

- Promote the query-budget tests into the normal suite so any future change that reintroduces an N+1
  FAILS CI/test. Add a short `docs/QUERY_BUDGETS.md` listing each endpoint's asserted query ceiling and
  the rationale, so future work knows the bar.
- Update PROGRESS.md with the before/after query counts table (the headline win of this build).

**Verify [test]:** the guard tests fail if you deliberately remove a `select_related` (sanity-check it,
then restore). Commit `BUILD_1 1.5 — query-budget regression guard + QUERY_BUDGETS.md`.

---

## End of BUILD_1
Write `BUILD_1_REPORT.md`: the before/after query-count table, indexes added (+ the query each serves),
the pagination/directory fix, any QUESTIONS/DECISIONS/BLOCKER entries, the backend test count after
(must be ≥ 1059 + the new tests), and what to spot-check. Then proceed to BUILD_2.
