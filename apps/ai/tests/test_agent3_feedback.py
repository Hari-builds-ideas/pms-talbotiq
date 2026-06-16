"""
Agent 3 — Feedback Summarization, exercised END-TO-END through the REAL Module-4
``summarize_feedback`` task with the FakeLLMProvider. The deterministic Module-4
gates (threshold / pre-LLM email guard / sensitive) still run first; a CONFIGURED
agent writes the 4 sections (still HITL-gated). The POST-LLM breach check is
load-bearing: a free-text leak in the GENERATED sections (which the pre-LLM
email-only guard on the source bodies cannot catch) → HRBP_HOLD.
"""
import pytest
from django.test import override_settings

from apps.ai.agents import feedback as agent3
from apps.ai.providers import register_fake_output
from apps.feedback.models import FeedbackSummary
from apps.feedback.tasks import summarize_feedback
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import FeedbackCycleFactory, FeedbackFactory, UserFactory

pytestmark = pytest.mark.django_db
S = FeedbackSummary.Status

WIRED = dict(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    FEEDBACK_SUMMARIZER_PROVIDER="apps.ai.agents.feedback.FeedbackSummarizerProvider",
)


def _clean_cycle(org, peers=3):
    cycle = FeedbackCycleFactory(subject=org.report)
    FeedbackFactory(cycle=cycle, giver=org.report, relationship="SELF", body="I grew.")
    FeedbackFactory(cycle=cycle, giver=org.manager, relationship="MANAGER", body="Solid.")
    for i in range(peers):
        peer = UserFactory(tenant=org.tenant, role="EMPLOYEE", email=f"p{i}@acme.test")
        FeedbackFactory(cycle=cycle, giver=peer, relationship="PEER", body=f"Peer note {i}.")
    return cycle


def _summary(org, cycle):
    with tenant_context(org.tenant):
        return FeedbackSummary.objects.get(cycle=cycle)


@override_settings(**WIRED)
def test_agent3_writes_four_sections_still_pending(org):
    cycle = _clean_cycle(org)
    result = summarize_feedback(str(org.tenant.id), str(cycle.id), actor_id=str(org.manager.id))
    assert result["summarized"] is True
    summary = _summary(org, cycle)
    assert set(summary.sections) == {"strengths", "growth", "themes", "risks"}
    assert summary.status == S.PENDING_HUMAN_REVIEW  # still human-gated (HITL)
    assert summary.confidence_score is not None


@override_settings(**WIRED)
def test_post_llm_breach_holds_for_hrbp(org):
    # Source bodies are CLEAN (the pre-LLM email guard passes), but the LLM output
    # leaks an email in a section → the POST-LLM check holds for an HRBP.
    def _leaky(prompt, model):
        # Sections are realistic length (the schema's non-blank quality floor),
        # but one leaks an email → the POST-LLM breach check must catch it.
        return {"sections": {
            "strengths": "Great work — ask leaked@acme.test for the detail.",
            "growth": "Could communicate trade-offs earlier in the cycle.",
            "themes": "Reliable, collaborative and pragmatic under pressure.",
            "risks": "Some bottlenecking on reviews during crunch periods.",
        }}

    register_fake_output("agent3", _leaky)
    try:
        cycle = _clean_cycle(org)
        result = summarize_feedback(str(org.tenant.id), str(cycle.id), actor_id=str(org.manager.id))
    finally:
        register_fake_output("agent3", agent3._fake)  # restore the clean fake

    assert result["summarized"] is True
    summary = _summary(org, cycle)
    assert summary.status == S.HRBP_HOLD
    assert summary.anonymity_passed is False


def test_unconfigured_llm_leaves_sections_null(org):
    with override_settings(FEEDBACK_SUMMARIZER_PROVIDER=WIRED["FEEDBACK_SUMMARIZER_PROVIDER"]):
        cycle = _clean_cycle(org)
        result = summarize_feedback(str(org.tenant.id), str(cycle.id), actor_id=str(org.manager.id))
    assert result["summarized"] is False and result["reason"] == "no_provider"
    assert _summary(org, cycle).sections is None  # never fabricated
