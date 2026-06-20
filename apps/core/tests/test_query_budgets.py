"""
Query-budget tests (BUILD_1) — the N+1 regression guard.

Each test seeds a LIST endpoint at two row counts and asserts the query count is
BOUNDED (does not scale with rows). An N+1 (the signature the names/`*_name`
serializer work risked) makes ``Δqueries ≈ rows``; a healthy endpoint adds a
small constant. The asserted ceilings live in ``docs/QUERY_BUDGETS.md``.

Phase 1.1 RECORDS the baseline (printed by each test, captured in PROGRESS.md);
the recording run showed 6 of 7 list endpoints N+1. Phase 1.2 adds the
`select_related`/`prefetch_related` that make these bounded and flips the
module-level ``ENFORCE_BOUNDED`` to True, so a future regression FAILS the suite.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    BenchCandidateFactory,
    CriticalRoleFactory,
    CycleFactory,
    DevelopmentRoadmapFactory,
    FeedbackCycleFactory,
    GoalFactory,
    JobDescriptionFactory,
    PositionFactory,
    ReviewFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SMALL, LARGE = 5, 25

# Flipped to True in Phase 1.2 once the views carry their select/prefetch fixes.
# In 1.1 the module only RECORDS the baseline (a failing assert would block the
# green baseline commit the contract requires).
ENFORCE_BOUNDED = False


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _emp(org):
    """A fresh employee under the org's manager (so it's in HRBP + manager scope)."""
    return UserFactory(tenant=org.tenant, role="EMPLOYEE", manager=org.manager)


def _measure(org, *, seed, path, capsys, label):
    """Seed SMALL then LARGE rows, measuring the endpoint's query count each time."""
    from apps.testsupport.query_budget import measure_scaling

    client = _client(org.hrbp)  # HRBP = tenant scope, sees every row

    def request():
        resp = client.get(path)
        assert resp.status_code == 200, resp.content
        return resp

    with tenant_context(org.tenant):
        result = measure_scaling(seed=seed, request=request, small=SMALL, large=LARGE)
    with capsys.disabled():
        print(f"\n[query-budget] {label}: {result}")
    if ENFORCE_BOUNDED:
        assert result.is_bounded, f"{label} N+1: {result}"
    return result


def test_reviews_list_bounded(org, capsys):
    cycle = CycleFactory(tenant=org.tenant)

    def seed(n):
        for _ in range(n):
            ReviewFactory(employee=_emp(org), cycle=cycle)

    _measure(org, seed=seed, path="/api/reviews/?page_size=100", capsys=capsys, label="reviews")


def test_feedback_cycles_list_bounded(org, capsys):
    def seed(n):
        for _ in range(n):
            FeedbackCycleFactory(subject=_emp(org))

    _measure(org, seed=seed, path="/api/feedback/cycles?page_size=100", capsys=capsys, label="feedback-cycles")


def test_goals_list_bounded(org, capsys):
    cycle = CycleFactory(tenant=org.tenant)

    def seed(n):
        for _ in range(n):
            GoalFactory(employee=_emp(org), cycle=cycle)

    _measure(org, seed=seed, path="/api/goals/?page_size=100", capsys=capsys, label="goals")


def test_org_positions_list_bounded(org, capsys):
    def seed(n):
        for _ in range(n):
            PositionFactory(reports_to=org.manager, filled_by=_emp(org))

    _measure(org, seed=seed, path="/api/org/positions?page_size=100", capsys=capsys, label="org-positions")


def test_jd_library_list_bounded(org, capsys):
    def seed(n):
        for _ in range(n):
            JobDescriptionFactory(created_by=org.hrbp)

    _measure(org, seed=seed, path="/api/jd/?page_size=100", capsys=capsys, label="jd-library")


def test_career_roadmaps_list_bounded(org, capsys):
    def seed(n):
        for _ in range(n):
            DevelopmentRoadmapFactory(employee=_emp(org))

    _measure(org, seed=seed, path="/api/career/roadmaps?page_size=100", capsys=capsys, label="career-roadmaps")


def test_succession_bench_list_bounded(org, capsys):
    role = CriticalRoleFactory(marked_by=org.hrbp, incumbent=org.manager)

    def seed(n):
        for _ in range(n):
            BenchCandidateFactory(critical_role=role, candidate=_emp(org))

    _measure(
        org,
        seed=seed,
        path=f"/api/succession/critical-roles/{role.id}/bench?page_size=100",
        capsys=capsys,
        label="succession-bench",
    )
