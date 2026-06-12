"""
Agent 1 — Review Assistant, exercised END-TO-END through the REAL Module-3 seam
task with the FakeLLMProvider: gather evidence → gateway (fake) → 5 sections →
structure → the state machine LOCKS the draft PENDING_HUMAN_REVIEW (HITL) + audits.
Confidence < 0.70 attaches a warning but STILL locks pending.
"""
import pytest
from django.test import override_settings

from apps.ai import providers
from apps.reviews.models import Review
from apps.reviews.tasks import draft_review_with_agent1
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory

pytestmark = pytest.mark.django_db

WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    REVIEW_ASSISTANT_PROVIDER="apps.ai.agents.review.ReviewAssistantProvider",
)


def _draft_review(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        return ReviewFactory(employee=org.report, cycle=cycle, state="DRAFT")


@override_settings(**WIRED)
def test_agent1_drafts_five_sections_and_locks_pending(org):
    review = _draft_review(org)
    result = draft_review_with_agent1(str(org.tenant.id), str(review.id), actor_id=str(org.manager.id))
    assert result["drafted"] is True
    with tenant_context(org.tenant):
        review.refresh_from_db()
    assert review.state == Review.State.PENDING_HUMAN_REVIEW  # HITL lock
    assert review.confidence_score is not None
    # The 5 sections are present in the structured draft body.
    for heading in ("Summary", "Strengths", "Areas For Development", "Goals Assessment", "Recommendations"):
        assert heading in review.draft_body


@override_settings(**WIRED)
def test_low_confidence_attaches_warning_but_still_locks_pending(org):
    providers.set_fake_confidence("agent1", 0.5)
    try:
        review = _draft_review(org)
        draft_review_with_agent1(str(org.tenant.id), str(review.id), actor_id=str(org.manager.id))
    finally:
        providers.set_fake_confidence("agent1", 0.9)
    with tenant_context(org.tenant):
        review.refresh_from_db()
    assert review.state == Review.State.PENDING_HUMAN_REVIEW  # still locked PENDING
    assert "LOW CONFIDENCE" in review.draft_body


def test_unconfigured_llm_leaves_review_unfabricated(org):
    # No LLM_PROVIDER (default NotConfigured) + the agent wired → the seam reports
    # no_provider and never fabricates a draft.
    with override_settings(REVIEW_ASSISTANT_PROVIDER="apps.ai.agents.review.ReviewAssistantProvider"):
        review = _draft_review(org)
        result = draft_review_with_agent1(str(org.tenant.id), str(review.id), actor_id=str(org.manager.id))
    assert result["drafted"] is False
    assert result["reason"] == "no_provider"
