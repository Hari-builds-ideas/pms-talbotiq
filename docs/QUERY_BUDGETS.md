# Query Budgets — the N+1 regression guard

This is the bar every paginated LIST endpoint must clear, and how it's enforced.

## The rule

A list endpoint's query count must be **bounded** — independent of how many rows
the page contains. An N+1 has the signature `queries ≈ rows × k`; a healthy
endpoint is `queries ≈ constant`. We measure each endpoint at two row counts
(5 vs 25) and assert the **delta is a small constant, not one-per-row**:

```
bounded  ⇔  Δqueries ≤ max(2, extra_rows // 4)
```

(`apps/testsupport/query_budget.py` · `ScalingResult.is_bounded`). The slack
absorbs an occasional extra constant query (e.g. a COUNT for pagination) while
still failing hard on a real N+1.

## The guard

`apps/core/tests/test_query_budgets.py` runs in the **normal suite** (not gated)
with `ENFORCE_BOUNDED = True`. Any change that reintroduces an N+1 — e.g.
dropping a `select_related` — turns the relevant test red. This was sanity-checked
in Phase 1.5: removing the reviews `select_related` made `test_reviews_list_bounded`
fail with `Δ=60 [N+1]`, and restoring it returned the suite to green.

A second, heavier guard lives in `apps/core/tests/test_large_tenant.py`
(`@pytest.mark.large_tenant`, deselected by default — run with `-m large_tenant`):
it seeds ~1.2k employees and asserts the hot lists stay page-bounded **and** under
a fixed query ceiling (≤ 15) at scale, in both tenant and big-team scope.

## Per-endpoint budgets (before → after BUILD_1)

Query count to serve one page, measured at 5 then 25 seeded rows. "Before" is the
Phase 1.1 baseline; "after" is post Phase 1.2 `select_related`/`prefetch_related`.

| endpoint | path | before (5→25) | after (5→25) | what it resolves |
|---|---|---|---|---|
| reviews | `GET /api/reviews/` | 18 → 78 (Δ60) | 3 → 3 (Δ0) | employee, reviewer, human_reviewer, cycle |
| goals | `GET /api/goals/` | 23 → 103 (Δ80) | 4 → 4 (Δ0) | employee, created_by, approved_by + prefetch kpis |
| org positions | `GET /api/org/positions` | 13 → 53 (Δ40) | 3 → 3 (Δ0) | filled_by, reports_to, published_jd |
| feedback cycles | `GET /api/feedback/cycles` | 8 → 28 (Δ20) | 3 → 3 (Δ0) | subject (givers never resolved here) |
| jd library | `GET /api/jd/` | 8 → 28 (Δ20) | 3 → 3 (Δ0) | created_by |
| career roadmaps | `GET /api/career/roadmaps` | 8 → 28 (Δ20) | 3 → 3 (Δ0) | employee, target_jd, target_position |
| succession bench | `GET /api/succession/critical-roles/{id}/bench` | 3 → 3 (Δ0) | 3 → 3 (Δ0) | already bounded |

**Headline:** every paginated list is now O(1) in rows. The worst offender
(goals) dropped from 103 queries per 25-row page to 4.

## What is NOT in the budget guard, and why

Bare-array (non-paginated) responses are intentionally per-parent **bounded**
sub-lists, so they have no N+1 risk to guard: a goal's KPIs, a review's
timeline/assessments, a cycle's requests, a JD's versions, a roadmap's progress
tiers, and the small template/integration libraries. Adding a row to one of these
means adding a child to a single parent, not scaling a tenant-wide list.

## How to add a new list endpoint

1. Add the FK derefs your serializer makes to `get_queryset` /the service that
   builds the queryset (`select_related` for forward FKs, `prefetch_related` for
   reverse/many).
2. Add a budget test to `test_query_budgets.py` following the existing pattern
   (seed at two row counts, assert `is_bounded`).
3. If the list scales with employee count, also cover it in `test_large_tenant.py`.
