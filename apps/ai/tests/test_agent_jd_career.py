"""
JD Generator + Career Roadmap agents, exercised END-TO-END through their REAL
Module-6 / Module-9 seam tasks with the FakeLLMProvider. Both lock their AI output
behind a human gate (JD → PENDING_HUMAN_REVIEW; Career → a source=AI DRAFT for
acceptance); both stay 503 without an LLM provider.
"""
import pytest
from django.test import override_settings

from apps.career.models import DevelopmentRoadmap
from apps.career.services import select_target_role
from apps.career.tasks import generate_roadmap
from apps.jd import lifecycle
from apps.jd.models import JobDescription
from apps.jd.tasks import generate_jd
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import JobDescriptionFactory

pytestmark = pytest.mark.django_db

JD_WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    JD_GENERATOR_PROVIDER="apps.ai.agents.jd.JDGeneratorProvider",
)
CAREER_WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    CAREER_ROADMAP_PROVIDER="apps.ai.agents.career.CareerRoadmapProvider",
)


# ── JD Generator ────────────────────────────────────────────────────────────


@override_settings(**JD_WIRED)
def test_jd_generator_writes_body_and_locks_pending(org):
    with tenant_context(org.tenant):
        jd = lifecycle.create_jd(
            title="Analytics Engineer", level="L4", actor=org.hrbp, body={},
            inputs={"role_brief": "Owns dbt models."},
        )
    result = generate_jd(str(org.tenant.id), str(jd.id), str(org.hrbp.id))
    assert result["generated"] is True
    with tenant_context(org.tenant):
        jd.refresh_from_db()
        version = lifecycle.working_version(jd)
    assert jd.status == JobDescription.Status.PENDING_HUMAN_REVIEW  # HITL lock
    assert jd.source == JobDescription.Source.AI
    assert version.body["summary"]  # body written (not fabricated by Module 6)
    assert set(version.body) == {"summary", "responsibilities", "must_haves", "nice_to_haves"}


def test_jd_generator_unconfigured_leaves_draft(org):
    with override_settings(JD_GENERATOR_PROVIDER=JD_WIRED["JD_GENERATOR_PROVIDER"]):
        with tenant_context(org.tenant):
            jd = lifecycle.create_jd(
                title="X", level="L4", actor=org.hrbp, body={}, inputs={"role_brief": "y"}
            )
        result = generate_jd(str(org.tenant.id), str(jd.id), str(org.hrbp.id))
    assert result == {"generated": False, "reason": "no_provider"}


# ── Career Roadmap ──────────────────────────────────────────────────────────


@override_settings(**CAREER_WIRED)
def test_career_agent_creates_ai_draft_roadmap(org):
    with tenant_context(org.tenant):
        jd = JobDescriptionFactory(created_by=org.hrbp, status="PUBLISHED")
        select_target_role(org.report, org.report, target_jd=jd)  # deterministic baseline
    result = generate_roadmap(
        str(org.tenant.id), str(org.report.id), {"jd": str(jd.id)}, actor_id=str(org.report.id)
    )
    assert result["generated"] is True
    with tenant_context(org.tenant):
        ai = DevelopmentRoadmap.objects.filter(
            employee=org.report, source=DevelopmentRoadmap.Source.AI
        ).first()
    assert ai is not None
    assert ai.status == DevelopmentRoadmap.Status.DRAFT  # human accepts before ACTIVE
    assert ai.advisory is True  # NEVER auto-promotion (the M9 CHECK still holds)
    assert ai.tiers  # enriched tiers present


def test_career_agent_unconfigured_keeps_deterministic_only(org):
    with override_settings(CAREER_ROADMAP_PROVIDER=CAREER_WIRED["CAREER_ROADMAP_PROVIDER"]):
        with tenant_context(org.tenant):
            jd = JobDescriptionFactory(created_by=org.hrbp, status="PUBLISHED")
            select_target_role(org.report, org.report, target_jd=jd)
        result = generate_roadmap(
            str(org.tenant.id), str(org.report.id), {"jd": str(jd.id)}, actor_id=str(org.report.id)
        )
    assert result == {"generated": False, "reason": "no_provider"}
    with tenant_context(org.tenant):
        assert not DevelopmentRoadmap.objects.filter(
            employee=org.report, source=DevelopmentRoadmap.Source.AI
        ).exists()
