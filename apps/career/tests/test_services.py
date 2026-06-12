"""
Career services — target selection + deterministic generation, scope (employee
own / manager team / HRBP tenant; out-of-scope → 404), the DATA BOUNDARY (career
never surfaces the succession surface), progress, the advisory DB guarantee, the
agent seam (503 / deterministic-intact), tenant isolation + off-request binding.
"""
import json
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.career import services
from apps.career.exceptions import InvalidCareerInput
from apps.career.models import DevelopmentRoadmap, RoadmapProgress, TargetRoleSelection
from apps.career.roadmap_agent import (
    CareerRoadmapNotConfiguredError,
    NotConfiguredProvider,
    get_provider,
)
from apps.career.tasks import generate_roadmap
from apps.goals.models import CycleScore
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    BenchCandidateFactory,
    CriticalRoleFactory,
    CycleFactory,
    JobDescriptionFactory,
    NineBoxPlacementFactory,
    PositionFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _published_jd(org):
    with tenant_context(org.tenant):
        return JobDescriptionFactory(created_by=org.hrbp, status="PUBLISHED")


def _score(tenant, employee, cycle, t):
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


# ── select target + deterministic generation ──────────────────────────────────


def test_employee_selects_own_target_creates_advisory_roadmap(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        selection, roadmap = services.select_target_role(org.report, org.report, target_jd=jd)
    assert isinstance(selection, TargetRoleSelection)
    assert roadmap.source == DevelopmentRoadmap.Source.DETERMINISTIC
    assert roadmap.status == DevelopmentRoadmap.Status.ACTIVE
    assert roadmap.advisory is True
    assert roadmap.tiers  # non-empty advisory path
    assert "performance_band_gap" in roadmap.skill_gap


def test_target_against_a_position_profile(org):
    with tenant_context(org.tenant):
        pos = PositionFactory(reports_to=org.manager)
        _, roadmap = services.select_target_role(org.report, org.report, target_position=pos)
    assert roadmap.target_position_id == pos.id
    assert roadmap.target_jd_id is None


def test_target_must_be_exactly_one(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        pos = PositionFactory(reports_to=org.manager)
        with pytest.raises(InvalidCareerInput):
            services.select_target_role(org.report, org.report, target_jd=jd, target_position=pos)
        with pytest.raises(InvalidCareerInput):
            services.select_target_role(org.report, org.report)


def test_target_jd_must_be_published(org):
    with tenant_context(org.tenant):
        draft_jd = JobDescriptionFactory(created_by=org.hrbp, status="DRAFT")
        with pytest.raises(InvalidCareerInput):
            services.select_target_role(org.report, org.report, target_jd=draft_jd)


def test_reselecting_same_target_refreshes_in_place(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        _, first = services.select_target_role(org.report, org.report, target_jd=jd)
        _, second = services.select_target_role(org.report, org.report, target_jd=jd)
        # One ACTIVE deterministic roadmap per (employee, target) — code-enforced.
        assert first.id == second.id
        assert (
            DevelopmentRoadmap.objects.filter(
                employee=org.report, target_jd=jd, status=DevelopmentRoadmap.Status.ACTIVE
            ).count()
            == 1
        )


# ── THE DATA BOUNDARY ──────────────────────────────────────────────────────────


def test_roadmap_never_surfaces_succession_data(org):
    """Even when the employee has bench/9-box/critical-role rows, their career
    roadmap exposes NONE of it — only their own performance-derived gap + tiers."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, 55)
        # Seed the sensitive succession surface for this very employee.
        role = CriticalRoleFactory(marked_by=org.hrbp, incumbent=org.manager)
        BenchCandidateFactory(critical_role=role, candidate=org.report, readiness="READY_NOW")
        NineBoxPlacementFactory(employee=org.report, cycle=cycle, potential_band="HIGH")

        _, roadmap = services.select_target_role(org.report, org.report, target_jd=jd)

    blob = json.dumps({"tiers": roadmap.tiers, "skill_gap": roadmap.skill_gap}).lower()
    for token in ("readiness", "potential", "bench", "coverage", "nine_box", "ninebox", "9box", "critical_role"):
        assert token not in blob, f"leaked succession token: {token}"
    # And no OTHER employee's id appears in the roadmap payload.
    assert str(org.peer.id) not in blob
    assert str(org.manager.id) not in blob


# ── scope (out-of-scope → 404; employee-visible, unlike succession) ───────────


def test_employee_cannot_select_for_a_peer(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        with pytest.raises(NotFound):
            services.select_target_role(org.report, org.peer, target_jd=jd)


def test_manager_can_select_for_report_but_not_peer(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        # org.report is in the manager's subtree; org.peer reports to hrbp (out).
        services.select_target_role(org.manager, org.report, target_jd=jd)
        with pytest.raises(NotFound):
            services.select_target_role(org.manager, org.peer, target_jd=jd)


def test_hrbp_sees_tenant_and_employee_only_self(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        # HRBP (TENANT) can generate for anyone.
        services.select_target_role(org.hrbp, org.report, target_jd=jd)
        services.select_target_role(org.hrbp, org.peer, target_jd=jd)
        # Employee scope list = own only.
        assert {r.employee_id for r in services.list_roadmaps(org.report)} == {org.report.id}
        # Manager scope list = subtree + self.
        mgr_ids = {r.employee_id for r in services.list_roadmaps(org.manager)}
        assert org.report.id in mgr_ids
        assert org.peer.id not in mgr_ids


def test_get_roadmap_out_of_scope_is_404(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        _, roadmap = services.select_target_role(org.peer, org.peer, target_jd=jd)
        # org.report (an employee) cannot see org.peer's roadmap.
        with pytest.raises(NotFound):
            services.get_roadmap_in_scope(org.report, roadmap.id)


def test_cross_tenant_is_404(org, other_tenant):
    jd = _published_jd(org)
    outsider = UserFactory(tenant=other_tenant, role="HRBP", email="out@other.test")
    with tenant_context(org.tenant):
        _, roadmap = services.select_target_role(org.report, org.report, target_jd=jd)
    with tenant_context(other_tenant):
        with pytest.raises(NotFound):
            services.get_roadmap_in_scope(outsider, roadmap.id)


# ── regenerate refreshes from current data ─────────────────────────────────────


def test_regenerate_recomputes_tiers_after_data_change(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        _, roadmap = services.select_target_role(org.report, org.report, target_jd=jd)
        gap_before = roadmap.skill_gap["performance_band_gap"]  # no score → 2
        _score(org.tenant, org.report, cycle, 70)  # now HIGH
        refreshed = services.regenerate_roadmap(org.report, roadmap)
    assert gap_before == 2
    assert refreshed.skill_gap["performance_band_gap"] == 0
    assert refreshed.id == roadmap.id  # refreshed in place


# ── progress ────────────────────────────────────────────────────────────────────


def test_progress_upsert_and_out_of_range(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        _, roadmap = services.select_target_role(org.report, org.report, target_jd=jd)
        p1 = services.set_progress(org.report, roadmap, tier_index=0, status="IN_PROGRESS")
        p2 = services.set_progress(org.report, roadmap, tier_index=0, status="DONE")
        assert p1.id == p2.id  # upsert, not duplicate
        assert RoadmapProgress.objects.filter(roadmap=roadmap, tier_index=0).count() == 1
        assert p2.status == "DONE"
        with pytest.raises(InvalidCareerInput):
            services.set_progress(org.report, roadmap, tier_index=999, status="DONE")


# ── advisory is a STRUCTURAL guarantee (never auto-promotion) ──────────────────


def test_advisory_false_is_rejected_by_the_database(org):
    """The CHECK constraint ck_roadmap_advisory_always_true makes a non-advisory
    roadmap impossible at the DB layer — career can never become auto-promotion."""
    with tenant_context(org.tenant):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DevelopmentRoadmap.objects.create(
                    tenant_id=org.tenant.id,
                    employee=org.report,
                    status=DevelopmentRoadmap.Status.ACTIVE,
                    tiers=[],
                    skill_gap={},
                    source=DevelopmentRoadmap.Source.DETERMINISTIC,
                    advisory=False,  # ← rejected by the CHECK constraint
                    generated_at=timezone.now(),
                )


# ── the agent seam (Module 10) ──────────────────────────────────────────────────


def test_default_provider_not_configured_raises():
    provider = get_provider()
    assert isinstance(provider, NotConfiguredProvider)
    assert provider.configured is False
    with pytest.raises(CareerRoadmapNotConfiguredError):
        provider.draft(employee_id=None, target_label="x", gap={}, baseline_tiers=[])


def test_enrich_with_no_provider_leaves_deterministic_intact(org):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        _, roadmap = services.select_target_role(org.report, org.report, target_jd=jd)
    snapshot = (roadmap.status, roadmap.source, len(roadmap.tiers))
    # Off-request: pass the tenant id as a STRING (the task binds the tenant).
    result = generate_roadmap(
        str(org.tenant.id), str(org.report.id), {"jd": str(jd.id)}, actor_id=str(org.report.id)
    )
    assert result == {"generated": False, "reason": "no_provider"}
    roadmap.refresh_from_db()
    assert (roadmap.status, roadmap.source, len(roadmap.tiers)) == snapshot
    with tenant_context(org.tenant):
        # No AI roadmap was created — the deterministic baseline is the only row.
        assert not DevelopmentRoadmap.objects.filter(
            employee=org.report, source=DevelopmentRoadmap.Source.AI
        ).exists()


# ── isolation ─────────────────────────────────────────────────────────────────


def test_roadmap_is_tenant_scoped(org, other_tenant):
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        services.select_target_role(org.report, org.report, target_jd=jd)
    with tenant_context(other_tenant):
        assert DevelopmentRoadmap.objects.count() == 0
