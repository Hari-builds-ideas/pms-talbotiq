"""
Engine tests — auditable determinism is the showcase. Uses the registered TEST
"widget" artifact type (see conftest) so the engine is exercised independently of
the review consumer.
"""
import uuid

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.approvals import engine
from apps.approvals.exceptions import (
    ActiveRouteExists,
    IllegalDecision,
    RouteApproverUnresolvable,
)
from apps.approvals.models import (
    ApprovalRoute,
    ApprovalStep,
    ApprovalStepInstance,
    ApprovalWorkflow,
)
from apps.audit.models import AuditLog
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    ApprovalStepFactory,
    ApprovalWorkflowFactory,
    UserFactory,
)
from .conftest import COMPLETED, REJECTED

pytestmark = pytest.mark.django_db

R = ApprovalRoute.Status
SI = ApprovalStepInstance.Status


def _seq_manager_hrbp(org):
    """A SEQUENTIAL widget workflow: step1 ROLE=MANAGER, step2 ROLE=HRBP."""
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER")
    ApprovalStepFactory(workflow=wf, order=2, approver_kind="ROLE", approver_role="HRBP")
    return wf


def _start(org, artifact_id, initiated_by=None):
    with tenant_context(org.tenant):
        return engine.start_route(
            "widget", artifact_id, initiated_by=initiated_by or org.manager,
            tenant_id=str(org.tenant.id),
        )


# ── SEQUENTIAL ──────────────────────────────────────────────────────────────


