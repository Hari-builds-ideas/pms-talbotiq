"""
RW_BUILD_4 — AI assistant propose-and-confirm (HITL). The safety contract:
  * a PROPOSAL is inert — proposing approves nothing (only an explicit Approve does);
  * EXECUTE re-checks capability + object scope on the real targets — it can never do
    what the user couldn't do via the normal endpoint (out-of-scope targets refused);
  * an approved action writes + audits EXACTLY once (idempotent re-run skips);
  * a user without the action's capability gets no proposal and can't execute.
"""
import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.ai.actions import execute_action, propose_action
from apps.audit.models import AuditLog
from apps.goals.models import Goal
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, ReviewFactory

pytestmark = pytest.mark.django_db

MSG = "please approve my team's goals"


def _pending_goal(org, employee):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    return GoalFactory(employee=employee, cycle=cycle, status="ACTIVE")  # approved_by=None


def test_proposal_is_inert_no_write(org):
    with tenant_context(org.tenant):
        goal = _pending_goal(org, org.report)
        proposal = propose_action(org.manager, MSG)
        assert proposal is not None
        assert proposal["action"] == "approve_goals"
        assert str(goal.id) in proposal["params"]["goal_ids"]
        # Proposing must NOT approve anything.
        goal.refresh_from_db()
        assert goal.approved_by_id is None
        assert AuditLog.objects.filter(action="goal.approved", target_id=goal.id).count() == 0


def test_execute_approves_and_audits_exactly_once(org):
    with tenant_context(org.tenant):
        goal = _pending_goal(org, org.report)
        out = execute_action(org.manager, "approve_goals", {"goal_ids": [str(goal.id)]})
        assert out["approved"] == 1
        goal.refresh_from_db()
        assert goal.approved_by_id == org.manager.id
        assert AuditLog.objects.filter(action="goal.approved", target_id=goal.id).count() == 1
        # Re-running the same approved action is a no-op (skipped) — no double write/audit.
        again = execute_action(org.manager, "approve_goals", {"goal_ids": [str(goal.id)]})
        assert again["approved"] == 0
        assert again["skipped"][0]["reason"] == "already_approved"
        assert AuditLog.objects.filter(action="goal.approved", target_id=goal.id).count() == 1


def test_out_of_scope_target_refused_at_execution(org):
    """A manager handing in a goal id outside their scope (a peer's, under HRBP) is
    skipped at execution — not approved."""
    with tenant_context(org.tenant):
        peer_goal = _pending_goal(org, org.peer)  # org.peer reports to hrbp, not manager
        out = execute_action(org.manager, "approve_goals", {"goal_ids": [str(peer_goal.id)]})
        assert out["approved"] == 0
        assert out["skipped"][0]["reason"] == "out_of_scope"
        peer_goal.refresh_from_db()
        assert peer_goal.approved_by_id is None


def test_employee_gets_no_proposal_and_cannot_execute(org):
    with tenant_context(org.tenant):
        goal = _pending_goal(org, org.report)
        # An employee lacks APPROVE_GOALS → no proposal is ever offered.
        assert propose_action(org.report, MSG) is None
        # …and a direct execute attempt is refused.
        with pytest.raises(PermissionDenied):
            execute_action(org.report, "approve_goals", {"goal_ids": [str(goal.id)]})
        goal.refresh_from_db()
        assert goal.approved_by_id is None


def test_propose_none_when_nothing_pending(org):
    with tenant_context(org.tenant):
        # No pending goals in the manager's scope → don't propose (chat replies normally).
        assert propose_action(org.manager, MSG) is None


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def test_execute_endpoint_writes_once_over_http(org):
    with tenant_context(org.tenant):
        goal = _pending_goal(org, org.report)
    resp = _client(org.manager).post(
        "/api/ai/actions/execute",
        {"action": "approve_goals", "params": {"goal_ids": [str(goal.id)]}},
        format="json",
    )
    assert resp.status_code == 200 and resp.json()["approved"] == 1
    with tenant_context(org.tenant):
        goal.refresh_from_db()
        assert goal.approved_by_id == org.manager.id
    # An employee hitting the execute endpoint is refused (no APPROVE_GOALS) → 403.
    emp = _client(org.report).post(
        "/api/ai/actions/execute",
        {"action": "approve_goals", "params": {"goal_ids": [str(goal.id)]}},
        format="json",
    )
    assert emp.status_code == 403


# ── RW_BUILD_5: a 2nd action — approve_reviews (reuses state_machine.approve) ──

REVIEW_MSG = "approve my team's reviews"


def _pending_review(org, employee):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    return ReviewFactory(employee=employee, cycle=cycle, state="PENDING_HUMAN_REVIEW")


def test_review_proposal_is_inert(org):
    with tenant_context(org.tenant):
        review = _pending_review(org, org.report)
        proposal = propose_action(org.manager, REVIEW_MSG)
        assert proposal and proposal["action"] == "approve_reviews"
        assert str(review.id) in proposal["params"]["review_ids"]
        review.refresh_from_db()
        assert review.state == "PENDING_HUMAN_REVIEW"  # proposing changed nothing


def test_execute_approves_reviews_and_is_idempotent(org):
    with tenant_context(org.tenant):
        review = _pending_review(org, org.report)
        out = execute_action(org.manager, "approve_reviews", {"review_ids": [str(review.id)]})
        assert out["approved"] == 1
        review.refresh_from_db()
        assert review.state == "APPROVED" and review.human_reviewer_id == org.manager.id
        assert AuditLog.objects.filter(action="review.approved", target_id=review.id).count() == 1
        # Re-run: already APPROVED → the state machine rejects → skipped, no double write.
        again = execute_action(org.manager, "approve_reviews", {"review_ids": [str(review.id)]})
        assert again["approved"] == 0 and again["skipped"]
        assert AuditLog.objects.filter(action="review.approved", target_id=review.id).count() == 1


def test_review_out_of_scope_refused_at_execution(org):
    with tenant_context(org.tenant):
        peer_review = _pending_review(org, org.peer)  # peer reports to hrbp, not manager
        out = execute_action(org.manager, "approve_reviews", {"review_ids": [str(peer_review.id)]})
        assert out["approved"] == 0 and out["skipped"]
        peer_review.refresh_from_db()
        assert peer_review.state == "PENDING_HUMAN_REVIEW"  # untouched


def test_employee_no_review_proposal_or_execute(org):
    with tenant_context(org.tenant):
        review = _pending_review(org, org.report)
        assert propose_action(org.report, REVIEW_MSG) is None
        with pytest.raises(PermissionDenied):
            execute_action(org.report, "approve_reviews", {"review_ids": [str(review.id)]})
        review.refresh_from_db()
        assert review.state == "PENDING_HUMAN_REVIEW"
