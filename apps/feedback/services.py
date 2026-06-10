"""
Feedback lifecycle services — the single write paths the API (and future
modules) call. Every consequential action audits BEFORE it takes effect.

All services bind the tenant themselves (the Module-2/Module-3 lesson: scoped
managers fail closed off-request; on a request, re-binding the same tenant is a
harmless no-op).
"""
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.tenancy.context import tenant_context

from .exceptions import (
    CycleNotCollecting,
    FeedbackImmutable,
    IllegalCycleTransition,
    InvitationRequired,
)
from .models import Feedback, FeedbackCycle, FeedbackRequest


def open_cycle(cycle, actor):
    """DRAFT -> COLLECTING. Opens the collection window."""
    with tenant_context(cycle.tenant_id):
        if cycle.status != FeedbackCycle.Status.DRAFT:
            raise IllegalCycleTransition(cycle.status, "open")
        record(
            action="feedback_cycle.opened",
            actor=actor,
            target_type="feedback_cycle",
            target_id=cycle.id,
            metadata={"subject": str(cycle.subject_id)},
            tenant=cycle.tenant_id,
        )
        cycle.status = FeedbackCycle.Status.COLLECTING
        cycle.opened_at = timezone.now()
        cycle.save(update_fields=["status", "opened_at", "updated_at"])
        return cycle


def close_cycle(cycle, actor):
    """COLLECTING -> CLOSED — the fence that ends capture — then summarize.

    Closing immutably freezes the cycle's feedback and fires the summarize
    pipeline (anonymise -> threshold -> breach guard -> Agent-3 seam). Returns
    ``(cycle, summarize_result)``.
    """
    with tenant_context(cycle.tenant_id):
        if cycle.status != FeedbackCycle.Status.COLLECTING:
            raise IllegalCycleTransition(cycle.status, "close")
        record(
            action="feedback_cycle.closed",
            actor=actor,
            target_type="feedback_cycle",
            target_id=cycle.id,
            metadata={"subject": str(cycle.subject_id)},
            tenant=cycle.tenant_id,
        )
        cycle.status = FeedbackCycle.Status.CLOSED
        cycle.closed_at = timezone.now()
        cycle.save(update_fields=["status", "closed_at", "updated_at"])

    # Lazy import: tasks.py imports this module's siblings; keep the edge one-way.
    from .tasks import summarize_feedback

    result = summarize_feedback(
        str(cycle.tenant_id), str(cycle.id), actor_id=str(actor.id) if actor else None
    )
    return cycle, result


def send_feedback_request(*, cycle, giver, relationship, actor):
    """Invite ``giver`` to give ``relationship`` feedback on the cycle's subject.

    The invitation fixes the relationship (never client-supplied at submit
    time). Rules: SELF may only be the subject; the subject may hold ONLY the
    SELF invitation (no peer/upward feedback about yourself); one invitation
    per giver per cycle. The Slack notification push is Module 12 — for MVP the
    pending FeedbackRequest row IS the in-app notification.
    """
    with tenant_context(cycle.tenant_id):
        if cycle.status == FeedbackCycle.Status.CLOSED:
            raise IllegalCycleTransition(cycle.status, "invite into")
        is_self = relationship == FeedbackRequest.Relationship.SELF
        if is_self and giver.id != cycle.subject_id:
            raise ValidationError(
                {"relationship": "A SELF invitation can only go to the cycle's subject."}
            )
        if not is_self and giver.id == cycle.subject_id:
            raise ValidationError(
                {"giver": "The subject can only receive the SELF invitation."}
            )
        if FeedbackRequest.objects.filter(cycle=cycle, giver=giver).exists():
            raise ValidationError(
                {"giver": "This giver already has an invitation for this cycle."}
            )
        record(
            action="feedback_request.sent",
            actor=actor,
            target_type="feedback_cycle",
            target_id=cycle.id,
            metadata={"relationship": relationship},
            tenant=cycle.tenant_id,
        )
        return FeedbackRequest.objects.create(
            tenant_id=cycle.tenant_id,
            cycle=cycle,
            giver=giver,
            relationship=relationship,
        )


def decline_request(request_obj, actor):
    """The invited giver declines. Only the giver themselves, only while PENDING."""
    with tenant_context(request_obj.tenant_id):
        if actor.id != request_obj.giver_id:
            raise ValidationError({"giver": "Only the invited giver may decline."})
        if request_obj.status != FeedbackRequest.Status.PENDING:
            raise ValidationError({"status": "Only a pending invitation can be declined."})
        request_obj.status = FeedbackRequest.Status.DECLINED
        request_obj.save(update_fields=["status", "updated_at"])
        return request_obj


