"""
The review state machine — an explicit, hand-rolled transition table.

No state-machine library: the table below IS the contract (it matches the Doc 2
§Module 4 diagram; the manual path is first-class). Every transition:

    1. validates the current state against the table (illegal -> 409 naming the
       attempted from/action),
    2. checks RBAC — capability + row scope (``actor_can_access`` on the review's
       subject) — unless it is a system transition (the Agent-1 worker),
    3. writes an immutable audit record BEFORE applying (CLAUDE.md rule: audit
       before the action takes effect),
    4. persists the new state (+ transition-specific fields), and
    5. appends a :class:`ReviewStateTransition` timeline row.

Legal transitions::

    DRAFT                -> AI_DRAFTING          request_ai_draft (Agent-1 seam)
    DRAFT                -> EDITING              start_edit (manual draft)
    AI_DRAFTING          -> PENDING_HUMAN_REVIEW ai_draft_ready (system; LOCKS the draft)
    EDITING              -> PENDING_HUMAN_REVIEW submit_for_review
    PENDING_HUMAN_REVIEW -> EDITING              start_edit (edit again)
    PENDING_HUMAN_REVIEW -> APPROVED             approve (HITL: sets human_reviewer)
    PENDING_HUMAN_REVIEW -> REJECTED             reject (reason REQUIRED)
    REJECTED             -> EDITING              start_edit (revise)
    APPROVED             -> FINALIZED            finalize (single-step for now)

Re-running a terminal/illegal transition (approve twice, finalize a FINALIZED
review, edit a FINALIZED review) is REJECTED with 409 — never a silent no-op.

HITL gate (layer 1 of 3): ``finalize`` demands state == APPROVED AND a non-null
``human_reviewer`` and raises 422 HITL_APPROVAL_REQUIRED otherwise. Layer 2 is
the DB CHECK constraint on the table; layer 3 is the API contract.

Module-5 seam: ``finalize`` is deliberately a SINGLE step (APPROVED -> FINALIZED).
When Module 5 (Approval Workflows) lands, its routing engine replaces the body of
``finalize`` with multi-step sequential/parallel sign-off, entering here and
completing with the same audited FINALIZED write. Do not widen this transition
elsewhere.
"""
import functools

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.services import record
from apps.rbac.matrix import Capability, role_has_capability
from apps.rbac.scope import actor_can_access
from apps.tenancy.context import tenant_context

from .exceptions import (
    HITLApprovalRequired,
    IllegalTransition,
    RejectionReasonRequired,
)
from .models import Review, ReviewStateTransition

S = Review.State

#: action -> (frozenset of legal from-states, to-state). The single source of
#: truth for legality; every transition function consults it.
TRANSITIONS = {
    "request_ai_draft": (frozenset({S.DRAFT}), S.AI_DRAFTING),
    "start_edit": (frozenset({S.DRAFT, S.PENDING_HUMAN_REVIEW, S.REJECTED}), S.EDITING),
    "ai_draft_ready": (frozenset({S.AI_DRAFTING}), S.PENDING_HUMAN_REVIEW),
    "submit_for_review": (frozenset({S.EDITING}), S.PENDING_HUMAN_REVIEW),
    "approve": (frozenset({S.PENDING_HUMAN_REVIEW}), S.APPROVED),
    "reject": (frozenset({S.PENDING_HUMAN_REVIEW}), S.REJECTED),
    "finalize": (frozenset({S.APPROVED}), S.FINALIZED),
    # Module 5: an approval route's rejection returns an APPROVED review to its
    # author to revise (additive edge; the engine's on_route_rejected uses it).
    "route_rejected": (frozenset({S.APPROVED}), S.EDITING),
}


def _tenant_bound(fn):
    """Bind the review's tenant for the duration of the transition.

    Transitions run on requests (tenant already bound — re-binding the same
    tenant is a harmless no-op) AND off-request (Celery worker, tests), where
    the scoped managers would otherwise FAIL CLOSED and even the legitimate
    manager would be denied by the subtree scope query. Same pattern as the
    Module-2 scoring engine.
    """

    @functools.wraps(fn)
    def wrapper(review, *args, **kwargs):
        with tenant_context(review.tenant_id):
            return fn(review, *args, **kwargs)

    return wrapper


