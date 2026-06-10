"""
THE HITL GATE — enforced in depth, proven at every layer.

Layer 1: the state machine refuses finalize without an approval (422).
Layer 2: the DATABASE refuses state=FINALIZED with a null human_reviewer via the
         ck_review_finalized_has_reviewer CHECK constraint — even on a direct
         ORM write that bypasses the state machine entirely (the same standard
         Module 1 set by proving the audit triggers against raw SQL).
Layer 3: the API returns 422 HITL_APPROVAL_REQUIRED (covered in test_api.py).
"""
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.reviews import state_machine as sm
from apps.reviews.exceptions import HITLApprovalRequired
from apps.reviews.models import Review
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory

pytestmark = pytest.mark.django_db

S = Review.State


@pytest.fixture
def review(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    return ReviewFactory(employee=org.report, cycle=cycle)


def _to_pending(review, actor):
    sm.start_edit(review, actor)
    sm.submit_for_review(review, actor, draft_body="draft")
    return review


# ── layer 1: the state machine ─────────────────────────────────────────────


def test_finalize_without_approval_is_422_hitl(org, review):
    _to_pending(review, org.manager)
    with pytest.raises(HITLApprovalRequired) as exc:
        sm.finalize(review, org.manager)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "HITL_APPROVAL_REQUIRED"
    review.refresh_from_db()
    assert review.state == S.PENDING_HUMAN_REVIEW
    assert review.human_reviewer_id is None


def test_approve_then_finalize_succeeds(org, review):
    _to_pending(review, org.manager)
    sm.approve(review, org.manager)
    assert review.human_reviewer_id == org.manager.id
    sm.finalize(review, org.manager)
    assert review.state == S.FINALIZED


def test_finalize_guard_checks_reviewer_not_only_state(org, review):
    # Belt-and-braces: even if state were forced to APPROVED with no reviewer
    # (bypassing approve()), the machine still refuses to finalize.
    _to_pending(review, org.manager)
    with tenant_context(org.tenant):
        Review.objects.filter(id=review.id).update(state=S.APPROVED, human_reviewer=None)
    review.refresh_from_db()
    assert review.state == S.APPROVED and review.human_reviewer_id is None
    with pytest.raises(HITLApprovalRequired):
        sm.finalize(review, org.manager)


# ── layer 2: the DB CHECK constraint ───────────────────────────────────────


def test_db_check_rejects_finalized_with_null_reviewer_on_direct_save(org, review):
    # Bypass the state machine entirely: a direct ORM field write.
    review.state = S.FINALIZED
    review.human_reviewer = None
    review.finalized_at = timezone.now()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            review.save()
    review.refresh_from_db()
    assert review.state == S.DRAFT  # the database refused the write


def test_db_check_rejects_finalized_with_null_reviewer_on_queryset_update(org, review):
    # .update() skips save() and any app-level guard — only the DB stands.
    with tenant_context(org.tenant):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Review.objects.filter(id=review.id).update(state=S.FINALIZED)
    review.refresh_from_db()
    assert review.state == S.DRAFT


def test_db_check_allows_finalized_with_reviewer(org, review):
    # The constraint blocks only the null-reviewer case; the legal write passes.
    _to_pending(review, org.manager)
    sm.approve(review, org.manager)
    sm.finalize(review, org.manager)
    review.refresh_from_db()
    assert review.state == S.FINALIZED
    assert review.human_reviewer_id is not None
