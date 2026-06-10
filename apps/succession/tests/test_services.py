"""
Succession services — readiness/9-box/coverage integration, the HITL plan flow,
the Agent-4 enrichment seam, manager-tier scoping, and tenant isolation.

Performance is read from Module-2 CycleScore; potential from the 9-box. Scope
violations (out-of-tier manager) raise 404, never 403.
"""
from decimal import Decimal

import pytest
from rest_framework.exceptions import NotFound

from apps.cycles.models import PerformanceCycle
from apps.goals.models import CycleScore
from apps.succession import constants as C
from apps.succession import engine, plans, services
from apps.succession.agent4 import (
    NotConfiguredProvider,
    SuccessionAnalyzerNotConfiguredError,
    get_provider,
)
from apps.succession.exceptions import IllegalPlanTransition
from apps.succession.models import BenchCandidate, CriticalRole, SuccessionPlan
from apps.succession.tasks import enrich_succession_with_agent4
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CriticalRoleFactory, CycleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _score(tenant, employee, cycle, t):
    """Create a CycleScore with T-score ``t`` for ``employee`` in ``cycle``."""
    from django.utils import timezone

    return CycleScore.objects.create(
        tenant_id=tenant.id,
        employee=employee,
        cycle=cycle,
        raw_score=Decimal("0"),
        z_score=Decimal("0"),
        t_score=Decimal(str(t)),
        cohort_size=10,
        computed_at=timezone.now(),
    )


def _ninebox(actor, employee, cycle, potential):
    return services.assess_nine_box(actor, employee, cycle, potential_band=potential)


# ── readiness from real CycleScores + 9-box ──────────────────────────────────


def test_high_high_candidate_is_ready_now_and_coverage_green(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, 70)          # HIGH performance
        _ninebox(org.hrbp, org.report, cycle, C.BAND_HIGH)  # HIGH potential
        role = CriticalRoleFactory(marked_by=org.hrbp)
        services.add_bench_candidate(org.hrbp, role, org.report)
        analysis = engine.compute_analysis(role)
    top = analysis["ranked_bench"][0]
    assert top["readiness"] == C.READY_NOW
    assert analysis["coverage_status"] == C.COVERAGE_GREEN
    assert analysis["red_flags"] == []


