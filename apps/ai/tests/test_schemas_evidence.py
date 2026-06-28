"""
Unit tests for the Phase-B AI-quality infrastructure: the upgraded schema
validator (``NonEmpty`` + nested dicts), the evidence builders (rich review
grounding, name-free succession summary) and the confidence/sufficiency blend.
"""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.ai.evidence import (
    confidence_with_sufficiency,
    review_evidence,
    succession_evidence,
)
from apps.ai.schemas import ListOf, NonEmpty, validate_shape
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    KpiMeasurementFactory,
)

pytestmark = pytest.mark.django_db


# ── validate_shape ───────────────────────────────────────────────────────────


def test_validate_shape_type_and_tuple():
    assert validate_shape({"a": "x"}, {"a": str}) == (True, [])
    ok, errors = validate_shape({"a": 1}, {"a": str})
    assert not ok and "must be str" in errors[0]
    assert validate_shape({"a": 1}, {"a": (str, int)})[0] is True


def test_validate_shape_missing_key():
    ok, errors = validate_shape({}, {"a": str})
    assert not ok and "missing key 'a'" in errors[0]


def test_nonempty_rejects_blank_and_short():
    ok, _ = validate_shape({"s": "   "}, {"s": NonEmpty()})
    assert not ok  # whitespace-only is blank
    ok, _ = validate_shape({"s": "hello"}, {"s": NonEmpty()})
    assert ok
    ok, _ = validate_shape({"s": "tiny"}, {"s": NonEmpty(20)})
    assert not ok  # below min_len
    ok, _ = validate_shape({"s": 123}, {"s": NonEmpty()})
    assert not ok  # not a string


def test_listof_requires_non_empty_list_of_matching_items():
    # Finding D: a required list with nothing in it is a hollow answer → fails.
    schema = {"items": ListOf(NonEmpty(1))}
    assert validate_shape({"items": ["a", "b"]}, schema) == (True, [])
    ok, errors = validate_shape({"items": []}, schema)
    assert not ok and "non-empty list" in errors[0]
    ok, errors = validate_shape({"items": "nope"}, schema)
    assert not ok and "non-empty list" in errors[0]  # not a list
    ok, errors = validate_shape({}, schema)
    assert not ok and "missing key 'items'" in errors[0]  # absent
    # Item-shape is enforced: objects where strings are expected fail.
    ok, errors = validate_shape({"items": [{"who": "x"}]}, schema)
    assert not ok and "items[0]" in errors[0]
    # Blank-string items fail too.
    ok, _ = validate_shape({"items": ["  "]}, schema)
    assert not ok


def test_nested_dict_schema():
    schema = {"sections": {"a": NonEmpty(3), "b": str}}
    assert validate_shape({"sections": {"a": "abc", "b": "x"}}, schema) == (True, [])
    ok, errors = validate_shape({"sections": {"a": "", "b": "x"}}, schema)
    assert not ok and "sections.a" in errors[0]
    ok, errors = validate_shape({"sections": {"b": "x"}}, schema)
    assert not ok and "missing key 'sections.a'" in errors[0]
    ok, errors = validate_shape({"sections": "nope"}, schema)
    assert not ok and "must be an object" in errors[0]


# ── confidence_with_sufficiency ──────────────────────────────────────────────


def test_confidence_blend_clamps_and_multiplies():
    assert confidence_with_sufficiency(0.88, 1.0) == pytest.approx(0.88)
    assert confidence_with_sufficiency(0.88, 0.5) == pytest.approx(0.44)
    assert confidence_with_sufficiency(2.0, 1.0) == 1.0  # clamp high
    assert confidence_with_sufficiency(None, 0.5) == pytest.approx(0.425)  # base default 0.85


# ── succession_evidence (name-free) ──────────────────────────────────────────


def test_succession_evidence_is_name_free_and_summarised():
    analysis = {
        "ranked_bench": [
            {"candidate_id": "x", "candidate_email": "a@acme.test", "readiness": "READY_NOW", "performance_band": "HIGH"},
            {"candidate_id": "y", "candidate_email": "b@acme.test", "readiness": "DEVELOPING", "performance_band": "MEDIUM"},
        ],
        "coverage_status": "AMBER",
        "red_flags": [{"code": "INADEQUATE_COVERAGE"}],
    }
    ev = succession_evidence(analysis)
    blob = str(ev)
    assert "a@acme.test" not in blob and "candidate_id" not in blob  # name-free
    assert ev["bench_size"] == 2
    assert ev["readiness_distribution"] == {"READY_NOW": 1, "DEVELOPING": 1}
    assert ev["coverage_status"] == "AMBER"
    assert ev["red_flag_codes"] == ["INADEQUATE_COVERAGE"]
    assert ev["evidence_sufficiency"] == 0.8  # 2 candidates


def test_succession_evidence_empty_bench_low_sufficiency():
    ev = succession_evidence({"ranked_bench": [], "coverage_status": "RED", "red_flags": []})
    assert ev["bench_size"] == 0 and ev["evidence_sufficiency"] == 0.35


# ── review_evidence (rich, DB-backed) ────────────────────────────────────────


def test_review_evidence_is_rich_and_grounded(org):
    with tenant_context(org.tenant):
        org.report.display_name = "Reza Kahn"
        org.report.save(update_fields=["display_name"])
        cycle = CycleFactory(tenant=org.tenant)
        goal = GoalFactory(employee=org.report, cycle=cycle, title="Ship the platform")
        kpi = KpiFactory(goal=goal, name="Throughput", target_value=Decimal("100.0000"), unit="%")
        KpiMeasurementFactory(kpi=kpi, value=Decimal("80.0000"), recorded_at=timezone.now())
        from apps.goals.models import CycleScore

        CycleScore.objects.create(
            tenant_id=org.tenant.id, employee=org.report, cycle=cycle,
            raw_score=Decimal("0.8"), z_score=Decimal("0.5"), t_score=Decimal("55.0"),
            cohort_size=10, risk_status="ON_TRACK", pace_behind=False,
            computed_at=timezone.now() - timedelta(minutes=1),
        )
        ev = review_evidence(SimpleNamespace(employee_id=org.report.id, cycle_id=cycle.id))

    assert ev["subject_name"] == "Reza"  # first name only
    assert ev["goals"][0]["title"] == "Ship the platform"
    kpi_ev = ev["goals"][0]["kpis"][0]
    assert kpi_ev["name"] == "Throughput"
    assert kpi_ev["target"] == "100" and kpi_ev["actual"] == "80"  # compact numbers
    assert kpi_ev["attainment_pct"] == 80
    assert ev["score"]["risk_status"] == "ON_TRACK" and ev["score"]["t_score"] == "55.0"
    assert ev["evidence_sufficiency"] == 1.0  # goals + measured KPI + score
