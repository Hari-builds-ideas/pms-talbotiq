"""
The deterministic career engine — skill gap (from the employee's OWN CycleScore +
goals) and the advisory tiered roadmap. No AI; this is the always-available core.

THE DATA BOUNDARY is asserted structurally here: the gap is built ONLY from the
Module-8 performance-band math (CycleScore) + Module-2 goal attainment, and never
contains a potential band / readiness / bench field.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.career import constants as C
from apps.career import engine
from apps.goals.models import CycleScore
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    KpiMeasurementFactory,
)

pytestmark = pytest.mark.django_db


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


# ── skill gap: performance band → gap (reuses the Module-8 band math) ─────────


@pytest.mark.parametrize(
    "t, band, gap",
    [
        (70, C.BAND_HIGH, 0),     # already HIGH → no performance gap
        (60, C.BAND_MEDIUM, 1),   # 40..60 inclusive → MEDIUM → 1 band to climb
        (50, C.BAND_MEDIUM, 1),
        (39, C.BAND_LOW, 2),      # LOW → 2 bands to HIGH
    ],
)
def test_skill_gap_performance_band_from_cyclescore(org, t, band, gap):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, t)
        result = engine.compute_skill_gap(org.report.id)
    assert result["current_performance_band"] == band
    assert result["required_performance_band"] == C.BAND_HIGH
    assert result["performance_band_gap"] == gap


def test_skill_gap_unknown_when_no_score(org):
    with tenant_context(org.tenant):
        result = engine.compute_skill_gap(org.report.id)
    # No CycleScore → UNKNOWN → maximal, most conservative gap (to HIGH).
    assert result["current_performance_band"] == C.BAND_UNKNOWN
    assert result["performance_band_gap"] == 2
    assert result["weak_categories"] == []


def test_skill_gap_contains_no_succession_surface(org):
    """The headline boundary: the gap NEVER exposes a potential band / readiness /
    bench / coverage — those are the management-only succession surface."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, 55)
        result = engine.compute_skill_gap(org.report.id)
    keys = set(result)
    assert keys == {
        "current_performance_band",
        "required_performance_band",
        "performance_band_gap",
        "weak_categories",
    }
    forbidden = ("potential", "readiness", "bench", "coverage", "nine", "9box")
    blob = repr(result).lower()
    assert not any(token in blob for token in forbidden)


# ── weak goal categories: reuse the Module-2 per-goal attainment ──────────────


def test_weak_goal_categories_flags_underperforming_goals(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        _score(org.tenant, org.report, cycle, 50)  # establishes the latest cycle

        # A WEAK goal: actual 50 / target 100 → attainment 0.5 < 0.8.
        weak_goal = GoalFactory(employee=org.report, cycle=cycle, title="Sales", weight=Decimal("100.00"))
        weak_kpi = KpiFactory(goal=weak_goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
        KpiMeasurementFactory(kpi=weak_kpi, value=Decimal("50.0000"))

        # A STRONG goal: actual 100 / target 100 → attainment 1.0 (not weak).
        strong_goal = GoalFactory(employee=org.report, cycle=cycle, title="Quality", weight=Decimal("100.00"))
        strong_kpi = KpiFactory(goal=strong_goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
        KpiMeasurementFactory(kpi=strong_kpi, value=Decimal("100.0000"))

        weak = engine.weak_goal_categories(org.report.id)

    titles = {w["goal"] for w in weak}
    assert "Sales" in titles
    assert "Quality" not in titles


def test_weak_goal_categories_empty_without_a_scored_cycle(org):
    # No CycleScore at all → no "latest scored cycle" → no categories.
    with tenant_context(org.tenant):
        assert engine.weak_goal_categories(org.report.id) == []


# ── tier builder: deterministic structure, ordering, basis codes ──────────────


def _gap(band, band_gap, weak=None):
    return {
        "current_performance_band": band,
        "required_performance_band": C.BAND_HIGH,
        "performance_band_gap": band_gap,
        "weak_categories": weak or [],
    }


def test_tiers_for_high_performer_has_potential_and_stretch_only():
    tiers = engine.build_roadmap_tiers(_gap(C.BAND_HIGH, 0), target_label="Staff Eng (L5)")
    bases = [t["basis"] for t in tiers]
    assert bases == [C.BASIS_GROWTH, C.BASIS_STRETCH]
    # Indices are a stable 0-based sequence.
    assert [t["index"] for t in tiers] == [0, 1]


def test_tiers_for_low_performer_climbs_both_bands():
    tiers = engine.build_roadmap_tiers(_gap(C.BAND_LOW, 2), target_label="Lead")
    bases = [t["basis"] for t in tiers]
    assert bases == [
        C.BASIS_PERFORMANCE,   # reach MEDIUM
        C.BASIS_PERFORMANCE,   # reach HIGH
        C.BASIS_GROWTH,
        C.BASIS_STRETCH,
    ]


def test_tiers_for_unknown_starts_with_baseline():
    tiers = engine.build_roadmap_tiers(_gap(C.BAND_UNKNOWN, 2), target_label="Lead")
    # The very first tier establishes a measurable baseline.
    assert tiers[0]["basis"] == C.BASIS_PERFORMANCE
    assert "baseline" in tiers[0]["title"].lower()


def test_tiers_include_one_per_weak_category():
    weak = [
        {"goal": "Sales", "goal_id": "x", "raw_score": "0.5000"},
        {"goal": "Delivery", "goal_id": "y", "raw_score": "0.6000"},
    ]
    tiers = engine.build_roadmap_tiers(_gap(C.BAND_HIGH, 0, weak), target_label="Lead")
    kpi_tiers = [t for t in tiers if t["basis"] == C.BASIS_KPI_CATEGORY]
    assert len(kpi_tiers) == 2
    assert any("Sales" in t["title"] for t in kpi_tiers)
    # Determinism: same input → identical output.
    again = engine.build_roadmap_tiers(_gap(C.BAND_HIGH, 0, weak), target_label="Lead")
    assert tiers == again
