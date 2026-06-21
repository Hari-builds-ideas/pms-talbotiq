"""
Review lifecycle services that sit outside the state machine proper.

``create_review`` is the single creation path (the API and any future module
call it): it enforces the ACTIVE-cycle rule, defaults the author to the acting
manager, and audits BEFORE the row exists. Transitions live in
``state_machine.py``; assessments in ``assessments.py``.
"""
from django.utils import timezone

from apps.audit.services import record
from apps.cycles.models import PerformanceCycle
from apps.tenancy.context import tenant_context

from .exceptions import CycleNotActive
from .models import Review, ReviewAssessment, ReviewComment


def create_review(*, employee, cycle, actor, draft_body=""):
    """Create a DRAFT review for ``employee`` in ``cycle``, authored by ``actor``.

    A review may only be created while its cycle is ACTIVE (409 otherwise) —
    but transitions on an in-flight review remain allowed after the cycle
    closes (you can finalize after close; you just can't open new reviews).
    ``reviewer`` (the author) defaults to the acting manager. RBAC/scope is the
    caller's job (the view gates capability + scope before calling).
    """
    if cycle.status != PerformanceCycle.Status.ACTIVE:
        raise CycleNotActive(cycle.status)
    record(
        action="review.created",
        actor=actor,
        target_type="review",
        target_id="",  # id exists only after insert; subject+cycle identify it
        metadata={"employee": str(employee.id), "cycle": str(cycle.id)},
        tenant=employee.tenant_id,
    )
    return Review.objects.create(
        tenant_id=employee.tenant_id,
        employee=employee,
        reviewer=actor,
        cycle=cycle,
        state=Review.State.DRAFT,
        draft_body=draft_body,
    )


def submit_assessment(*, review, assessor, assessment_type, body):
    """Capture (or for SELF, upsert) an assessment on a review.

    One row per (review, assessor) — enforced by a unique constraint. SELF
    re-submission UPSERTS (the subject refining their self-evaluation before
    the review is finalized); other types reject a duplicate by the same
    assessor with a validation error. ``submitted_at`` is always server time.
    Scope/identity rules (who may submit which type) are enforced by the view;
    this service enforces the structural rules.
    """
    from rest_framework.exceptions import ValidationError

    now = timezone.now()
    with tenant_context(review.tenant_id):
        return _submit_assessment_bound(
            review=review,
            assessor=assessor,
            assessment_type=assessment_type,
            body=body,
            now=now,
            ValidationError=ValidationError,
        )


def _submit_assessment_bound(*, review, assessor, assessment_type, body, now, ValidationError):
    if assessment_type == ReviewAssessment.Type.SELF:
        if assessor.id != review.employee_id:
            raise ValidationError(
                {"assessment_type": "Only the review's subject may submit a SELF assessment."}
            )
        record(
            action="assessment.submitted",
            actor=assessor,
            target_type="review",
            target_id=review.id,
            metadata={"assessment_type": assessment_type},
            tenant=review.tenant_id,
        )
        assessment, _created = ReviewAssessment.all_objects.update_or_create(
            review=review,
            assessor=assessor,
            defaults={
                "tenant_id": review.tenant_id,
                "assessment_type": assessment_type,
                "body": body,
                "submitted_at": now,
            },
        )
        return assessment

    if ReviewAssessment.objects.filter(review=review, assessor=assessor).exists():
        raise ValidationError(
            {"assessor": "This assessor has already submitted an assessment for this review."}
        )
    record(
        action="assessment.submitted",
        actor=assessor,
        target_type="review",
        target_id=review.id,
        metadata={"assessment_type": assessment_type},
        tenant=review.tenant_id,
    )
    return ReviewAssessment.objects.create(
        tenant_id=review.tenant_id,
        review=review,
        assessor=assessor,
        assessment_type=assessment_type,
        body=body,
        submitted_at=now,
    )


# ── review comments (BUILD_7 Feature A) ──────────────────────────────────────


def create_comment(*, review, author, body, section=None, parent=None):
    """Create a comment on ``review`` (author = the caller; the view has already
    confirmed the author can VIEW the review in scope). Optional ``section`` tag
    and ``parent`` (a reply). Threading is ONE level: a reply's parent must be a
    top-level comment of the same review, else a 422. Audited."""
    from .exceptions import CommentThreadingError

    if parent is not None:
        if parent.review_id != review.id:
            raise CommentThreadingError("The parent comment belongs to another review.")
        if parent.parent_id is not None:
            raise CommentThreadingError("Replies are one level deep — you can't reply to a reply.")

    with tenant_context(review.tenant_id):
        record(
            action="review.commented",
            actor=author,
            target_type="review",
            target_id=review.id,
            metadata={"section": section or "general", "reply": parent is not None},
            tenant=review.tenant_id,
        )
        return ReviewComment.objects.create(
            tenant_id=review.tenant_id,
            review=review,
            author=author,
            parent=parent,
            section=section,
            body=body,
        )


def edit_comment(*, comment, actor, body):
    """Edit a comment's body. Author-only (the view enforces it); stamps
    ``edited_at`` and audits."""
    now = timezone.now()
    with tenant_context(comment.tenant_id):
        record(
            action="review.comment_edited",
            actor=actor,
            target_type="review",
            target_id=comment.review_id,
            metadata={"comment": str(comment.id)},
            tenant=comment.tenant_id,
        )
        comment.body = body
        comment.edited_at = now
        comment.save(update_fields=["body", "edited_at", "updated_at"])
        return comment


def delete_comment(*, comment, actor):
    """Soft-delete a comment (author-only; the view enforces it). Audited. Its
    replies cascade-soft-delete is NOT automatic — replies are kept but orphaned
    display is handled client-side; we soft-delete just this row."""
    with tenant_context(comment.tenant_id):
        record(
            action="review.comment_deleted",
            actor=actor,
            target_type="review",
            target_id=comment.review_id,
            metadata={"comment": str(comment.id)},
            tenant=comment.tenant_id,
        )
        comment.delete()  # TenantScopedModel soft-delete (sets deleted_at)
