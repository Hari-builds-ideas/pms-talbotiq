"""
HTTP tests for the Approval-Workflows API, hitting the REAL ``/api/approvals/...``
routes (production urlconf — no ``@pytest.mark.urls``).

The headline scenario drives a REAL review to APPROVED and finalizes it over
HTTP so the live Module-3 ↔ Module-5 routing integration is exercised end to end
(``/api/reviews/<id>/finalize`` ENTERS the route when an active "review" workflow
exists; route completion finalises the review through the existing audited path).

Themes:
  * CONFIG (Admin/HRBP only): nested-step create, at-most-one-active replacement,
    the capability gate (Employee/Manager → 403);
  * E2E SEQUENTIAL over HTTP through the review integration: inbox → approve →
    next step active → approve → route APPROVED → review FINALIZED, with the
    audit trail (route.started / step.approved / route.completed);
  * the status-code contract: 409 ILLEGAL_DECISION (out-of-order), reject →
    route REJECTED + review back to EDITING, then a fresh route on re-finalize;
  * assignment / RBAC: peer-manager not the assigned approver → 403, Employee
    lacks the capability → 403, cross-tenant step/route → 404;
  * PARALLEL: both slots actionable at once, both approve → FINALIZED;
  * the route tracker visibility rule; inbox sequencing correctness.
"""
import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.identity.tokens import issue_tokens_for_user
from apps.reviews import state_machine as sm
from apps.reviews.models import Review
from apps.reviews.services import create_review
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db

APPROVALS = "/api/approvals/"
REVIEWS = "/api/reviews/"


# ── helpers ───────────────────────────────────────────────────────────────────


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _seq_workflow_payload(active=True):
    """A canonical SEQUENTIAL "review" matrix: MANAGER (step 1) → HRBP (step 2)."""
    return {
        "name": "Review sign-off",
        "artifact_type": "review",
        "mode": "SEQUENTIAL",
        "active": active,
        "steps": [
            {"order": 1, "approver_kind": "ROLE", "approver_role": "MANAGER"},
            {"order": 2, "approver_kind": "ROLE", "approver_role": "HRBP"},
        ],
    }


