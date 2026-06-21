"""
The approval engine fires the Module-12 notification signals (best-effort,
``send_robust``): ``approval_step_assigned`` when a step becomes active (route
start + next-step activation) and ``approval_step_escalated`` on escalation. The
engine itself stays unaware of Slack — integrations subscribes elsewhere.
"""
from unittest.mock import patch

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


# ── notification GENERATION: signal → integrations receiver → Slack notifier ──


def test_route_start_generates_an_assignment_notification(org, widget):
    """End-to-end: route start fires approval_step_assigned, and the integrations
    receiver actually invokes the Slack notifier — the notification is GENERATED on
    the event (not just the signal fired)."""
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager)
    _sequential_widget_workflow(org)
    with patch("apps.integrations.receivers.notify_approval_assignment") as notify:
        with tenant_context(org.tenant):
            engine.start_route(
                "widget", artifact_id, initiated_by=org.admin, tenant_id=str(org.tenant.id)
            )
    assert notify.called
    assert notify.call_args.kwargs["order"] == 1


def test_escalation_generates_an_escalation_notification(org, widget):
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager)
    _sequential_widget_workflow(org)
    with patch("apps.integrations.receivers.notify_approval_escalation") as notify:
        with tenant_context(org.tenant):
            route = engine.start_route(
                "widget", artifact_id, initiated_by=org.admin, tenant_id=str(org.tenant.id)
            )
            engine.escalate_step(route.step_instances.order_by("order").first())
    assert notify.called
