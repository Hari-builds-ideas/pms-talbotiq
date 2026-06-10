"""
Module 6 ↔ Module 5: JD is the SECOND consumer of the approval engine, proving
it is generic. Opt-in routing mirrors reviews exactly:

* No active "jd" workflow  -> approve single-step PUBLISHES (Module-6 default).
* An active "jd" workflow   -> approve ENTERS the route (status IN_REVIEW); route
  completion PUBLISHES via the audited lifecycle; route rejection returns the JD
  to PENDING_HUMAN_REVIEW for the author.

Self-approval block: the JD author is in ``protected_user_ids`` and can never
decide their own JD's route (the engine refuses with 403), even when they hold
the step's role-slot. A subject-less JD has no manager, so a ROLE=MANAGER step
falls back to the engine's universal ADMIN slot (it is NOT unresolvable — that
fallback is the engine's documented behaviour).
"""
import pytest

from apps.approvals import engine
from apps.approvals.exceptions import RouteApproverUnresolvable
from apps.approvals.models import ApprovalRoute
from apps.jd import lifecycle
from apps.jd.models import JobDescription
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import ApprovalStepFactory, ApprovalWorkflowFactory
from rest_framework.exceptions import PermissionDenied

pytestmark = pytest.mark.django_db

S = JobDescription.Status

_BODY = {
    "summary": "Leads the data platform.",
    "responsibilities": ["Own the warehouse"],
    "must_haves": ["SQL"],
}


def _pending_jd(org, author=None):
    jd = lifecycle.create_jd(
        title="Data Lead", level="L5", actor=author or org.hrbp, body=dict(_BODY)
    )
    lifecycle.submit_for_review(jd, author or org.hrbp)
    return jd


def _jd_workflow(org, *, mode="SEQUENTIAL", role="HRBP"):
    wf = ApprovalWorkflowFactory(
        tenant=org.tenant, artifact_type="jd", mode=mode, active=True
    )
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role=role)
    return wf


def test_no_workflow_single_step_publishes(org):
    jd = _pending_jd(org)
    lifecycle.approve(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.PUBLISHED
    assert jd.approval_route_id is None


def test_active_workflow_routes_instead_of_publishing(org):
    _jd_workflow(org)
    # Author is the manager so the HRBP can legitimately approve the route step.
    jd = _pending_jd(org, author=org.manager)
    lifecycle.approve(jd, org.manager)
    jd.refresh_from_db()
    assert jd.status == S.IN_REVIEW
    assert jd.current_version_id is None  # NOT published yet
    assert jd.approval_route_id is not None
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=jd.approval_route_id)
        assert route.status == "IN_PROGRESS" and route.artifact_type == "jd"


def test_route_completion_publishes_via_lifecycle(org):
    _jd_workflow(org)
    jd = _pending_jd(org, author=org.manager)
    lifecycle.approve(jd, org.manager)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=jd.approval_route_id)
        step = route.step_instances.get(order=1)
    engine.record_decision(step, org.hrbp, "APPROVE")
    jd.refresh_from_db()
    assert jd.status == S.PUBLISHED
    assert jd.approval_route_id is None
    with tenant_context(org.tenant):
        assert jd.current_version.is_published is True


def test_route_rejection_returns_to_pending_and_allows_fresh_route(org):
    _jd_workflow(org)
    jd = _pending_jd(org, author=org.manager)
    lifecycle.approve(jd, org.manager)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=jd.approval_route_id)
        step = route.step_instances.get(order=1)
    engine.record_decision(step, org.hrbp, "REJECT", comment="needs scope")
    jd.refresh_from_db()
    assert jd.status == S.PENDING_HUMAN_REVIEW  # returned to the author
    assert jd.approval_route_id is None
    with tenant_context(org.tenant):
        assert jd.current_version_id is None  # never published

    # Re-approve starts a FRESH route (the first is terminal/REJECTED).
    lifecycle.approve(jd, org.manager)
    with tenant_context(org.tenant):
        assert ApprovalRoute.objects.filter(artifact_id=jd.id).count() == 2


def test_author_cannot_approve_own_jd_route(org):
    """Self-approval block: the HRBP who authored the JD holds the HRBP slot but
    is protected, so the engine refuses their decision (403). A DIFFERENT HRBP
    can act."""
    _jd_workflow(org, role="HRBP")
    author_hrbp = org.hrbp
    jd = _pending_jd(org, author=author_hrbp)
    lifecycle.approve(jd, author_hrbp)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=jd.approval_route_id)
        step = route.step_instances.get(order=1)
    with pytest.raises(PermissionDenied):
        engine.record_decision(step, author_hrbp, "APPROVE")
    # A different HRBP-slot holder (Admin holds no HRBP role, so add one) acts.
    from apps.testsupport.factories import UserFactory

    other_hrbp = UserFactory(tenant=org.tenant, role="HRBP", email="hrbp2@acme.test")
    engine.record_decision(step, other_hrbp, "APPROVE")
    jd.refresh_from_db()
    assert jd.status == S.PUBLISHED


def test_manager_step_falls_back_to_admin_for_subjectless_jd(org):
    """A JD has no employee subject, so a ROLE=MANAGER step has no manager to
    resolve to and falls back to the engine's universal ADMIN slot (escalated).
    The tenant Admin completes it -> publish."""
    _jd_workflow(org, role="MANAGER")
    jd = _pending_jd(org, author=org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    with tenant_context(org.tenant):
        route = ApprovalRoute.objects.get(id=jd.approval_route_id)
        step = route.step_instances.get(order=1)
        assert step.approver_id is None
        assert step.approver_role == "ADMIN"
        assert step.escalated is True
    engine.record_decision(step, org.admin, "APPROVE")
    jd.refresh_from_db()
    assert jd.status == S.PUBLISHED


def test_unrecognised_approver_config_is_unresolvable(org):
    """The genuine 422 path: a ROLE step whose role is neither MANAGER nor an
    HRBP/ADMIN slot cannot be resolved — start_route raises before any row is
    written, and the JD stays PENDING_HUMAN_REVIEW."""
    wf = ApprovalWorkflowFactory(
        tenant=org.tenant, artifact_type="jd", mode="SEQUENTIAL", active=True
    )
    ApprovalStepFactory(workflow=wf, order=1, approver_kind="ROLE", approver_role="EMPLOYEE")
    jd = _pending_jd(org, author=org.hrbp)
    with pytest.raises(RouteApproverUnresolvable):
        lifecycle.approve(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.PENDING_HUMAN_REVIEW  # no partial route, no state change
    with tenant_context(org.tenant):
        assert ApprovalRoute.objects.filter(artifact_id=jd.id).count() == 0
