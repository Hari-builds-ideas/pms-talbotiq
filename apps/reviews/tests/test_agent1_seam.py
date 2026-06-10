"""
Tests for the Agent-1 (Review Assistant) seam, :mod:`apps.reviews.agent1` and
its Celery entry point :mod:`apps.reviews.tasks`.

The seam is a real, loud contract — not a silent stub. These tests prove the
default raises/skips loudly (review untouched, still DRAFT), that a configured
provider's draft flows through the state machine and is LOCKED
PENDING_HUMAN_REVIEW, and that the manual path needs no AI at all.
"""
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.reviews import state_machine as sm
from apps.reviews.agent1 import (
    NotConfiguredProvider,
    ReviewAssistantNotConfiguredError,
    ReviewAssistantProvider,
    get_provider,
)
from apps.reviews.models import Review, ReviewStateTransition
from apps.reviews.tasks import draft_review_with_agent1
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory

pytestmark = pytest.mark.django_db

S = Review.State


class FakeProvider(ReviewAssistantProvider):
    """In-test concrete provider; module-level so it has an import path for
    the ``REVIEW_ASSISTANT_PROVIDER`` setting."""

    def draft(self, review) -> dict:
        return {
            "draft_body": "ai draft text",
            "confidence_score": Decimal("0.9100"),
            "citations": [{"source": "goal", "id": "x"}],
        }


FAKE_PROVIDER_PATH = f"{__name__}.FakeProvider"


@pytest.fixture
def review(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    return ReviewFactory(employee=org.report, cycle=cycle)


# ── the default provider is loud, not silent ───────────────────────────────


def test_not_configured_provider_draft_raises(review):
    with pytest.raises(ReviewAssistantNotConfiguredError):
        NotConfiguredProvider().draft(review)


def test_get_provider_defaults_to_not_configured():
    provider = get_provider()
    assert isinstance(provider, NotConfiguredProvider)
    assert provider.configured is False


@override_settings(REVIEW_ASSISTANT_PROVIDER=FAKE_PROVIDER_PATH)
def test_get_provider_resolves_configured_import_string():
    provider = get_provider()
    assert isinstance(provider, FakeProvider)
    assert provider.configured is True


# ── no provider: log-and-skip, review untouched, never crash ───────────────


def test_task_with_no_provider_skips_and_review_stays_draft(org, review):
    result = draft_review_with_agent1(
        str(org.tenant.id), str(review.id), actor_id=str(org.manager.id)
    )
    # Loud-but-safe: the no-provider summary, and the review untouched. (The
    # warning goes to logger "pms.reviews.agent1"; the reason is the robust
    # contract assertion, as in the Jira seam tests.)
    assert result == {"drafted": False, "reason": "no_provider"}
    review.refresh_from_db()
    assert review.state == S.DRAFT
    assert review.draft_body == ""
    assert review.source == Review.Source.MANUAL


# ── configured provider: the full HITL-gated draft flow ────────────────────


@override_settings(REVIEW_ASSISTANT_PROVIDER=FAKE_PROVIDER_PATH)
def test_task_with_configured_provider_locks_pending_human_review(org, review):
    result = draft_review_with_agent1(
        str(org.tenant.id), str(review.id), actor_id=str(org.manager.id)
    )
    assert result == {
        "drafted": True,
        "review_id": str(review.id),
        "state": S.PENDING_HUMAN_REVIEW,
    }
    review.refresh_from_db()
    assert review.state == S.PENDING_HUMAN_REVIEW  # LOCKED, never published
    assert review.source == Review.Source.AI
    assert review.draft_body == "ai draft text"
    assert review.confidence_score == Decimal("0.9100")
    assert review.citations == [{"source": "goal", "id": "x"}]
    # Timeline: the human-requested transition then the system lock.
    with tenant_context(org.tenant):
        rows = list(
            ReviewStateTransition.objects.filter(review=review).order_by("at", "created_at")
        )
    assert [(r.from_state, r.to_state) for r in rows] == [
        (S.DRAFT, S.AI_DRAFTING),
        (S.AI_DRAFTING, S.PENDING_HUMAN_REVIEW),
    ]
    assert rows[0].actor_id == org.manager.id  # accountable requester
    assert rows[1].actor_id is None  # system lock


@override_settings(REVIEW_ASSISTANT_PROVIDER=FAKE_PROVIDER_PATH)
def test_task_with_configured_provider_requires_an_actor(org, review):
    result = draft_review_with_agent1(str(org.tenant.id), str(review.id), actor_id=None)
    assert result == {"drafted": False, "reason": "actor_required"}
    review.refresh_from_db()
    assert review.state == S.DRAFT  # untouched


# ── unknown review ──────────────────────────────────────────────────────────


def test_task_with_unknown_review_returns_not_found(org):
    result = draft_review_with_agent1(
        str(org.tenant.id),
        "00000000-0000-0000-0000-000000000000",
        actor_id=str(org.manager.id),
    )
    assert result == {"drafted": False, "reason": "not_found"}


# ── the manual path needs no AI ─────────────────────────────────────────────


def test_manual_path_finalizes_with_provider_unconfigured(org, review):
    # The whole human flow works with no provider — the seam never blocks it.
    mgr = org.manager
    sm.start_edit(review, mgr)
    sm.submit_for_review(review, mgr, draft_body="written by a human")
    sm.approve(review, mgr)
    sm.finalize(review, mgr)
    assert review.state == S.FINALIZED
    assert review.source == Review.Source.MANUAL
    assert review.confidence_score is None and review.citations is None
