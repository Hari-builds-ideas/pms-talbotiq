# PROGRESS.md — production-hardening build series (BUILD_1…5)

> Append-only log. Verification honesty: **[test]** asserted by a test ·
> **[live]** exercised over real HTTP · **[build]** build/typecheck/lint only.

## Current: BUILD_1 — ORM & queries · Phase 1.2 (N+1 elimination)

Baseline (start of series): backend suite **1065 passing** (grew from the
contract's stated 1059 via the names + display work). Stack runs as one Docker
compose (`web`, `mysql`, `redis`, `celery-worker`, `celery-beat`, `flower`,
`frontend`).

---

## N+1 baseline (Phase 1.1, recorded run · query count at 5 vs 25 list rows)

| endpoint | path | 5 rows | 25 rows | Δ | verdict |
|---|---|---|---|---|---|
| reviews | `/api/reviews/` | 18 | 78 | 60 | N+1 (~3/row) |
| goals | `/api/goals/` | 23 | 103 | 80 | N+1 (~4/row) |
| org-positions | `/api/org/positions` | 13 | 53 | 40 | N+1 (~2/row) |
| feedback-cycles | `/api/feedback/cycles` | 8 | 28 | 20 | N+1 (~1/row) |
| jd-library | `/api/jd/` | 8 | 28 | 20 | N+1 (~1/row) |
| career-roadmaps | `/api/career/roadmaps` | 8 | 28 | 20 | N+1 (~1/row) |
| succession-bench | `/api/succession/critical-roles/{id}/bench` | 3 | 3 | 0 | already BOUNDED |

Cause: the `*_name`/`*_title` SerializerMethodFields added in the UUID→name fix
deref person/entity FKs per row on lists that lacked `select_related`. Phase 1.2
fixes each view's `get_queryset` and flips `ENFORCE_BOUNDED=True`.

---

## Log

(ordinal · build/phase · what · files · verification · commit)

1 · BUILD_1/1.1 · query-count harness + N+1 baseline · `apps/testsupport/query_budget.py` (count_queries/ScalingResult/measure_scaling, additive seeding), `apps/core/tests/test_query_budgets.py` (7 endpoint budget tests, recording mode) · **[test]** 7 passed; baseline table above · commit `BUILD_1 1.1`
