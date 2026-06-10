"""
Module 5 ↔ Module 3: review.finalize OPT-IN routing, proven not to break Module 3.

With NO active "review" workflow, finalize is single-step exactly as before. With
one active, finalize ENTERS the route (review stays APPROVED + linked); route
completion finalises via the EXISTING audited path (CHECK constraint intact);
route rejection returns the review to its author.
"""
import pytest

from apps.approvals import engine
from apps.approvals.models import ApprovalRoute
from apps.reviews import state_machine as sm
from apps.reviews.models import Review
from apps.reviews.services import create_review
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    ApprovalStepFactory,
    ApprovalWorkflowFactory,
    CycleFactory,
)

pytestmark = pytest.mark.django_db

S = Review.State


def _approved_review(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    review = create_review(employee=org.report, cycle=cycle, actor=org.manager)
    sm.start_edit(review, org.manager)
    sm.submit_for_review(review, org.manager, draft_body="great year")
    sm.approve(review, org.manager)
    return review


def _review_workflow(org, mode="SEQUENTIAL"):
    wf = ApprovalWorkflowFactory(
        tenant=org.tenant, artifact_type="review", mode=mode, active=True
    )
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER")
    ApprovalStepFactory(workflow=wf, order=2, approver_kind="ROLE", approver_role="HRBP")
    return wf


def test_no_workflow_single_step_finalize_unchanged(org):
    review = _approved_review(org)
    sm.finalize(review, org.manager)
    assert review.state == S.FINALIZED          # exactly Module 3
    assert review.approval_route_id is None


def test_active_workflow_routes_finalize_instead_of_finalising(org):
    _review_workflow(org)
    review = _approved_review(org)
    sm.finalize(review, org.manager)
    review.refresh_from_db()
    assert review.state == S.APPROVED           # NOT finalised
    assert review.finalized_at is None
    assert review.approval_route_id is not None
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=review.approval_route_id)
    assert route.status == "IN_PROGRESS" and route.artifact_type == "review"


def test_route_completion_finalises_review_via_existing_path(org):
    _review_workflow(org)
    review = _approved_review(org)
    sm.finalize(review, org.manager)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=review.approval_route_id)
        s1, s2 = route.step_instances.order_by("order")
        assert s1.approver_id == org.manager.id  # MANAGER -> subject's manager
    engine.record_decision(s1, org.manager, "APPROVE")
    engine.record_decision(s2, org.hrbp, "APPROVE")
    review.refresh_from_db()
    assert review.state == S.FINALIZED
    assert review.final_body == "great year"
    assert review.human_reviewer_id == org.manager.id   # CHECK constraint satisfied
    with tenant_context(org.tenant):
        route.refresh_from_db()
    assert route.status == "APPROVED"


def test_route_rejection_returns_review_to_author_and_allows_fresh_route(org):
    _review_workflow(org)
    review = _approved_review(org)
    sm.finalize(review, org.manager)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=review.approval_route_id)
        s1 = route.step_instances.get(order=1)
    engine.record_decision(s1, org.manager, "REJECT", comment="redo the evidence")
    review.refresh_from_db()
    assert review.state == S.EDITING            # returned to author
    assert review.approval_route_id is None     # link cleared
    assert review.finalized_at is None          # FINALIZED never written

    # Re-submission starts a FRESH route (the first is terminal/REJECTED).
    sm.submit_for_review(review, org.manager, draft_body="v2")
    sm.approve(review, org.manager)
    sm.finalize(review, org.manager)
    with tenant_context(org.tenant):
        assert ApprovalRoute.objects.filter(artifact_id=review.id).count() == 2


def test_parallel_review_workflow_completes_and_finalises(org):
    wf = ApprovalWorkflowFactory(
        tenant=org.tenant, artifact_type="review", mode="PARALLEL", active=True
    )
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER", required=True)
    ApprovalStepFactory(workflow=wf, order=2, approver_kind="ROLE", approver_role="HRBP", required=True)
    review = _approved_review(org)
    sm.finalize(review, org.manager)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=review.approval_route_id)
        steps = {s.order: s for s in route.step_instances.all()}
    engine.record_decision(steps[1], org.manager, "APPROVE")
    engine.record_decision(steps[2], org.hrbp, "APPROVE")
    review.refresh_from_db()
    assert review.state == S.FINALIZED
