"""
Tests for the Agent-3 (Feedback Summarization) seam, :mod:`apps.feedback.agent3`
and its Celery entry point :mod:`apps.feedback.tasks`.

The seam is a real, loud contract — not a silent stub. These tests prove the
default raises/skips loudly (summary exists with sections NULL — theme text is
NEVER fabricated), that the deterministic gates (threshold, breach guard,
sensitive hold) run BEFORE any provider, that a breach means the provider is
never invoked, and that a configured provider's sections are saved verbatim
yet still locked behind human release.
"""
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.audit.models import AuditLog
from apps.feedback.agent3 import (
    FeedbackSummarizerNotConfiguredError,
    FeedbackSummarizerProvider,
    NotConfiguredProvider,
    get_provider,
)
from apps.feedback.models import FeedbackSummary
from apps.feedback.tasks import summarize_feedback
from apps.tenancy.context import get_current_tenant_id, tenant_context
from apps.testsupport.factories import FeedbackCycleFactory, FeedbackFactory, UserFactory

pytestmark = pytest.mark.django_db

S = FeedbackSummary.Status

SECTIONS = {
    "strengths": "Consistently unblocks the team.",
    "growth": "Could delegate more.",
    "themes": "Ownership and reliability.",
    "risks": "Workload concentration.",
}


class FakeProvider(FeedbackSummarizerProvider):
    """In-test concrete provider; module-level so it has an import path for
    the ``FEEDBACK_SUMMARIZER_PROVIDER`` setting."""

    def summarize(self, payload) -> dict:
        return {"sections": SECTIONS, "confidence_score": Decimal("0.8800")}


class ExplodingProvider(FeedbackSummarizerProvider):
    """A configured provider that must NEVER be reached — proves the breach
    path stops before any provider logic. Module-level call counter."""

    calls = 0

    def summarize(self, payload) -> dict:
        type(self).calls += 1
        raise AssertionError("Agent-3 provider must never run on an anonymity breach.")


FAKE_PROVIDER_PATH = f"{__name__}.FakeProvider"
EXPLODING_PROVIDER_PATH = f"{__name__}.ExplodingProvider"


def _populated_cycle(org, peers=3, sensitive_peer=False, leaky_body=None):
    """A COLLECTING cycle with SELF + MANAGER + N peers' 360 feedback."""
    cycle = FeedbackCycleFactory(subject=org.report)
    FeedbackFactory(cycle=cycle, giver=org.report, relationship="SELF", body="I grew a lot.")
    FeedbackFactory(cycle=cycle, giver=org.manager, relationship="MANAGER", body="Solid year.")
    for i in range(peers):
        peer = UserFactory(tenant=org.tenant, role="EMPLOYEE", email=f"peer{i}@acme.test")
        FeedbackFactory(
            cycle=cycle,
            giver=peer,
            relationship="PEER",
            body=leaky_body if (leaky_body and i == 0) else f"Peer note {i}.",
            giver_marked_sensitive=sensitive_peer and i == 0,
        )
    return cycle


def _run(org, cycle):
    return summarize_feedback(
        str(org.tenant.id), str(cycle.id), actor_id=str(org.manager.id)
    )


def _summary(org, cycle):
    with tenant_context(org.tenant):
        return FeedbackSummary.objects.get(cycle=cycle)


def _audit_actions(org, cycle):
    with tenant_context(org.tenant):
        return set(
            AuditLog.objects.filter(target_id=str(cycle.id)).values_list(
                "action", flat=True
            )
        )


# ── the default provider is loud, not silent ───────────────────────────────


def test_not_configured_provider_summarize_raises():
    with pytest.raises(FeedbackSummarizerNotConfiguredError):
        NotConfiguredProvider().summarize({})


def test_get_provider_defaults_to_not_configured():
    provider = get_provider()
    assert isinstance(provider, NotConfiguredProvider)
    assert provider.configured is False


@override_settings(FEEDBACK_SUMMARIZER_PROVIDER=FAKE_PROVIDER_PATH)
def test_get_provider_resolves_configured_import_string():
    provider = get_provider()
    assert isinstance(provider, FakeProvider)
    assert provider.configured is True


# ── no provider: deterministic summary exists, sections NEVER fabricated ───


