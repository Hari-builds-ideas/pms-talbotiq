"""
Escalation beat-task tests — the periodic sweep that reassigns overdue PENDING
steps to their escalation target.

These exercise ``apps.approvals.tasks.escalate_overdue_routes`` (the celery-beat
task) on top of the engine, using the registered TEST "widget" artifact type (see
conftest) so the sweep is verified independently of any real consumer. The task
runs OFF-REQUEST, so the multi-tenant test asserts it binds each tenant itself
and leaks no ambient tenant context.
"""
import uuid

import pytest
from django.utils import timezone

from apps.approvals import engine
from apps.approvals.models import ApprovalRoute, ApprovalStepInstance
from apps.approvals.tasks import escalate_overdue_routes
from apps.audit.models import AuditLog
from apps.tenancy.context import get_current_tenant_id, tenant_context
from apps.testsupport.factories import (
    ApprovalStepFactory,
    ApprovalWorkflowFactory,
    TenantFactory,
    UserFactory,
)
from .conftest import WIDGETS

pytestmark = pytest.mark.django_db

R = ApprovalRoute.Status
SI = ApprovalStepInstance.Status


# ── helpers ──────────────────────────────────────────────────────────────────


def _register_widget(*, subject=None, manager=None, protected=()):
    """Register an ad-hoc widget artifact and return its id.

    Mirrors the ``widget`` fixture for cases that need more than one artifact
    (e.g. a second tenant). The "widget" handler is registered globally by
    conftest; only the per-artifact context lives in WIDGETS, so we add/remove a
    single entry here. Callers clean up via the returned id when needed.
    """
    artifact_id = str(uuid.uuid4())
    WIDGETS[artifact_id] = {
        "subject": subject,
        "manager": manager,
        "protected": set(protected),
    }
    return artifact_id


def _seq_manager_step(tenant, *, timeout_hours=24, escalation_role="HRBP"):
    """A SEQUENTIAL widget workflow whose step-1 is ROLE=MANAGER with a timeout."""
    wf = ApprovalWorkflowFactory(tenant=tenant, artifact_type="widget", mode="SEQUENTIAL")
    ApprovalStepFactory(
        workflow=wf,
        order=1,
        approver_kind="ROLE",
        approver_role="MANAGER",
        timeout_hours=timeout_hours,
        escalation_role=escalation_role,
    )
    return wf


def _start(tenant, artifact_id, initiated_by):
    with tenant_context(tenant):
        return engine.start_route(
            "widget", artifact_id, initiated_by=initiated_by, tenant_id=str(tenant.id)
        )


def _force_overdue(tenant, step_id, hours=1):
    """Push a step's due_at into the past so the sweep treats it as overdue."""
    with tenant_context(tenant):
        step = ApprovalStepInstance.objects.get(id=step_id)
        step.due_at = timezone.now() - timezone.timedelta(hours=hours)
        step.save(update_fields=["due_at"])


# ── core escalation ────────────────────────────────────────────────────────


def test_sweep_escalates_overdue_step_and_audits(org, widget):
    """An overdue step-1 (ROLE=MANAGER, escalation_role=HRBP) is reassigned to the
    HRBP slot, the route stays IN_PROGRESS, and a step.escalated audit row exists."""
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_step(org.tenant, escalation_role="HRBP")
    route = _start(org.tenant, artifact_id, initiated_by=org.manager)

    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
        assert s1.approver_id == org.manager.id and s1.due_at is not None
    _force_overdue(org.tenant, s1.id)

    summary = escalate_overdue_routes()

    with tenant_context(org.tenant):
        s1.refresh_from_db()
        route.refresh_from_db()
        escalated_audit = AuditLog.objects.filter(
            target_id=str(route.id), action="step.escalated"
        ).exists()
    assert s1.escalated is True
    assert s1.approver is None and s1.approver_role == "HRBP"  # reassigned to HRBP slot
    assert s1.status == SI.PENDING  # still awaiting a decision, just by the new target
    assert route.status == R.IN_PROGRESS
    assert escalated_audit
    assert summary["scanned"] >= 1 and summary["escalated"] >= 1


def test_sweep_ignores_step_not_yet_due(org, widget):
    """A step whose due_at is in the future is left untouched by the sweep."""
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_step(org.tenant)
    route = _start(org.tenant, artifact_id, initiated_by=org.manager)

    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
        # due_at is in the future (timeout_hours=24 from start) — leave it.
        assert s1.due_at > timezone.now()

    escalate_overdue_routes()

    with tenant_context(org.tenant):
        s1.refresh_from_db()
    assert s1.escalated is False
    assert s1.approver_id == org.manager.id  # not reassigned