def _check_legality(review, action):
    allowed_from, to_state = TRANSITIONS[action]
    if review.state not in allowed_from:
        raise IllegalTransition(review.state, action, to_state)
    return to_state


def _check_rbac(actor, review, capability):
    """Capability + row scope. Fails closed; raises DRF PermissionDenied (403)."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication required for this transition.")
    if not role_has_capability(actor.role, capability):
        raise PermissionDenied("Your role does not permit this review transition.")
    if not actor_can_access(actor, review.employee):
        raise PermissionDenied("This review is outside your access scope.")


def _apply(review, *, action, to_state, actor, audit_action, note="", metadata=None):
    """Audit BEFORE, then persist the state + timeline row. Returns the review."""
    from_state = review.state
    meta = {"from_state": from_state, "to_state": to_state}
    if metadata:
        meta.update(metadata)
    record(
        action=audit_action,
        actor=actor,
        target_type="review",
        target_id=review.id,
        metadata=meta,
        tenant=review.tenant_id,
    )
    review.state = to_state
    review.save()
    ReviewStateTransition.objects.create(
        tenant_id=review.tenant_id,
        review=review,
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        at=timezone.now(),
        note=note,
    )
    return review


@_tenant_bound
def request_ai_draft(review, actor):
    """DRAFT -> AI_DRAFTING. The Agent-1 seam entry (Module 10 owns the agent).

    Callers (the Celery task) must only invoke this once a provider is actually
    configured — an unconfigured provider leaves the review in DRAFT (the task
    logs-and-skips; see ``apps/reviews/agent1.py``).
    """
    to_state = _check_legality(review, "request_ai_draft")
    _check_rbac(actor, review, Capability.RUN_AI_REVIEW_DRAFT)
    return _apply(
        review,
        action="request_ai_draft",
        to_state=to_state,
        actor=actor,
        audit_action="review.ai_draft_requested",
    )


@_tenant_bound
def start_edit(review, actor):
    """DRAFT/PENDING_HUMAN_REVIEW/REJECTED -> EDITING (manual draft / revise)."""
    to_state = _check_legality(review, "start_edit")
    _check_rbac(actor, review, Capability.MANAGE_REVIEWS)
    return _apply(
        review,
        action="start_edit",
        to_state=to_state,
        actor=actor,
        audit_action="review.edit_started",
    )


@_tenant_bound
def ai_draft_ready(review, *, draft_body, confidence_score=None, citations=None):
    """AI_DRAFTING -> PENDING_HUMAN_REVIEW. SYSTEM transition (actor=None).

    Called by the Agent-1 worker to LOCK a returned draft for human review (the
    Doc 3 §5 safeguard pipeline). No RBAC: there is no human actor; the lock is
    the safeguard.
    """
    to_state = _check_legality(review, "ai_draft_ready")
    review.draft_body = draft_body
    review.source = Review.Source.AI
    review.confidence_score = confidence_score
    review.citations = citations
    return _apply(
        review,
        action="ai_draft_ready",
        to_state=to_state,
        actor=None,
        audit_action="review.ai_draft_ready",
        note="AI draft locked for human review",
    )


@_tenant_bound
def submit_for_review(review, actor, *, draft_body=None):
    """EDITING -> PENDING_HUMAN_REVIEW (save the manual draft for approval)."""
    to_state = _check_legality(review, "submit_for_review")
    _check_rbac(actor, review, Capability.MANAGE_REVIEWS)
    if draft_body is not None:
        review.draft_body = draft_body
    return _apply(
        review,
        action="submit_for_review",
        to_state=to_state,
        actor=actor,
        audit_action="review.submitted",
    )


@_tenant_bound
def approve(review, actor):
    """PENDING_HUMAN_REVIEW -> APPROVED. THE HITL human approval.

    Sets ``human_reviewer`` (the acting human) + ``approved_at`` (server time).
    The actor must hold APPROVE_REVIEW and be in scope for the subject — a peer
    manager can never be recorded as approver. ``human_reviewer`` is immutable
    afterwards: approve is only legal from PENDING_HUMAN_REVIEW, so re-approving
    an APPROVED/FINALIZED review is rejected by the table (409).
    """
    to_state = _check_legality(review, "approve")
    _check_rbac(actor, review, Capability.APPROVE_REVIEW)
    review.human_reviewer = actor
    review.approved_at = timezone.now()
    return _apply(
        review,
        action="approve",
        to_state=to_state,
        actor=actor,
        audit_action="review.approved",
        metadata={"human_reviewer": str(actor.id)},
    )


@_tenant_bound
def reject(review, actor, *, reason):
    """PENDING_HUMAN_REVIEW -> REJECTED. A non-empty reason is REQUIRED (422)."""
    to_state = _check_legality(review, "reject")
    _check_rbac(actor, review, Capability.APPROVE_REVIEW)
    if reason is None or not str(reason).strip():
        raise RejectionReasonRequired()
    review.rejected_reason = str(reason).strip()
    return _apply(
        review,
        action="reject",
        to_state=to_state,
        actor=actor,
        audit_action="review.rejected",
        metadata={"reason": review.rejected_reason},
        note=review.rejected_reason,
    )


@_tenant_bound
def finalize(review, actor):
    """APPROVED -> FINALIZED, OR enter an approval route (Module 5, opt-in).

    HITL gate, layer 1: demands state == APPROVED AND human_reviewer set; anything
    else is 422 HITL_APPROVAL_REQUIRED.

    Opt-in routing: if the tenant has an ACTIVE "review" approval workflow, finalize
    ENTERS the route instead of finalising — the review stays APPROVED, gains an
    in-flight ``approval_route`` link, and the engine calls ``_finalize_apply`` on
    route completion (writing FINALIZED through the same audited path, the DB CHECK
    constraint still governing). With NO active workflow, finalize behaves EXACTLY
    as before (single step). The Module-3 state machine is otherwise untouched.
    """
    if review.state != S.APPROVED or review.human_reviewer_id is None:
        raise HITLApprovalRequired(review.state)
    _check_rbac(actor, review, Capability.FINALIZE_REVIEW)

    # Lazy import keeps state_machine import-order-independent of the approvals app.
    from apps.approvals.engine import active_workflow_for, start_route

    if review.approval_route_id is None and active_workflow_for(review.tenant_id, "review"):
        route = start_route(
            "review", review.id, initiated_by=actor, tenant_id=review.tenant_id
        )
        record(
            action="review.finalize_routed",
            actor=actor,
            target_type="review",
            target_id=review.id,
            metadata={"route_id": str(route.id)},
            tenant=review.tenant_id,
        )
        review.approval_route = route
        review.save(update_fields=["approval_route", "updated_at"])
        return review

    return _finalize_apply(review, actor)


def _finalize_apply(review, actor):
    """The actual APPROVED -> FINALIZED write — the EXISTING audited finalize path.

    Called directly on the single-step path (after finalize's HITL + RBAC checks)
    AND by the approval-route completion handler (Module 5). Callers are already
    tenant-bound and have guaranteed state == APPROVED with human_reviewer set, so
    the DB CHECK constraint always passes.
    """
    to_state = TRANSITIONS["finalize"][1]
    review.final_body = review.draft_body
    review.finalized_at = timezone.now()
    return _apply(
        review,
        action="finalize",
        to_state=to_state,
        actor=actor,
        audit_action="review.finalized",
        metadata={"human_reviewer": str(review.human_reviewer_id)},
    )


@_tenant_bound
def route_rejected(review, *, reason=""):
    """APPROVED -> EDITING — an approval route rejected the finalize (Module 5).

    Returns the review to its author to revise and clears the route link. A SYSTEM
    transition (actor=None — the route's reject WAS the human decision, audited on
    the route). human_reviewer is left set (harmless under EDITING; a fresh approve
    cycle re-stamps it before any re-finalize).
    """
    to_state = _check_legality(review, "route_rejected")
    review.approval_route = None
    if reason:
        review.rejected_reason = reason
    return _apply(
        review,
        action="route_rejected",
        to_state=to_state,
        actor=None,
        audit_action="review.route_rejected",
        note=reason,
    )
