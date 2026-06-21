"""
State-machine tests — the transition table IS the contract.

Covers: every LEGAL transition succeeds (with the right side effects), a
representative set of ILLEGAL transitions all raise 409, the reject-reason rule,
RBAC inside the machine (peer manager 403), and audit-before-effect ordering.
The HITL gate has its own file (test_hitl.py).
"""
import pytest
from rest_framework.exceptions import PermissionDenied

from apps.audit.models import AuditLog
from apps.reviews import state_machine as sm
from apps.reviews.exceptions import (
    HITLApprovalRequired,
    IllegalTransition,
    RejectionReasonRequired,
)
from apps.reviews.models import Review, ReviewStateTransition
from apps.reviews.services import create_review
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
    sm.submit_for_review(review, actor, draft_body="draft v1")
    return review


# ── every LEGAL transition ─────────────────────────────────────────────────


def test_manual_happy_path_reaches_finalized_with_no_ai(org, review):
    mgr = org.manager
    sm.start_edit(review, mgr)
    assert review.state == S.EDITING
    sm.submit_for_review(review, mgr, draft_body="solid year")
    assert review.state == S.PENDING_HUMAN_REVIEW
    sm.approve(review, mgr)
    assert review.state == S.APPROVED
    assert review.human_reviewer_id == mgr.id
    assert review.approved_at is not None
    sm.finalize(review, mgr)
    assert review.state == S.FINALIZED
    assert review.final_body == "solid year"
    assert review.finalized_at is not None
    assert review.source == Review.Source.MANUAL
    assert review.confidence_score is None and review.citations is None


def test_pending_back_to_editing_and_resubmit(org, review):
    _to_pending(review, org.manager)
    sm.start_edit(review, org.manager)  # edit again
    assert review.state == S.EDITING
    sm.submit_for_review(review, org.manager, draft_body="draft v2")
    assert review.state == S.PENDING_HUMAN_REVIEW
    assert review.draft_body == "draft v2"


def test_reject_then_revise(org, review):
    _to_pending(review, org.manager)
    sm.reject(review, org.manager, reason="needs concrete evidence")
    assert review.state == S.REJECTED
    assert review.rejected_reason == "needs concrete evidence"
    sm.start_edit(review, org.manager)  # revise
    assert review.state == S.EDITING


def test_request_ai_draft_and_system_lock(org, review):
    sm.request_ai_draft(review, org.manager)
    assert review.state == S.AI_DRAFTING
    sm.ai_draft_ready(review, draft_body="ai draft", confidence_score=None, citations=None)
    assert review.state == S.PENDING_HUMAN_REVIEW
    assert review.source == Review.Source.AI
    # The system transition records a timeline row with no actor.
    with tenant_context(org.tenant):
        last = review.transitions.order_by("-at", "-created_at").first()
    assert last.actor is None
    assert last.from_state == S.AI_DRAFTING and last.to_state == S.PENDING_HUMAN_REVIEW


def test_every_transition_appends_timeline_row(org, review):
    mgr = org.manager
    sm.start_edit(review, mgr)
    sm.submit_for_review(review, mgr)
    sm.approve(review, mgr)
    sm.finalize(review, mgr)
    with tenant_context(org.tenant):
        rows = list(
            ReviewStateTransition.objects.filter(review=review).order_by("at", "created_at")
        )
    assert [(r.from_state, r.to_state) for r in rows] == [
        (S.DRAFT, S.EDITING),
        (S.EDITING, S.PENDING_HUMAN_REVIEW),
        (S.PENDING_HUMAN_REVIEW, S.APPROVED),
        (S.APPROVED, S.FINALIZED),
    ]


# ── ILLEGAL transitions: rejected with 409, never a no-op ──────────────────