def _post_seq_workflow(org, active=True):
    """An Admin POSTs the canonical SEQUENTIAL review workflow; returns its id."""
    resp = _client_for(org.admin).post(
        f"{APPROVALS}workflows", _seq_workflow_payload(active=active), format="json"
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


def _approved_review(org):
    """Drive a fresh review for org.report to APPROVED (manager authors it)."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    review = create_review(employee=org.report, cycle=cycle, actor=org.manager)
    sm.start_edit(review, org.manager)
    sm.submit_for_review(review, org.manager, draft_body="great year")
    sm.approve(review, org.manager)
    return review


# ── 1. CONFIG ───────────────────────────────────────────────────────────────


def test_admin_creates_sequential_workflow_with_steps_and_lists(org):
    admin = _client_for(org.admin)
    resp = admin.post(
        f"{APPROVALS}workflows", _seq_workflow_payload(active=False), format="json"
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "SEQUENTIAL"
    assert body["active"] is False
    assert [s["order"] for s in body["steps"]] == [1, 2]
    assert [s["approver_role"] for s in body["steps"]] == ["MANAGER", "HRBP"]

    # It lists for the tenant.
    rows = admin.get(f"{APPROVALS}workflows").json()
    assert body["id"] in {w["id"] for w in rows}


def test_second_active_workflow_deactivates_the_first(org):
    admin = _client_for(org.admin)
    first_id = _post_seq_workflow(org, active=True)
    assert admin.get(f"{APPROVALS}workflows/{first_id}").json()["active"] is True

    # A second active workflow for the same artifact type → the first deactivates.
    second_id = _post_seq_workflow(org, active=True)
    assert admin.get(f"{APPROVALS}workflows/{second_id}").json()["active"] is True
    assert admin.get(f"{APPROVALS}workflows/{first_id}").json()["active"] is False


def test_employee_cannot_create_workflow(org):
    emp = _client_for(org.report)  # EMPLOYEE lacks CONFIGURE_APPROVAL_WORKFLOW
    resp = emp.post(
        f"{APPROVALS}workflows", _seq_workflow_payload(), format="json"
    )
    assert resp.status_code == 403


def test_manager_cannot_create_workflow(org):
    mgr = _client_for(org.manager)  # MANAGER lacks CONFIGURE_APPROVAL_WORKFLOW (HRBP+)
    resp = mgr.post(
        f"{APPROVALS}workflows", _seq_workflow_payload(), format="json"
    )
    assert resp.status_code == 403


def test_hrbp_can_create_workflow(org):
    hrbp = _client_for(org.hrbp)  # HRBP holds CONFIGURE_APPROVAL_WORKFLOW
    resp = hrbp.post(
        f"{APPROVALS}workflows", _seq_workflow_payload(active=False), format="json"
    )
    assert resp.status_code == 201


def test_activate_deactivate_endpoints_audit_and_flip(org):
    admin = _client_for(org.admin)
    wf_id = _post_seq_workflow(org, active=False)

    act = admin.post(f"{APPROVALS}workflows/{wf_id}/activate")
    assert act.status_code == 200
    assert act.json()["active"] is True

    deact = admin.post(f"{APPROVALS}workflows/{wf_id}/deactivate")
    assert deact.status_code == 200
    assert deact.json()["active"] is False

    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="workflow.activated").exists()
        assert AuditLog.objects.filter(action="workflow.deactivated").exists()


# ── 2. E2E SEQUENTIAL over HTTP through the review integration ────────────────


def test_e2e_sequential_route_over_http_finalises_the_review(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)

    # Finalize ENTERS the route: the review stays APPROVED, gains a route link.
    final = mgr.post(f"{REVIEWS}{review.id}/finalize")
    assert final.status_code == 200
    assert final.json()["state"] == "APPROVED"
    review.refresh_from_db()
    assert review.approval_route_id is not None

    # The assigned MANAGER (the subject's manager) sees step 1 in their inbox.
    mgr_inbox = mgr.get(f"{APPROVALS}inbox").json()
    assert len(mgr_inbox) == 1
    step1 = mgr_inbox[0]
    assert step1["order"] == 1
    assert step1["artifact_type"] == "review"
    assert step1["artifact_id"] == str(review.id)

    # Manager approves step 1 → 200.
    approve1 = mgr.post(f"{APPROVALS}steps/{step1['id']}/approve")
    assert approve1.status_code == 200
    assert approve1.json()["status"] == "APPROVED"

    # Now the HRBP step is active and appears in the HRBP inbox.
    hrbp_inbox = hrbp.get(f"{APPROVALS}inbox").json()
    assert len(hrbp_inbox) == 1
    step2 = hrbp_inbox[0]
    assert step2["order"] == 2

    # HRBP approves step 2 → route APPROVED → the review is FINALIZED.
    approve2 = hrbp.post(f"{APPROVALS}steps/{step2['id']}/approve")
    assert approve2.status_code == 200
    assert approve2.json()["status"] == "APPROVED"

    after = mgr.get(f"{REVIEWS}{review.id}").json()
    assert after["state"] == "FINALIZED"

    # Audit trail: route lifecycle + the step decisions.
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="route.started").exists()
        assert AuditLog.objects.filter(action="step.approved").count() == 2
        assert AuditLog.objects.filter(action="route.completed").exists()


# ── 3. OUT-OF-ORDER ───────────────────────────────────────────────────────────


def test_out_of_order_decision_is_409_illegal_decision(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)
    mgr.post(f"{REVIEWS}{review.id}/finalize")

    with tenant_context(org.tenant):
        review.refresh_from_db()
        step2_id = str(
            review.approval_route.step_instances.get(order=2).id
        )

    # HRBP approving step 2 while step 1 is still pending → 409 ILLEGAL_DECISION.
    resp = hrbp.post(f"{APPROVALS}steps/{step2_id}/approve")
    assert resp.status_code == 409
    assert resp.json()["code"] == "ILLEGAL_DECISION"


# ── 4. REJECT ─────────────────────────────────────────────────────────────────


def test_reject_returns_review_to_editing_and_allows_fresh_route(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    mgr = _client_for(org.manager)
    mgr.post(f"{REVIEWS}{review.id}/finalize")

    with tenant_context(org.tenant):
        review.refresh_from_db()
        step1_id = str(review.approval_route.step_instances.get(order=1).id)

    # Manager rejects step 1 → 200, route REJECTED, review back to EDITING.
    rej = mgr.post(
        f"{APPROVALS}steps/{step1_id}/reject", {"comment": "redo evidence"}, format="json"
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "REJECTED"
    assert mgr.get(f"{REVIEWS}{review.id}").json()["state"] == "EDITING"

    # A re-approved finalize starts a FRESH route (the first is terminal).
    review.refresh_from_db()
    sm.submit_for_review(review, org.manager, draft_body="v2")
    sm.approve(review, org.manager)
    mgr.post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        from apps.approvals.models import ApprovalRoute

        assert ApprovalRoute.objects.filter(artifact_id=review.id).count() == 2


# ── 5. ASSIGNMENT / RBAC ──────────────────────────────────────────────────────


def test_peer_manager_not_assigned_approver_gets_403(org):
    # A second MANAGER in the tenant who is NOT the subject's manager: holds
    # ACT_ON_APPROVAL_STEP but is not the assigned step-1 approver.
    peer_manager = UserFactory(tenant=org.tenant, role="MANAGER")
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    _client_for(org.manager).post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        review.refresh_from_db()
        step1_id = str(review.approval_route.step_instances.get(order=1).id)

    resp = _client_for(peer_manager).post(f"{APPROVALS}steps/{step1_id}/approve")
    assert resp.status_code == 403


def test_employee_cannot_act_on_step(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    _client_for(org.manager).post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        review.refresh_from_db()
        step1_id = str(review.approval_route.step_instances.get(order=1).id)

    # EMPLOYEE lacks ACT_ON_APPROVAL_STEP → fast-fail 403 (capability gate).
    resp = _client_for(org.report).post(f"{APPROVALS}steps/{step1_id}/approve")
    assert resp.status_code == 403


def test_cross_tenant_step_approve_is_404(org, other_tenant):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    _client_for(org.manager).post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        review.refresh_from_db()
        step1_id = str(review.approval_route.step_instances.get(order=1).id)

    # A manager in ANOTHER tenant: the scoped manager hides the row → 404.
    with tenant_context(other_tenant):
        outsider = UserFactory(tenant=other_tenant, role="MANAGER")
    resp = _client_for(outsider).post(f"{APPROVALS}steps/{step1_id}/approve")
    assert resp.status_code == 404


def test_cross_tenant_route_get_is_404(org, other_tenant):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    _client_for(org.manager).post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        review.refresh_from_db()
        route_id = str(review.approval_route_id)

    with tenant_context(other_tenant):
        outsider = UserFactory(tenant=other_tenant, role="ADMIN")
    resp = _client_for(outsider).get(f"{APPROVALS}routes/{route_id}")
    assert resp.status_code == 404


# ── 6. PARALLEL ───────────────────────────────────────────────────────────────


def test_parallel_workflow_both_slots_actionable_then_finalises(org):
    payload = {
        "name": "Parallel sign-off",
        "artifact_type": "review",
        "mode": "PARALLEL",
        "active": True,
        "steps": [
            {"order": 1, "approver_kind": "ROLE", "approver_role": "MANAGER", "required": True},
            {"order": 2, "approver_kind": "ROLE", "approver_role": "HRBP", "required": True},
        ],
    }
    assert (
        _client_for(org.admin)
        .post(f"{APPROVALS}workflows", payload, format="json")
        .status_code
        == 201
    )
    review = _approved_review(org)
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)
    mgr.post(f"{REVIEWS}{review.id}/finalize")

    # PARALLEL: BOTH slots are actionable at once.
    mgr_inbox = mgr.get(f"{APPROVALS}inbox").json()
    hrbp_inbox = hrbp.get(f"{APPROVALS}inbox").json()
    assert len(mgr_inbox) == 1 and mgr_inbox[0]["order"] == 1
    assert len(hrbp_inbox) == 1 and hrbp_inbox[0]["order"] == 2

    assert mgr.post(f"{APPROVALS}steps/{mgr_inbox[0]['id']}/approve").status_code == 200
    assert hrbp.post(f"{APPROVALS}steps/{hrbp_inbox[0]['id']}/approve").status_code == 200

    assert mgr.get(f"{REVIEWS}{review.id}").json()["state"] == "FINALIZED"


# ── 7. TRACKER visibility ─────────────────────────────────────────────────────


def test_route_tracker_visibility_rule(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    _client_for(org.manager).post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        review.refresh_from_db()
        route_id = str(review.approval_route_id)

    # The SUBJECT employee is neither initiator, approver, nor a config holder.
    assert (
        _client_for(org.report).get(f"{APPROVALS}routes/{route_id}").status_code == 403
    )
    # The initiator manager → 200.
    assert (
        _client_for(org.manager).get(f"{APPROVALS}routes/{route_id}").status_code == 200
    )
    # The HRBP (a config holder) → 200.
    assert _client_for(org.hrbp).get(f"{APPROVALS}routes/{route_id}").status_code == 200


def test_route_list_by_artifact_for_in_scope_viewer(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    mgr = _client_for(org.manager)
    mgr.post(f"{REVIEWS}{review.id}/finalize")
    with tenant_context(org.tenant):
        review.refresh_from_db()
        route_id = str(review.approval_route_id)

    rows = mgr.get(
        f"{APPROVALS}routes?artifact_type=review&artifact_id={review.id}"
    ).json()
    assert {r["id"] for r in rows} == {route_id}

    # Both query params are required.
    assert mgr.get(f"{APPROVALS}routes?artifact_type=review").status_code == 400


# ── 8. INBOX correctness (sequential waiting step not surfaced) ───────────────


def test_sequential_inbox_hides_waiting_step_until_active(org):
    _post_seq_workflow(org, active=True)
    review = _approved_review(org)
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)
    mgr.post(f"{REVIEWS}{review.id}/finalize")

    # While step 1 is pending, the HRBP's inbox is EMPTY (step 2 is waiting,
    # not actionable yet).
    assert hrbp.get(f"{APPROVALS}inbox").json() == []

    # After the manager approves step 1, step 2 surfaces for the HRBP.
    step1_id = mgr.get(f"{APPROVALS}inbox").json()[0]["id"]
    assert mgr.post(f"{APPROVALS}steps/{step1_id}/approve").status_code == 200

    hrbp_inbox = hrbp.get(f"{APPROVALS}inbox").json()
    assert len(hrbp_inbox) == 1
    assert hrbp_inbox[0]["order"] == 2