def test_sequential_resolution_and_active_step(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        steps = list(route.step_instances.order_by("order"))
    assert route.mode == "SEQUENTIAL" and route.status == R.IN_PROGRESS
    assert steps[0].approver_id == org.manager.id  # MANAGER resolved to subject's manager
    assert steps[0].approver_role is None
    assert steps[1].approver is None and steps[1].approver_role == "HRBP"  # role-slot
    assert all(s.status == SI.PENDING for s in steps)


def test_sequential_out_of_order_rejected(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        step2 = route.step_instances.get(order=2)
    with pytest.raises(IllegalDecision):
        engine.record_decision(step2, org.hrbp, "APPROVE")  # step 1 not done


def test_sequential_full_approval_completes_and_fires_handler(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1, s2 = route.step_instances.order_by("order")
    engine.record_decision(s1, org.manager, "APPROVE")
    with tenant_context(org.tenant):
        route.refresh_from_db()
        assert route.status == R.IN_PROGRESS  # step 2 still pending
    engine.record_decision(s2, org.hrbp, "APPROVE")
    with tenant_context(org.tenant):
        route.refresh_from_db()
    assert route.status == R.APPROVED and route.completed_at is not None
    assert str(route.id) in COMPLETED and str(route.id) not in REJECTED


def test_sequential_reject_ends_route_and_fires_rejected(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    engine.record_decision(s1, org.manager, "REJECT", comment="not yet")
    with tenant_context(org.tenant):
        route.refresh_from_db()
        s2 = route.step_instances.get(order=2)
    assert route.status == R.REJECTED
    assert str(route.id) in REJECTED and str(route.id) not in COMPLETED
    assert s2.status == SI.PENDING  # never activated


# ── PARALLEL ────────────────────────────────────────────────────────────────


def _parallel(org):
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="PARALLEL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER", required=True)
    ApprovalStepFactory(workflow=wf, order=2, approver_kind="ROLE", approver_role="HRBP", required=True)
    ApprovalStepFactory(workflow=wf, order=3, approver_kind="ROLE", approver_role="ADMIN", required=False)
    return wf


def test_parallel_all_required_approve_completes(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _parallel(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        steps = {s.order: s for s in route.step_instances.all()}
        assert all(s.status == SI.PENDING for s in steps.values())  # all active at once
    engine.record_decision(steps[1], org.manager, "APPROVE")
    with tenant_context(org.tenant):
        route.refresh_from_db()
        assert route.status == R.IN_PROGRESS  # HRBP (required) still pending
    engine.record_decision(steps[2], org.hrbp, "APPROVE")  # last REQUIRED
    with tenant_context(org.tenant):
        route.refresh_from_db()
    assert route.status == R.APPROVED  # non-required ADMIN step does NOT block
    assert str(route.id) in COMPLETED


def test_parallel_required_reject_ends_route(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _parallel(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s2 = route.step_instances.get(order=2)
    engine.record_decision(s2, org.hrbp, "REJECT", comment="blocking")
    with tenant_context(org.tenant):
        route.refresh_from_db()
    assert route.status == R.REJECTED and str(route.id) in REJECTED


def test_parallel_non_required_does_not_block(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _parallel(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        steps = {s.order: s for s in route.step_instances.all()}
    # Approve only the two required steps; never touch the advisory ADMIN step.
    engine.record_decision(steps[1], org.manager, "APPROVE")
    engine.record_decision(steps[2], org.hrbp, "APPROVE")
    with tenant_context(org.tenant):
        route.refresh_from_db()
        admin_step = route.step_instances.get(order=3)
    assert route.status == R.APPROVED
    assert admin_step.status == SI.PENDING  # advisory, left undecided


# ── resolution edge cases ───────────────────────────────────────────────────


def test_named_step_resolves_to_specific_user(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="NAMED", approver_role=None, approver_user=org.hrbp)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        assert route.step_instances.get(order=1).approver_id == org.hrbp.id


def test_self_approval_resolves_to_escalation(org, widget):
    # A NAMED step pointing at the subject (protected) escalates to the target.
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(
        workflow=wf, order=1, approver_kind="NAMED", approver_role=None,
        approver_user=org.report, escalation_user=org.hrbp,
    )
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        step = route.step_instances.get(order=1)
    assert step.approver_id == org.hrbp.id  # NOT the subject
    assert step.escalated is True


def test_manager_step_falls_back_to_admin_slot_when_no_manager(org, widget):
    # subject has no manager and no escalation target on the step -> ADMIN slot.
    loner = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="loner@acme.test")  # manager=None
    artifact_id, set_ctx = widget
    set_ctx(subject=loner, manager=None, protected={loner.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER")
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        step = route.step_instances.get(order=1)
    # No manager + no escalation target -> ADMIN role-slot fallback (always resolvable).
    assert step.approver is None and step.approver_role == "ADMIN" and step.escalated is True


def test_unresolvable_raises_422_and_creates_no_route(org, widget):
    # A step with an unrecognised approver configuration cannot be resolved.
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="HRBP")
    ApprovalStepFactory(workflow=wf, order=2, approver_kind="ROLE", approver_role="BOGUS")
    with tenant_context(org.tenant):
        with pytest.raises(RouteApproverUnresolvable):
            engine.start_route(
                "widget", artifact_id, initiated_by=org.admin, tenant_id=str(org.tenant.id)
            )
        # No half-built route — resolution fails before any row is written.
        assert ApprovalRoute.objects.filter(artifact_id=artifact_id).count() == 0
        assert ApprovalStepInstance.objects.count() == 0


# ── authorization ───────────────────────────────────────────────────────────


def test_only_assigned_named_approver_can_decide(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="NAMED", approver_role=None, approver_user=org.hrbp)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    with pytest.raises(PermissionDenied):
        engine.record_decision(s1, org.manager, "APPROVE")  # not the named approver
    engine.record_decision(s1, org.hrbp, "APPROVE")  # the named approver
    with tenant_context(org.tenant):
        route.refresh_from_db()
    assert route.status == R.APPROVED


def test_role_slot_decidable_by_any_holder(org, widget, make_user):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="HRBP")
    route = _start(org, artifact_id)
    other_hrbp = make_user(tenant=org.tenant, role="HRBP", email="hrbp2@acme.test")
    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    # An employee cannot fill the HRBP slot.
    with pytest.raises(PermissionDenied):
        engine.record_decision(s1, org.report, "APPROVE")
    # Any HRBP in the tenant can.
    engine.record_decision(s1, other_hrbp, "APPROVE")
    with tenant_context(org.tenant):
        s1.refresh_from_db()
    assert s1.decided_by_id == other_hrbp.id


def test_protected_subject_cannot_decide_role_slot(org, widget, make_user):
    # The subject happens to be an HRBP; they still can't act on their own artifact.
    hrbp_subject = make_user(tenant=org.tenant, role="HRBP", email="subjisharbp@acme.test")
    artifact_id, set_ctx = widget
    set_ctx(subject=hrbp_subject, manager=org.manager, protected={hrbp_subject.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="HRBP")
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    with pytest.raises(PermissionDenied):
        engine.record_decision(s1, hrbp_subject, "APPROVE")  # self-approval blocked


def test_cross_tenant_actor_cannot_decide(org, other_tenant, widget, make_user):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="HRBP")
    route = _start(org, artifact_id)
    outsider_hrbp = make_user(tenant=other_tenant, role="HRBP", email="out@other.test")
    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    with pytest.raises(PermissionDenied):
        engine.record_decision(s1, outsider_hrbp, "APPROVE")  # different tenant


# ── idempotency + state guards ──────────────────────────────────────────────


def test_redecide_and_double_complete_rejected(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1, s2 = route.step_instances.order_by("order")
    engine.record_decision(s1, org.manager, "APPROVE")
    with tenant_context(org.tenant):
        s1.refresh_from_db()
    with pytest.raises(IllegalDecision):
        engine.record_decision(s1, org.manager, "APPROVE")  # already decided
    engine.record_decision(s2, org.hrbp, "APPROVE")  # completes route
    with tenant_context(org.tenant):
        s2.refresh_from_db()
    with pytest.raises(IllegalDecision):
        engine.record_decision(s2, org.hrbp, "APPROVE")  # route not in progress


def test_second_route_for_artifact_blocked(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    _start(org, artifact_id)
    with pytest.raises(ActiveRouteExists):
        _start(org, artifact_id)


def test_activate_deactivates_prior(org):
    wf1 = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", active=True)
    wf2 = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", active=False)
    engine.activate_workflow(wf2)
    with tenant_context(org.tenant):
        wf1.refresh_from_db()
        wf2.refresh_from_db()
    assert wf2.active is True and wf1.active is False
    assert engine.active_workflow_for(str(org.tenant.id), "widget").id == wf2.id


# ── audit before effect ─────────────────────────────────────────────────────


def test_audit_written_for_route_and_decisions(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1, s2 = route.step_instances.order_by("order")
    engine.record_decision(s1, org.manager, "APPROVE")
    engine.record_decision(s2, org.hrbp, "APPROVE")
    with tenant_context(org.tenant):
        actions = set(
            AuditLog.objects.filter(target_id=str(route.id)).values_list("action", flat=True)
        )
    assert {"route.started", "step.approved", "route.completed"} <= actions


def test_audit_precedes_state_change(org, widget, monkeypatch):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_hrbp(org)
    route = _start(org, artifact_id)
    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    original = ApprovalStepInstance.save

    def boom(self, *a, **k):
        raise RuntimeError("crash after audit, before persist")

    monkeypatch.setattr(ApprovalStepInstance, "save", boom)
    with pytest.raises(RuntimeError):
        engine.record_decision(s1, org.manager, "APPROVE")
    monkeypatch.setattr(ApprovalStepInstance, "save", original)
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(target_id=str(route.id), action="step.approved").exists()
        s1.refresh_from_db()
    assert s1.status == SI.PENDING  # effect did not apply


# ── escalation ──────────────────────────────────────────────────────────────


def test_escalate_overdue_step_reassigns_to_target(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(
        workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER",
        timeout_hours=24, escalation_role="HRBP",
    )
    route = _start(org, artifact_id)
    from django.utils import timezone

    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
        assert s1.approver_id == org.manager.id and s1.due_at is not None
        # Force overdue.
        s1.due_at = timezone.now() - timezone.timedelta(hours=1)
        s1.save(update_fields=["due_at"])
    overdue = engine.overdue_pending_steps()
    assert any(s.id == s1.id for s in overdue)
    engine.escalate_step(s1)
    with tenant_context(org.tenant):
        s1.refresh_from_db()
        escalated_audit = AuditLog.objects.filter(
            target_id=str(route.id), action="step.escalated"
        ).exists()
    assert s1.escalated is True
    assert s1.approver is None and s1.approver_role == "HRBP"  # reassigned to HRBP slot
    assert escalated_audit
