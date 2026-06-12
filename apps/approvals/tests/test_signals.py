"""
The approval engine fires the Module-12 notification signals (best-effort,
``send_robust``): ``approval_step_assigned`` when a step becomes active (route
start + next-step activation) and ``approval_step_escalated`` on escalation. The
engine itself stays unaware of Slack — integrations subscribes elsewhere.
"""
import pytest

from apps.approvals import engine
from apps.approvals.signals import approval_step_assigned, approval_step_escalated
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import ApprovalStepFactory, ApprovalWorkflowFactory

pytestmark = pytest.mark.django_db


def _sequential_widget_workflow(org):
    wf = ApprovalWorkflowFactory(tenant=org.tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="MANAGER")
    ApprovalStepFactory(workflow=wf, order=2, approver_kind="ROLE", approver_role="HRBP")
    return wf


def test_start_route_fires_assignment_for_the_active_step(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager)
    _sequential_widget_workflow(org)

    captured = []
    approval_step_assigned.connect(
        lambda sender, **kw: captured.append(kw), dispatch_uid="t_assign", weak=False
    )
    try:
        with tenant_context(org.tenant):
            engine.start_route(
                "widget", artifact_id, initiated_by=org.admin, tenant_id=str(org.tenant.id)
            )
    finally:
        approval_step_assigned.disconnect(dispatch_uid="t_assign")

    # SEQUENTIAL: only step 1 is active at start → exactly one assignment signal.
    assert len(captured) == 1
    assert captured[0]["order"] == 1
    assert captured[0]["artifact_type"] == "widget"


def test_escalate_step_fires_escalation_signal(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager)
    _sequential_widget_workflow(org)

    captured = []
    approval_step_escalated.connect(
        lambda sender, **kw: captured.append(kw), dispatch_uid="t_esc", weak=False
    )
    try:
        with tenant_context(org.tenant):
            route = engine.start_route(
                "widget", artifact_id, initiated_by=org.admin, tenant_id=str(org.tenant.id)
            )
            active = route.step_instances.order_by("order").first()
            engine.escalate_step(active)  # no explicit target → ADMIN-slot fallback
    finally:
        approval_step_escalated.disconnect(dispatch_uid="t_esc")

    assert len(captured) == 1
    assert captured[0]["order"] == 1
