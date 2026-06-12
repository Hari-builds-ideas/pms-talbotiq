"""
Analytics services — the MIN-COHORT SUPPRESSION boundary (the headline safety
property), scope tiers, the calibration grid (reusing the 9-box), and cache
correctness + invalidation.
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.analytics import constants as C
from apps.analytics import services
from apps.goals.models import CycleScore
from apps.succession.models import NineBoxPlacement
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _score(tenant, employee, cycle, t):
    with tenant_context(tenant):
        return CycleScore.objects.create(
            tenant_id=tenant.id, employee=employee, cycle=cycle,
            raw_score=Decimal("0"), z_score=Decimal("0"), t_score=Decimal(str(t)),
            cohort_size=10, computed_at=timezone.now(),
        )


def _department(tenant, n, *, scored=True):
    """A manager head + ``n`` direct reports (each scored in a fresh cycle)."""
    head = UserFactory(tenant=tenant, role="MANAGER")
    cycle = CycleFactory(tenant=tenant, status="ACTIVE")
    reports = []
    for i in range(n):
        r = UserFactory(tenant=tenant, role="EMPLOYEE", manager=head)
        reports.append(r)
        if scored:
            _score(tenant, r, cycle, 45 + i * 3)
    return head, cycle, reports


# ── MIN-COHORT SUPPRESSION (the boundary at 5) ────────────────────────────────


def test_four_person_department_suppresses_individual_values(tenant):
    head, cycle, _ = _department(tenant, 4)
    result = services.department_analytics(head, head, cycle)
    assert result["cohort_size"] == 4
    assert result["suppressed"] is True
    # No individual values exposed for a sub-threshold cohort — aggregate only.
    assert result["individuals"] == []
    assert "note" in result
    # The aggregate (counts / mean) is still present (aggregate-only).
    assert result["aggregate"]["headcount"] == 4


def test_five_person_department_exposes_individuals(tenant):
    head, cycle, reports = _department(tenant, 5)
    result = services.department_analytics(head, head, cycle)
    assert result["cohort_size"] == 5
    assert result["suppressed"] is False
    assert len(result["individuals"]) == 5
    exposed = {row["employee"] for row in result["individuals"]}
    assert exposed == {str(r.id) for r in reports}


def test_min_cohort_threshold_is_five_and_distinct_from_feedback(tenant):
    from apps.feedback import constants as FC

    assert C.MIN_COHORT == 5
    # Deliberately a DIFFERENT, larger threshold than the 360 per-group min volume.
    assert FC.MIN_FEEDBACK_VOLUME == 3
    assert C.MIN_COHORT != FC.MIN_FEEDBACK_VOLUME


# ── individual analytics (own trend; scoped) ──────────────────────────────────


def test_individual_trend_returns_own_scores(tenant):
    head, cycle, reports = _department(tenant, 5)
    emp = reports[0]
    trend = services.individual_trend(emp, emp)  # employee viewing themselves
    assert trend["employee"] == str(emp.id)
    assert len(trend["trend"]) == 1
    assert trend["trend"][0]["cycle"] == str(cycle.id)


def test_individual_trend_out_of_scope_is_404(tenant):
    head, cycle, reports = _department(tenant, 5)
    # One employee cannot see another employee's trend.
    with pytest.raises(NotFound):
        services.individual_trend(reports[0], reports[1])


def test_manager_can_see_a_report_trend(tenant):
    head, cycle, reports = _department(tenant, 5)
    # A Manager→report scope check walks the reporting subtree (User.objects), so
    # it MUST run inside a bound tenant context (true on the request path via
    # middleware; wrapped here per scope.py's documented test convention).
    with tenant_context(tenant):
        trend = services.individual_trend(head, reports[0])  # manager → report: OK
    assert trend["employee"] == str(reports[0].id)


# ── department scope (out-of-scope head → 404) ────────────────────────────────


def test_department_out_of_scope_head_is_404(tenant):
    head, cycle, _ = _department(tenant, 5)
    other_mgr = UserFactory(tenant=tenant, role="MANAGER")  # not in head's line
    # other_mgr (a manager) cannot pull head's department (head not in their tier).
    with pytest.raises(NotFound):
        services.department_analytics(other_mgr, head, cycle)


def test_hrbp_can_pull_any_department(tenant):
    head, cycle, _ = _department(tenant, 5)
    hrbp = UserFactory(tenant=tenant, role="HRBP")
    result = services.department_analytics(hrbp, head, cycle)
    assert result["cohort_size"] == 5


# ── calibration grid (reuses the 9-box) ───────────────────────────────────────


def test_calibration_grid_counts_nine_box(tenant):
    hrbp = UserFactory(tenant=tenant, role="HRBP")
    cycle = CycleFactory(tenant=tenant, status="ACTIVE")
    with tenant_context(tenant):
        for box, (perf, pot) in {9: ("HIGH", "HIGH"), 5: ("MEDIUM", "MEDIUM")}.items():
            emp = UserFactory(tenant=tenant, role="EMPLOYEE")
            NineBoxPlacement.objects.create(
                tenant_id=tenant.id, employee=emp, cycle=cycle,
                performance_band=perf, potential_band=pot, box=box,
                assessed_by=hrbp, assessed_at=timezone.now(),
            )
    grid = services.calibration_grid(hrbp, cycle)
    assert grid["total"] == 2
    assert grid["grid"]["9"] == 1
    assert grid["grid"]["5"] == 1
    assert grid["grid"]["1"] == 0


# ── cache correctness + invalidation ──────────────────────────────────────────


def test_department_result_is_cached_then_invalidated(tenant):
    head, cycle, _ = _department(tenant, 5)
    first = services.department_analytics(head, head, cycle)
    assert first["cohort_size"] == 5

    # Add a 6th report. The CACHED result still reports 5 (served from cache).
    UserFactory(tenant=tenant, role="EMPLOYEE", manager=head)
    cached = services.department_analytics(head, head, cycle)
    assert cached["cohort_size"] == 5  # stale-by-design until invalidated

    # Invalidating the analytics namespace forces a fresh compute → 6.
    services.invalidate_analytics_cache(tenant)
    fresh = services.department_analytics(head, head, cycle)
    assert fresh["cohort_size"] == 6


def test_recompute_signal_invalidates_analytics_cache(tenant):
    head, cycle, _ = _department(tenant, 5)
    services.department_analytics(head, head, cycle)  # warm the cache
    UserFactory(tenant=tenant, role="EMPLOYEE", manager=head)
    # The Module-2 recompute signal receiver clears the tenant's analytics cache.
    services._on_cycle_scores_recomputed(sender=None, tenant_id=str(tenant.id))
    fresh = services.department_analytics(head, head, cycle)
    assert fresh["cohort_size"] == 6


# ── isolation ─────────────────────────────────────────────────────────────────


def test_department_is_tenant_isolated(tenant, other_tenant):
    head, cycle, _ = _department(tenant, 5)
    # A cross-tenant cycle id resolves to nothing for this tenant's head.
    other_cycle = CycleFactory(tenant=other_tenant, status="ACTIVE")
    result = services.department_analytics(head, head, other_cycle)
    # No scores for that (foreign) cycle → scored 0 (tenant-scoped read).
    assert result["aggregate"]["scored"] == 0