def give_feedback_360(*, cycle, giver, body, marked_sensitive=False):
    """Submit 360 feedback. Authorised ONLY by a PENDING invitation.

    The giver is ALWAYS the acting user (server-set upstream — anti-spoof).
    Cycle must be COLLECTING (409 otherwise — DRAFT hasn't opened, CLOSED is the
    capture fence). The relationship comes FROM the invitation. One submission
    per giver per cycle (the invitation flips to SUBMITTED; the DB constraint
    backs it).
    """
    with tenant_context(cycle.tenant_id):
        if cycle.status != FeedbackCycle.Status.COLLECTING:
            raise CycleNotCollecting(cycle.status)
        invitation = FeedbackRequest.objects.filter(
            cycle=cycle, giver=giver, status=FeedbackRequest.Status.PENDING
        ).first()
        if invitation is None:
            raise InvitationRequired()
        record(
            action="feedback.submitted",
            actor=giver,
            target_type="feedback_cycle",
            target_id=cycle.id,
            metadata={"relationship": invitation.relationship},
            tenant=cycle.tenant_id,
        )
        item = Feedback.objects.create(
            tenant_id=cycle.tenant_id,
            cycle=cycle,
            subject=cycle.subject,
            giver=giver,
            relationship=invitation.relationship,
            kind=Feedback.Kind.THREE_SIXTY,
            body=body,
            giver_marked_sensitive=marked_sensitive,
        )
        invitation.status = FeedbackRequest.Status.SUBMITTED
        invitation.save(update_fields=["status", "updated_at"])
        return item


def give_continuous_feedback(*, subject, giver, body, marked_sensitive=False):
    """Any-time, cycle-less feedback within the tenant.

    Not subject to the 360 min-volume gate, never auto-summarised. Self-directed
    continuous feedback is rejected (the SELF row of a 360 is the only
    self-feedback).
    """
    with tenant_context(giver.tenant_id):
        if subject.id == giver.id:
            raise ValidationError(
                {"subject": "Continuous feedback about yourself is not supported."}
            )
        record(
            action="feedback.submitted",
            actor=giver,
            target_type="user",
            target_id=subject.id,
            metadata={"kind": "CONTINUOUS"},
            tenant=giver.tenant_id,
        )
        return Feedback.objects.create(
            tenant_id=giver.tenant_id,
            cycle=None,
            subject=subject,
            giver=giver,
            relationship=Feedback.Relationship.PEER,
            kind=Feedback.Kind.CONTINUOUS,
            body=body,
            giver_marked_sensitive=marked_sensitive,
        )


def approve_summary(summary, actor):
    """HRBP review: release a held (or pending) summary to its subject.

    HRBP_HOLD -> RELEASED clears an anonymity-breach / sensitive hold after a
    human reviewed it; PENDING_HUMAN_REVIEW -> RELEASED is the human approval of
    a (Module 10) drafted summary. RELEASED is terminal. ``reviewed_by`` and
    ``released_at`` are server-set. Audits BEFORE the effect.
    """
    from .models import FeedbackSummary

    with tenant_context(summary.tenant_id):
        if summary.status == FeedbackSummary.Status.RELEASED:
            raise ValidationError({"status": "This summary is already released."})
        record(
            action="summary.approved",
            actor=actor,
            target_type="feedback_summary",
            target_id=summary.id,
            metadata={"from_status": summary.status},
            tenant=summary.tenant_id,
        )
        record(
            action="summary.released",
            actor=actor,
            target_type="feedback_summary",
            target_id=summary.id,
            metadata={"subject": str(summary.subject_id)},
            tenant=summary.tenant_id,
        )
        summary.status = FeedbackSummary.Status.RELEASED
        summary.reviewed_by = actor
        summary.released_at = timezone.now()
        summary.save(
            update_fields=["status", "reviewed_by", "released_at", "updated_at"]
        )
        return summary


def edit_own_feedback(item, actor, *, body=None, marked_sensitive=None):
    """A giver may edit their OWN feedback until its cycle is CLOSED.

    Once the cycle closes (or for continuous feedback, indefinitely editable by
    its giver), the 360 item is immutable — the summary was built from it.
    """
    with tenant_context(item.tenant_id):
        if actor.id != item.giver_id:
            raise ValidationError({"giver": "Only the giver may edit their feedback."})
        if item.cycle_id is not None and item.cycle.status == FeedbackCycle.Status.CLOSED:
            raise FeedbackImmutable()
        if body is not None:
            item.body = body
        if marked_sensitive is not None:
            item.giver_marked_sensitive = marked_sensitive
        item.save()
        return item