@pytest.mark.parametrize(
    "action",
    ["approve", "reject", "finalize", "submit_for_review", "ai_draft_ready"],
)
def test_illegal_from_draft(org, review, action):
    # From DRAFT only request_ai_draft and start_edit are legal. finalize from
    # DRAFT is the HITL case (422); the others are structural 409s.
    mgr = org.manager
    if action == "finalize":
        with pytest.raises(HITLApprovalRequired):
            sm.finalize(review, mgr)
    elif action == "ai_draft_ready":
        with pytest.raises(IllegalTransition):
            sm.ai_draft_ready(review, draft_body="x")
    elif action == "reject":
        with pytest.raises(IllegalTransition):
            sm.reject(review, mgr, reason="r")
    else:
        with pytest.raises(IllegalTransition):
            getattr(sm, action)(review, mgr)
    review.refresh_from_db()
    assert review.state == S.DRAFT  # nothing applied


def test_approve_twice_is_rejected(org, review):
    _to_pending(review, org.manager)
    sm.approve(review, org.manager)
    with pytest.raises(IllegalTransition):
        sm.approve(review, org.manager)  # re-approve: human_reviewer immutable
    review.refresh_from_db()
    assert review.state == S.APPROVED
    assert review.human_reviewer_id == org.manager.id


def test_finalized_is_terminal(org, review):
    mgr = org.manager
    _to_pending(review, mgr)
    sm.approve(review, mgr)
    sm.finalize(review, mgr)
    for action, kwargs in [
        ("start_edit", {}),
        ("approve", {}),
        ("reject", {"reason": "r"}),
        ("submit_for_review", {}),
        ("request_ai_draft", {}),
    ]:
        with pytest.raises(IllegalTransition):
            getattr(sm, action)(review, mgr, **kwargs)
    with pytest.raises(HITLApprovalRequired) as exc:
        # finalize twice: state is FINALIZED != APPROVED -> the HITL guard fires.
        sm.finalize(review, mgr)
    assert exc.value.detail["code"] == "HITL_APPROVAL_REQUIRED"


def test_illegal_transition_payload_names_from_and_action(org, review):
    with pytest.raises(IllegalTransition) as exc:
        sm.approve(review, org.manager)  # from DRAFT
    detail = exc.value.detail
    assert detail["from_state"] == S.DRAFT
    assert detail["action"] == "approve"
    assert detail["code"] == "ILLEGAL_TRANSITION"
    assert exc.value.status_code == 409


# ── reject-reason rule ─────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_reason", [None, "", "   "])
def test_reject_requires_non_empty_reason(org, review, bad_reason):
    _to_pending(review, org.manager)
    with pytest.raises(RejectionReasonRequired) as exc:
        sm.reject(review, org.manager, reason=bad_reason)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "REJECTION_REASON_REQUIRED"
    review.refresh_from_db()
    assert review.state == S.PENDING_HUMAN_REVIEW  # unchanged


# ── RBAC inside the machine ────────────────────────────────────────────────


def test_peer_manager_cannot_transition_out_of_scope_review(org, review, make_user):
    # A second manager with no reporting line to org.report: in-tenant, out of scope.
    peer_mgr = make_user(tenant=org.tenant, role="MANAGER", email="peermgr@acme.test")
    with pytest.raises(PermissionDenied):
        sm.start_edit(review, peer_mgr)
    _to_pending(review, org.manager)
    with pytest.raises(PermissionDenied):
        sm.approve(review, peer_mgr)  # a peer can never become human_reviewer
    review.refresh_from_db()
    assert review.human_reviewer_id is None


def test_employee_cannot_approve_or_finalize_own_review(org, review):
    _to_pending(review, org.manager)
    with pytest.raises(PermissionDenied):
        sm.approve(review, org.report)  # subject lacks APPROVE_REVIEW
    sm.approve(review, org.manager)
    with pytest.raises(PermissionDenied):
        sm.finalize(review, org.report)  # subject lacks FINALIZE_REVIEW


# ── audit-before-effect ────────────────────────────────────────────────────


def test_audit_written_for_each_consequential_transition(org, review):
    mgr = org.manager
    _to_pending(review, mgr)
    sm.approve(review, mgr)
    sm.finalize(review, mgr)
    with tenant_context(org.tenant):
        actions = set(
            AuditLog.objects.filter(target_id=str(review.id)).values_list("action", flat=True)
        )
    assert {"review.submitted", "review.approved", "review.finalized"} <= actions
    with tenant_context(org.tenant):
        approved = AuditLog.objects.filter(
            target_id=str(review.id), action="review.approved"
        ).first()
    assert approved.metadata["human_reviewer"] == str(mgr.id)


