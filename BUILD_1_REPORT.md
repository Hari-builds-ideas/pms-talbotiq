# BUILD_1 — ORM & Queries — REPORT

**Status: COMPLETE.** All 5 phases implemented, verified, committed, and pushed to
`main`. Backend suite **1073 passed, 2 deselected** (the gated large-tenant tests);
frontend `tsc` + `lint` + `build` clean. No regressions; the suite grew from 1065.

This build was CODE-ONLY against the existing stack (existing MySQL/Redis/Celery/
React). It needed **zero real LLM calls**.

## The headline win

Every paginated LIST endpoint was N+1 because the `*_name`/`*_title` serializer
fields (added in the earlier UUID→name fix) dereferenced a person/entity FK per
row. After Phase 1.2 every list is **O(1) in rows**:

| endpoint | before (5→25 rows) | after |
|---|---|---|
| reviews | 18 → 78 (Δ60) | 3 → 3 |
| goals | 23 → 103 (Δ80) | 4 → 4 |
| org positions | 13 → 53 (Δ40) | 3 → 3 |
| feedback cycles | 8 → 28 (Δ20) | 3 → 3 |
| jd library | 8 → 28 (Δ20) | 3 → 3 |
| career roadmaps | 8 → 28 (Δ20) | 3 → 3 |
| succession bench | 3 → 3 | 3 → 3 |

Worst offender (goals) dropped from 103 queries per 25-row page to 4.

## Phase-by-phase

**1.1 — query-count harness + N+1 baseline** (`5533154`)
`apps/testsupport/query_budget.py` (count_queries / ScalingResult / measure_scaling,
additive seeding) + `apps/core/tests/test_query_budgets.py` (7 endpoint budget
tests). Recorded the baseline: 6 of 7 lists N+1.

**1.2 — eliminate the name/title N+1** (`c4cda54`)
`select_related`/`prefetch_related` at the layer that owns each queryset: reviews
(list + calibration), goals (+ prefetch kpis for `kpi_weight_total`), org positions,
feedback cycles (subject only — **givers are never serialized, anonymity intact**),
jd library (`search_jds`), career roadmaps (`list_roadmaps`). Flipped
`ENFORCE_BOUNDED=True`. Output bytes unchanged; no scope/tenant/RBAC predicate
touched. Giver-anonymity assertions still green.

**1.3 — ORM optimization + targeted indexes** (`44e7d3f`)
Two indexes, each serving an identified hot query (not speculative):
`ix_review_tenant_recent (tenant, -created_at)` (broad-scope default list) and
`ix_goal_emp_recent (tenant, employee, -created_at)` (the employee/team Goal read,
previously with no employee-leading index). Both migrations apply **and reverse**
cleanly; DDL verified (`created_at DESC`). `person_card` got `select_related("manager")`.
Audit findings deliberately left unchanged (no `.only()`/`.defer()` win; analytics/
calibration aggregation stays in Python — a DB rollup would add a query, not save
one). See `DECISIONS.md` D2.

**1.4 — pagination + large-tenant correctness** (`f6b61f2`)
Audit: every entity LIST already paginates and the React client already reads each
as `Paginated<T>` (the reskin had fixed the "treated as arrays" worry). The real
large-tenant smell was the **admin dashboard fetching the whole user list to count
it** — fixed server-side with `GET /api/admin/users/stats` (one GROUP BY) and the
two dashboard tiles rewired to it (the one frontend touch). Added the gated
`test_large_tenant.py` (~1.2k employees): hot lists stay page-bounded and ≤15
queries in both tenant and big-team scope; the org tree is scope-bounded (an
Employee gets only their line). See `DECISIONS.md` D3, `QUESTIONS.md` Q1.

**1.5 — regression guard + QUERY_BUDGETS.md** (`aa7ca9c`)
The budget guard runs in the normal suite, so a future N+1 fails CI. Sanity-checked:
removing the reviews `select_related` made the test fail (Δ=60); restoring returned
it green. `docs/QUERY_BUDGETS.md` documents the rule, the guard, per-endpoint
before→after, and how to add a new list.

## Invariants preserved (verified, not assumed)
- **Tenant isolation / RBAC / scope** — only `select_related`/index/aggregate
  changes; no predicate altered. Cross-tenant still 404s.
- **360 anonymity** — feedback cycle select_relates only `subject`; the serializer
  carries no giver field; the existing giver-anonymity assertions stayed green.
- **HITL** — untouched (no AI paths in this build).

## Deferred (logged, none a correctness/isolation risk today)
Admin user TABLE pagination (needs UI page controls + search), a scoped
single-employee score lookup, and org-chart expand-on-demand lazy-load — all are
UI/UX work for BUILD_5, not ORM work. The tree is already scope-bounded and the
dashboard no longer pulls the user list. See `QUESTIONS.md` Q1.

## Verification ledger
- **[test]** 1073 passed, 2 deselected; budget guard sanity-checked (fail → restore).
- **[test]** large-tenant 2/2 (5s) at ~1.2k employees.
- **[build]** frontend tsc + lint + production build clean.
- **[live]** running stack: `/admin/users/stats` {total 31, roles sum 31} 70ms;
  `/org/tree` 31 nodes 68ms; `/reviews/?page_size=50` {count,next,previous,results} 39ms.

Next: **BUILD_2 — ASYNC_AI**.