def test_task_with_no_provider_writes_deterministic_summary(org):
    cycle = _populated_cycle(org, peers=3)
    result = _run(org, cycle)
    summary = _summary(org, cycle)
    assert result == {
        "summarized": False,
        "reason": "no_provider",
        "summary_id": str(summary.id),
        "status": S.PENDING_HUMAN_REVIEW,
    }
    assert summary.sections is None  # NEVER fabricated
    assert summary.status == S.PENDING_HUMAN_REVIEW
    assert summary.anonymity_passed is True
    assert summary.sensitive is False
    assert summary.volume_total == 5  # SELF + MANAGER + 3 PEER
    assert summary.insufficient_groups == []
    assert summary.insufficient_volume is False
    assert summary.confidence_score is None
    assert summary.generated_at is not None
    assert "summary.generated" in _audit_actions(org, cycle)


# ── threshold: a below-minimum PEER group is recorded, not a hold ───────────


def test_below_threshold_peer_group_marks_insufficient_volume(org):
    cycle = _populated_cycle(org, peers=1)
    result = _run(org, cycle)
    assert result["reason"] == "no_provider"
    summary = _summary(org, cycle)
    assert summary.insufficient_groups == ["PEER"]
    assert summary.insufficient_volume is True
    assert summary.status == S.PENDING_HUMAN_REVIEW  # partial path, no breach
    assert summary.anonymity_passed is True


# ── breach: HRBP_HOLD, audited, and the provider is NEVER invoked ───────────


@override_settings(FEEDBACK_SUMMARIZER_PROVIDER=EXPLODING_PROVIDER_PATH)
def test_anonymity_breach_holds_summary_and_never_calls_provider(org):
    ExplodingProvider.calls = 0
    cycle = _populated_cycle(
        org, peers=3, leaky_body=f"You should ask {org.peer.email} about this."
    )
    result = _run(org, cycle)
    summary = _summary(org, cycle)
    assert result == {
        "summarized": False,
        "reason": "anonymity_breach",
        "findings": 1,
        "summary_id": str(summary.id),
    }
    assert summary.status == S.HRBP_HOLD
    assert summary.anonymity_passed is False
    assert summary.sections is None
    assert "summary.held_for_hrbp" in _audit_actions(org, cycle)
    # The configured provider was never reached — the guard stops the pipeline.
    assert ExplodingProvider.calls == 0


# ── sensitive: clean anonymity but held before release (decision 7) ─────────


def test_sensitive_feedback_holds_summary_for_hrbp(org):
    cycle = _populated_cycle(org, peers=3, sensitive_peer=True)
    result = _run(org, cycle)
    assert result["reason"] == "no_provider"
    assert result["status"] == S.HRBP_HOLD
    summary = _summary(org, cycle)
    assert summary.sensitive is True
    assert summary.anonymity_passed is True  # no breach — held for sensitivity
    assert summary.status == S.HRBP_HOLD
    assert "summary.held_for_hrbp" in _audit_actions(org, cycle)


# ── configured provider: sections saved verbatim, still human-gated ─────────


@override_settings(FEEDBACK_SUMMARIZER_PROVIDER=FAKE_PROVIDER_PATH)
def test_task_with_configured_provider_saves_sections_still_pending(org):
    cycle = _populated_cycle(org, peers=3)
    result = _run(org, cycle)
    summary = _summary(org, cycle)
    assert result == {
        "summarized": True,
        "summary_id": str(summary.id),
        "status": S.PENDING_HUMAN_REVIEW,
    }
    assert summary.sections == SECTIONS  # verbatim
    assert summary.confidence_score == Decimal("0.8800")
    # Human release still required — the HITL discipline.
    assert summary.status == S.PENDING_HUMAN_REVIEW
    assert summary.released_at is None and summary.reviewed_by is None


# ── idempotent re-run: one summary row per cycle, refreshed in place ────────


def test_rerun_is_idempotent_one_summary_row(org):
    cycle = _populated_cycle(org, peers=3)
    first = _run(org, cycle)
    second = _run(org, cycle)
    assert first["summary_id"] == second["summary_id"]
    with tenant_context(org.tenant):
        assert FeedbackSummary.objects.filter(cycle=cycle).count() == 1


# ── unknown cycle ───────────────────────────────────────────────────────────


def test_task_with_unknown_cycle_returns_not_found(org):
    result = summarize_feedback(
        str(org.tenant.id),
        "00000000-0000-0000-0000-000000000000",
        actor_id=str(org.manager.id),
    )
    assert result == {"summarized": False, "reason": "not_found"}


# ── tenant binding: the task binds (and unbinds) its own tenant ─────────────


def test_task_binds_its_own_tenant_and_leaves_no_ambient_context(org):
    # Every test above already calls the task with NO ambient tenant context;
    # this one makes the discipline explicit: nothing is bound before or after.
    assert get_current_tenant_id() is None
    cycle = _populated_cycle(org, peers=3)
    _run(org, cycle)
    assert get_current_tenant_id() is None