def test_audit_precedes_the_state_change(org, review, monkeypatch):
    # Make the post-audit save explode; the audit row must already exist.
    _to_pending(review, org.manager)
    original_save = Review.save

    def exploding_save(self, *a, **k):
        raise RuntimeError("simulated crash after audit, before persist")

    monkeypatch.setattr(Review, "save", exploding_save)
    with pytest.raises(RuntimeError):
        sm.approve(review, org.manager)
    monkeypatch.setattr(Review, "save", original_save)
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            target_id=str(review.id), action="review.approved"
        ).exists()
    review.refresh_from_db()
    assert review.state == S.PENDING_HUMAN_REVIEW  # effect did NOT apply


# ── creation rules ─────────────────────────────────────────────────────────


def test_create_review_requires_active_cycle(org):
    from apps.reviews.exceptions import CycleNotActive

    for status in ("DRAFT", "CLOSED"):
        cycle = CycleFactory(tenant=org.tenant, status=status)
        with pytest.raises(CycleNotActive) as exc:
            create_review(employee=org.report, cycle=cycle, actor=org.manager)
        assert exc.value.status_code == 409


def test_transitions_still_allowed_after_cycle_closes(org, review):
    # In-flight reviews complete even after the cycle closes.
    _to_pending(review, org.manager)
    review.cycle.status = "CLOSED"
    review.cycle.save()
    sm.approve(review, org.manager)
    sm.finalize(review, org.manager)
    assert review.state == S.FINALIZED


def test_reviewer_defaults_to_acting_manager(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    r = create_review(employee=org.report, cycle=cycle, actor=org.manager)
    assert r.reviewer_id == org.manager.id
    assert r.state == S.DRAFT
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="review.created").exists()


def test_one_review_per_employee_per_cycle(org):
    from django.db import IntegrityError, transaction

    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    create_review(employee=org.report, cycle=cycle, actor=org.manager)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            create_review(employee=org.report, cycle=cycle, actor=org.manager)


# ── tenant isolation ───────────────────────────────────────────────────────


def test_cross_tenant_review_reads_impossible(org, other_tenant, make_user):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    review = ReviewFactory(employee=org.report, cycle=cycle)
    with tenant_context(other_tenant):
        assert Review.objects.filter(id=review.id).count() == 0
    with tenant_context(org.tenant):
        assert Review.objects.filter(id=review.id).count() == 1


def test_cross_tenant_actor_out_of_scope(org, other_tenant, make_user, review):
    outsider_mgr = make_user(tenant=other_tenant, role="MANAGER", email="out@other.test")
    with pytest.raises(PermissionDenied):
        sm.start_edit(review, outsider_mgr)


# ── Module-5 route-rejection edge: APPROVED -> EDITING ─────────────────────


def test_route_rejected_returns_approved_review_to_editing(org, review):
    """An approval route rejecting the finalize bounces the APPROVED review back to
    EDITING as a SYSTEM transition, clearing the in-flight route link."""
    mgr = org.manager
    _to_pending(review, mgr)
    sm.approve(review, mgr)
    assert review.state == S.APPROVED

    sm.route_rejected(review, reason="approver sent it back")
    assert review.state == S.EDITING
    assert review.approval_route_id is None
    with tenant_context(review.tenant_id):
        last = ReviewStateTransition.objects.filter(review=review).order_by("-at").first()
    assert last.from_state == S.APPROVED and last.to_state == S.EDITING
    assert last.actor_id is None  # system transition (the human decision was on the route)


def test_route_rejected_illegal_unless_approved(org, review):
    """route_rejected is only legal from APPROVED — illegal from PENDING_HUMAN_REVIEW."""
    _to_pending(review, org.manager)  # PENDING_HUMAN_REVIEW
    with pytest.raises(IllegalTransition):
        sm.route_rejected(review, reason="x")