def test_no_score_candidate_is_not_ready_and_coverage_red(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        services.add_bench_candidate(org.hrbp, role, org.report)  # no CycleScore
        analysis = engine.compute_analysis(role)
    assert analysis["ranked_bench"][0]["readiness"] == C.NOT_READY
    assert analysis["coverage_status"] == C.COVERAGE_RED
    assert analysis["red_flags"][0]["code"] == "INADEQUATE_COVERAGE"


def test_only_ready_soon_is_amber(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, 70)            # HIGH
        _ninebox(org.hrbp, org.report, cycle, C.BAND_MEDIUM)  # HIGH+MED -> READY_SOON
        role = CriticalRoleFactory(marked_by=org.hrbp)
        services.add_bench_candidate(org.hrbp, role, org.report)
        analysis = engine.compute_analysis(role)
    assert analysis["coverage_status"] == C.COVERAGE_AMBER


def test_hrbp_override_persists_across_regenerate(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        bc = services.add_bench_candidate(org.hrbp, role, org.report)  # NOT_READY (no score)
        # HRBP overrides to READY_NOW — this must STICK.
        services.set_readiness(org.hrbp, bc, BenchCandidate.Readiness.READY_NOW)
        engine.compute_analysis(role)  # re-generate
        bc.refresh_from_db()
    assert bc.readiness == C.READY_NOW
    assert bc.readiness_overridden is True


# ── 9-box ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("t, band", [(39, C.BAND_LOW), (50, C.BAND_MEDIUM), (70, C.BAND_HIGH)])
def test_ninebox_performance_band_from_cyclescore(org, t, band):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, t)
        placement = _ninebox(org.hrbp, org.report, cycle, C.BAND_HIGH)
    assert placement.performance_band == band
    assert placement.box == engine.compute_box(band, C.BAND_HIGH)


def test_ninebox_is_unique_per_employee_cycle_upsert(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, 70)
        first = _ninebox(org.hrbp, org.report, cycle, C.BAND_LOW)
        second = _ninebox(org.hrbp, org.report, cycle, C.BAND_HIGH)  # re-assess upserts
        assert first.id == second.id
        assert second.potential_band == C.BAND_HIGH
        from apps.succession.models import NineBoxPlacement
        assert NineBoxPlacement.objects.filter(employee=org.report, cycle=cycle).count() == 1


# ── HITL plan flow ────────────────────────────────────────────────────────────


def test_generate_locks_pending_then_publish(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        services.add_bench_candidate(org.hrbp, role, org.report)
        plan = plans.generate_plan(org.hrbp, role)
        assert plan.status == SuccessionPlan.Status.PENDING_HUMAN_REVIEW
        assert plan.source == SuccessionPlan.Source.DETERMINISTIC
        plans.add_action_item(org.hrbp, plan, "Pair with incumbent for 2 cycles")
        plan = plans.publish_plan(org.hrbp, plan)
        assert plan.status == SuccessionPlan.Status.PUBLISHED
        assert plan.reviewed_by_id == org.hrbp.id and plan.published_at is not None
        assert plan.action_items[0]["text"].startswith("Pair")


def test_cannot_publish_without_review(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        # A DRAFT plan (never went through PENDING_HUMAN_REVIEW) cannot publish.
        draft = SuccessionPlan.objects.create(
            tenant_id=org.tenant.id, critical_role=role,
            status=SuccessionPlan.Status.DRAFT, coverage_status=C.COVERAGE_RED,
            generated_at=__import__("django.utils.timezone", fromlist=["now"]).now(),
        )
        with pytest.raises(IllegalPlanTransition):
            plans.publish_plan(org.hrbp, draft)


def test_cannot_publish_twice(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        plan = plans.generate_plan(org.hrbp, role)
        plans.publish_plan(org.hrbp, plan)
        with pytest.raises(IllegalPlanTransition):
            plans.publish_plan(org.hrbp, plan)


# ── Agent-4 enrichment seam ───────────────────────────────────────────────────


def test_default_provider_not_configured_raises():
    provider = get_provider()
    assert isinstance(provider, NotConfiguredProvider)
    assert provider.configured is False
    with pytest.raises(SuccessionAnalyzerNotConfiguredError):
        provider.analyze(critical_role=None, plan=None)


def test_enrich_with_no_provider_skips_and_leaves_plan_intact(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        services.add_bench_candidate(org.hrbp, role, org.report)
        plan = plans.generate_plan(org.hrbp, role)
    snapshot = (plan.status, plan.coverage_status, plan.source)
    result = enrich_succession_with_agent4(str(org.tenant.id), str(plan.id), str(org.hrbp.id))
    assert result == {"enriched": False, "reason": "no_provider"}
    plan.refresh_from_db()
    # The deterministic plan is COMPLETELY intact (core works without AI).
    assert (plan.status, plan.coverage_status, plan.source) == snapshot
    with tenant_context(org.tenant):
        assert SuccessionPlan.objects.filter(critical_role=role).count() == 1  # no AI plan added


# ── manager-tier scope (out-of-tier -> 404) ───────────────────────────────────


def test_manager_can_bench_own_report_but_not_a_peers_report(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        # org.manager's subtree = {report}; peer reports to hrbp (out of tier).
        services.add_bench_candidate(org.manager, role, org.report)  # OK
        with pytest.raises(NotFound):
            services.add_bench_candidate(org.manager, role, org.peer)


def test_manager_cannot_assess_ninebox_for_out_of_tier(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        with pytest.raises(NotFound):
            services.assess_nine_box(org.manager, org.peer, cycle, potential_band=C.BAND_HIGH)


def test_manager_dashboard_scoped_to_their_tier(org):
    with tenant_context(org.tenant):
        role_mine = CriticalRoleFactory(marked_by=org.hrbp, name="Mine")
        services.add_bench_candidate(org.hrbp, role_mine, org.report)   # report ∈ manager tier
        role_peer = CriticalRoleFactory(marked_by=org.hrbp, name="Peer")
        services.add_bench_candidate(org.hrbp, role_peer, org.peer)     # peer ∉ manager tier
        names = {r["name"] for r in plans.dashboard(org.manager)["critical_roles"]}
        all_names = {r["name"] for r in plans.dashboard(org.hrbp)["critical_roles"]}
    assert "Mine" in names and "Peer" not in names
    assert {"Mine", "Peer"} <= all_names


# ── isolation ─────────────────────────────────────────────────────────────────


def test_critical_role_is_tenant_scoped(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="HRBP", email="out@other.test")
    with tenant_context(other_tenant):
        CriticalRoleFactory(marked_by=outsider, name="Foreign")
    with tenant_context(org.tenant):
        assert CriticalRole.objects.count() == 0
