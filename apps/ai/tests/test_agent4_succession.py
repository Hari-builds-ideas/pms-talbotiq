"""
Agent 4 — Successor Planning, exercised END-TO-END through the REAL Module-8
``enrich_succession_with_agent4`` task with the FakeLLMProvider: enrich the
deterministic analysis into a NEW source=AI plan PENDING_HUMAN_REVIEW, leaving the
deterministic plan COMPLETELY INTACT (and never pulling raw 360).
"""
import pytest
from django.test import override_settings

from apps.succession import plans, services
from apps.succession.models import SuccessionPlan
from apps.succession.tasks import enrich_succession_with_agent4
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CriticalRoleFactory

pytestmark = pytest.mark.django_db

WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    SUCCESSION_ANALYZER_PROVIDER="apps.ai.agents.succession.SuccessionAnalyzerProvider",
)


def _role_with_plan(org):
    with tenant_context(org.tenant):
        role = CriticalRoleFactory(marked_by=org.hrbp)
        services.add_bench_candidate(org.hrbp, role, org.report)
        plan = plans.generate_plan(org.hrbp, role)
    return role, plan


@override_settings(**WIRED)
def test_agent4_creates_ai_plan_leaving_deterministic_intact(org):
    role, det_plan = _role_with_plan(org)
    snapshot = (det_plan.status, det_plan.source, det_plan.coverage_status)
    result = enrich_succession_with_agent4(str(org.tenant.id), str(det_plan.id), actor_id=str(org.hrbp.id))
    assert result["enriched"] is True
    with tenant_context(org.tenant):
        det_plan.refresh_from_db()
        ai_plans = list(SuccessionPlan.objects.filter(critical_role=role, source=SuccessionPlan.Source.AI))
    # The deterministic plan is COMPLETELY intact.
    assert (det_plan.status, det_plan.source, det_plan.coverage_status) == snapshot
    # A NEW AI plan was created, locked PENDING_HUMAN_REVIEW, with a confidence.
    assert len(ai_plans) == 1
    ai = ai_plans[0]
    assert ai.status == SuccessionPlan.Status.PENDING_HUMAN_REVIEW
    assert ai.confidence_score is not None
    assert any(f.get("code") == "AI_NARRATIVE" for f in ai.red_flags)


def test_unconfigured_llm_leaves_deterministic_plan_intact(org):
    role, det_plan = _role_with_plan(org)
    with override_settings(SUCCESSION_ANALYZER_PROVIDER=WIRED["SUCCESSION_ANALYZER_PROVIDER"]):
        result = enrich_succession_with_agent4(str(org.tenant.id), str(det_plan.id), actor_id=str(org.hrbp.id))
    assert result == {"enriched": False, "reason": "no_provider"}
    with tenant_context(org.tenant):
        assert not SuccessionPlan.objects.filter(critical_role=role, source=SuccessionPlan.Source.AI).exists()
