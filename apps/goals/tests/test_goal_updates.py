"""
GoalUpdate — the goal "Updates" timeline (AGENT_UX_V3 Part 2.3). A short progress
note, written by the goal's OWNER or a manager in scope, append-only + audited.
Covers: create + list over HTTP, tenant isolation (cross-tenant id → 404), the audit
row, and the object-scope boundary (a peer out of scope → 403).
"""
import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.goals.models import GoalUpdate
from apps.goals.services import add_goal_update
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, UserFactory

pytestmark = pytest.mark.django_db


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _goal(org, employee):
    return GoalFactory(employee=employee, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), status="ACTIVE")


def test_owner_creates_and_lists_updates(org):
    with tenant_context(org.tenant):
        goal = _goal(org, org.report)
    url = f"/api/goals/{goal.id}/updates"
    resp = _client(org.report).post(url, {"text": "Shipped v2 of the pricing page."}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.json()["text"] == "Shipped v2 of the pricing page."
    listed = _client(org.report).get(url)
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert listed.json()[0]["author_name"]  # author resolved


def test_manager_can_update_a_report_goal_but_a_peer_cannot(org):
    with tenant_context(org.tenant):
        goal = _goal(org, org.report)  # report → manager
    url = f"/api/goals/{goal.id}/updates"
    # A manager (in scope) may add an update to a report's goal.
    assert _client(org.manager).post(url, {"text": "Great progress, keep it up."}, format="json").status_code == 201
    # A peer (under HRBP, out of this manager's subtree) is refused by object scope.
    assert _client(org.peer).post(url, {"text": "nope"}, format="json").status_code == 403


def test_tenant_isolation_cross_tenant_goal_is_404(org, other_tenant):
    with tenant_context(org.tenant):
        goal = _goal(org, org.report)
    outsider = UserFactory(tenant=other_tenant, role="ADMIN", email="out-gu@other.test")
    resp = _client(outsider).post(f"/api/goals/{goal.id}/updates", {"text": "x"}, format="json")
    assert resp.status_code == 404  # the goal is invisible under the outsider's tenant
    with tenant_context(org.tenant):
        assert GoalUpdate.objects.filter(goal=goal).count() == 0  # nothing written


def test_add_goal_update_audits_before_write(org):
    with tenant_context(org.tenant):
        goal = _goal(org, org.report)
        update = add_goal_update(org.report, goal, "Closed the top 3 support tickets.")
        assert update.author_id == org.report.id and update.text
        assert AuditLog.objects.filter(action="goal.update.added", target_id=goal.id).count() == 1


def test_empty_update_text_is_rejected(org):
    with tenant_context(org.tenant):
        goal = _goal(org, org.report)
    resp = _client(org.report).post(f"/api/goals/{goal.id}/updates", {"text": "   "}, format="json")
    assert resp.status_code == 400
