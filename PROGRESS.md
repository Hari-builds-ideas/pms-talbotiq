# PROGRESS.md — production-hardening build series (BUILD_1…5)

> Append-only log. Verification honesty: **[test]** asserted by a test ·
> **[live]** exercised over real HTTP · **[build]** build/typecheck/lint only.

## Current: BUILD_1 — ORM & queries · Phase 1.4 (pagination + large-tenant correctness)

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

3 · BUILD_1/1.3 · ORM optimization + targeted indexes · `apps/reviews/models.py` (+ix_review_tenant_recent `(tenant,-created_at)`), `apps/goals/models.py` (+ix_goal_emp_recent `(tenant,employee,-created_at)`), 2 migrations (`reviews/0003`, `goals/0002`), `apps/org/services.py` (person_card select_related manager) · **[test]** migrations apply+reverse clean, DDL verified (`created_at DESC`); 239 affected-suite tests pass; full suite (see next) · aggregation audit: analytics/calibration left in Python (no-win, documented D2) · commit `BUILD_1 1.3`

2 · BUILD_1/1.2 · eliminate the name/title N+1 at the queryset level · `apps/reviews/views.py` (list + calibration: select_related employee/reviewer/human_reviewer/cycle), `apps/goals/views.py` (select_related employee/created_by/approved_by + prefetch kpis), `apps/org/views.py` (select_related filled_by/reports_to/published_jd), `apps/feedback/views.py` (select_related subject only — givers never serialized), `apps/jd/services.py` (search_jds → select_related created_by), `apps/career/services.py` (list_roadmaps → select_related employee/target_jd/target_position), `apps/core/tests/test_query_budgets.py` (ENFORCE_BOUNDED=True) · **[test]** budget Δ→0 on all 7 (reviews 78→3, goals 103→4, positions 53→3, feedback/jd/career 28→3); 6 affected app suites 354 passed; giver-anonymity unchanged (cycle serializer carries no giver field; existing `test_api.py:116/130/135` still green) · commit `BUILD_1 1.2`