def test_sweep_ignores_step_with_no_timeout(org, widget):
    """A step with no timeout configured has no due_at and is never escalated."""
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    # No timeout_hours -> no due_at -> never picked up by the sweep.
    _seq_manager_step(org.tenant, timeout_hours=None)
    route = _start(org.tenant, artifact_id, initiated_by=org.manager)

    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
        assert s1.due_at is None

    escalate_overdue_routes()

    with tenant_context(org.tenant):
        s1.refresh_from_db()
    assert s1.escalated is False
    assert s1.approver_id == org.manager.id


def test_sweep_skips_already_decided_step(org, widget):
    """A step already APPROVED is a no-op for the sweep even if its due_at is past."""
    artifact_id, set_ctx = widget
    set_ctx(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_step(org.tenant)
    route = _start(org.tenant, artifact_id, initiated_by=org.manager)

    with tenant_context(org.tenant):
        s1 = route.step_instances.get(order=1)
    # Decide the only step, completing the route.
    engine.record_decision(s1, org.manager, "APPROVE")
    # Then force its due_at into the past — overdue_pending_steps filters on
    # PENDING, so a decided step is never returned; belt-and-braces here.
    with tenant_context(org.tenant):
        s1.refresh_from_db()
        assert s1.status == SI.APPROVED
        s1.due_at = timezone.now() - timezone.timedelta(hours=1)
        s1.save(update_fields=["due_at"])

    escalate_overdue_routes()

    with tenant_context(org.tenant):
        s1.refresh_from_db()
        route.refresh_from_db()
        escalated_audit = AuditLog.objects.filter(
            target_id=str(route.id), action="step.escalated"
        ).exists()
    assert s1.escalated is False  # untouched
    assert s1.decided_by_id == org.manager.id
    assert route.status == R.APPROVED  # left completed
    assert escalated_audit is False  # the sweep never escalated it


# ── multi-tenant, off-request ────────────────────────────────────────────────


def test_sweep_escalates_across_tenants_without_leaking_context(org, widget):
    """OFF-REQUEST sweep: overdue steps in TWO tenants both escalate, with NO
    ambient tenant bound. The task must bind each tenant itself and leak none."""
    # Tenant A — the `org` fixture, via the `widget` fixture.
    a_artifact, set_a = widget
    set_a(subject=org.report, manager=org.manager, protected={org.report.id})
    _seq_manager_step(org.tenant, escalation_role="HRBP")
    route_a = _start(org.tenant, a_artifact, initiated_by=org.manager)

    # Tenant B — a fully independent tenant + reporting line + its own widget.
    tenant_b = TenantFactory(slug="beta", name="Beta")
    b_manager = UserFactory(tenant=tenant_b, role="MANAGER", email="mgr@beta.test")
    b_report = UserFactory(
        tenant=tenant_b, role="EMPLOYEE", email="rep@beta.test", manager=b_manager
    )
    b_artifact = _register_widget(
        subject=b_report, manager=b_manager, protected={b_report.id}
    )
    try:
        _seq_manager_step(tenant_b, escalation_role="HRBP")
        route_b = _start(tenant_b, b_artifact, initiated_by=b_manager)

        with tenant_context(org.tenant):
            sa = route_a.step_instances.get(order=1)
        with tenant_context(tenant_b):
            sb = route_b.step_instances.get(order=1)
        _force_overdue(org.tenant, sa.id)
        _force_overdue(tenant_b, sb.id)

        # No ambient tenant bound — exactly how celery-beat invokes it.
        assert get_current_tenant_id() is None
        summary = escalate_overdue_routes()
        # The sweep must not leak any bound tenant back to the caller.
        assert get_current_tenant_id() is None

        with tenant_context(org.tenant):
            sa.refresh_from_db()
        with tenant_context(tenant_b):
            sb.refresh_from_db()
        assert sa.escalated is True and sa.approver_role == "HRBP"
        assert sb.escalated is True and sb.approver_role == "HRBP"
        assert summary["scanned"] >= 2 and summary["escalated"] >= 2
        assert summary["errors"] == 0
    finally:
        WIDGETS.pop(b_artifact, None)


# ── summary shape ────────────────────────────────────────────────────────────


def test_summary_dict_shape_on_empty_sweep():
    """With no overdue steps the task still returns the full, sane summary dict."""
    summary = escalate_overdue_routes()
    assert set(summary) == {"scanned", "escalated", "errors"}
    assert all(isinstance(summary[k], int) and summary[k] >= 0 for k in summary)
    assert summary["escalated"] + summary["errors"] <= summary["scanned"]
