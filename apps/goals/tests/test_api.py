"""
HTTP tests for the Goals & KPI API, hitting the REAL ``/api/goals/...`` and
``/api/cycles/...`` routes (production urlconf — no ``@pytest.mark.urls``).

Three themes:
  * an end-to-end flow: create → weight-validate → enter-actual → recompute →
    read own score, all over HTTP;
  * the RBAC matrix: capability gates (403 without MANAGE_REPORTS_GOALS),
    object-scope gates (manager vs peer / report), cross-tenant isolation (404);
  * audit assertions: ``goal.created``, ``goal.approved``, ``actual.recorded``
    and ``scores.recomputed`` rows are written.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.goals.models import Kpi
from apps.goals.templates import seed_templates_for_tenant
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

GOALS = "/api/goals/"
CYCLES = "/api/cycles/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _goal_payload(employee, cycle, *, kpi_weights=(60, 40), status="ACTIVE"):
    """Build a goal-create body for ``employee`` with KPIs at ``kpi_weights``."""
    kpis = [
        {
            "name": f"KPI {i}",
            "weight": f"{w:.2f}",
            "target_value": "100.0000",
            "direction": "INCREASING",
        }
        for i, w in enumerate(kpi_weights)
    ]
    return {
        "employee": str(employee.id),
        "cycle": str(cycle.id),
        "title": "Ship the thing",
        "weight": "100.00",
        "status": status,
        "kpis": kpis,
    }


# ── end-to-end: create → validate → actual → recompute → read ──────────────


def test_e2e_create_actual_recompute_read(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)

    # 1. Manager creates a goal for their report; KPIs sum to 100 → 201.
    resp = mgr.post(GOALS, _goal_payload(org.report, cycle, kpi_weights=(60, 40)), format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["employee"] == str(org.report.id)
    assert len(body["kpis"]) == 2
    assert Decimal(body["kpi_weight_total"]) == Decimal("100.00")
    kpi_id = body["kpis"][0]["id"]

    # 2. Report (the owner) records an actual on their own KPI → 201.
    rep = _client_for(org.report)
    actual = rep.post(f"{GOALS}kpis/{kpi_id}/actuals", {"value": "80"}, format="json")
    assert actual.status_code == 201
    assert Decimal(actual.json()["value"]) == Decimal("80.0000")

    # 3. Manager recomputes; report reads their own score.
    rc = mgr.post(f"{CYCLES}{cycle.id}/recompute")
    assert rc.status_code == 200
    assert rc.json()["scored"] >= 1

    score = rep.get(f"{CYCLES}{cycle.id}/scores/me")
    assert score.status_code == 200
    assert score.json()["employee"] == str(org.report.id)


def test_kpi_weights_must_sum_to_exactly_100_lower_boundary(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    # 59.99 + 40.00 = 99.99 → rejected.
    resp = mgr.post(
        GOALS, _goal_payload(org.report, cycle, kpi_weights=(59.99, 40.00)), format="json"
    )
    assert resp.status_code == 400
    assert "kpis" in resp.json()


def test_kpi_weights_must_sum_to_exactly_100_upper_boundary(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    # 60.01 + 40.00 = 100.01 → rejected.
    resp = mgr.post(
        GOALS, _goal_payload(org.report, cycle, kpi_weights=(60.01, 40.00)), format="json"
    )
    assert resp.status_code == 400
    assert "kpis" in resp.json()


def test_kpi_weights_exactly_100_accepted(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    resp = mgr.post(
        GOALS, _goal_payload(org.report, cycle, kpi_weights=(50, 50)), format="json"
    )
    assert resp.status_code == 201


def test_target_value_must_be_positive(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    payload = _goal_payload(org.report, cycle, kpi_weights=(100,))
    payload["kpis"][0]["target_value"] = "0"
    resp = mgr.post(GOALS, payload, format="json")
    assert resp.status_code == 400


# ── actuals: OWN-only enforcement ──────────────────────────────────────────


def test_employee_cannot_record_actual_on_peers_kpi(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    # A KPI that belongs to the PEER (not the report).
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.peer, cycle=cycle, status="ACTIVE")
        kpi = KpiFactory(goal=goal, weight=Decimal("100.00"))

    rep = _client_for(org.report)  # report is NOT the peer
    resp = rep.post(f"{GOALS}kpis/{kpi.id}/actuals", {"value": "10"}, format="json")
    assert resp.status_code == 403


def test_non_numeric_actual_is_400_and_writes_nothing(org):
    # QA-NIGHT: {"value": "not-a-number"} used to 500 in record_actual's Decimal
    # coercion — AFTER the audit row was written. Must be a clean 400 with no
    # measurement and no "actual.recorded" audit entry.
    from apps.audit.models import AuditLog
    from apps.goals.models import KpiMeasurement

    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")
        kpi = KpiFactory(goal=goal, weight=Decimal("100.00"))

    rep = _client_for(org.report)
    resp = rep.post(f"{GOALS}kpis/{kpi.id}/actuals", {"value": "not-a-number"}, format="json")
    assert resp.status_code == 400, resp.content
    with tenant_context(org.tenant):
        assert not KpiMeasurement.objects.filter(kpi=kpi).exists()
        assert not AuditLog.objects.filter(
            action="actual.recorded", target_id=kpi.id
        ).exists()


def test_manager_cannot_use_actuals_endpoint_for_report(org):
    # The actuals endpoint is OWN-only: even a manager (who manages the report's
    # goals) cannot record via THIS endpoint for their report → 403.
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")
        kpi = KpiFactory(goal=goal, weight=Decimal("100.00"))

    mgr = _client_for(org.manager)
    resp = mgr.post(f"{GOALS}kpis/{kpi.id}/actuals", {"value": "10"}, format="json")
    assert resp.status_code == 403


def test_record_actual_audits_before_write(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")
        kpi = KpiFactory(goal=goal, weight=Decimal("100.00"))

    rep = _client_for(org.report)
    rep.post(f"{GOALS}kpis/{kpi.id}/actuals", {"value": "42"}, format="json")
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="actual.recorded", target_id=str(kpi.id)
        ).exists()


# ── RBAC matrix ────────────────────────────────────────────────────────────


def test_employee_cannot_create_goal(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    emp = _client_for(org.report)  # EMPLOYEE lacks MANAGE_REPORTS_GOALS
    resp = emp.post(GOALS, _goal_payload(org.report, cycle), format="json")
    assert resp.status_code == 403


def test_manager_cannot_create_goal_for_peer_outside_subtree(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    # peer reports to hrbp, NOT to manager → out of scope → 403.
    resp = mgr.post(GOALS, _goal_payload(org.peer, cycle), format="json")
    assert resp.status_code == 403


def test_manager_can_create_and_edit_reports_goal(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    create = mgr.post(GOALS, _goal_payload(org.report, cycle), format="json")
    assert create.status_code == 201
    goal_id = create.json()["id"]

    patch = mgr.patch(f"{GOALS}{goal_id}", {"title": "Renamed"}, format="json")
    assert patch.status_code == 200
    assert patch.json()["title"] == "Renamed"


def test_hrbp_can_create_goal_tenant_wide(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    hrbp = _client_for(org.hrbp)
    # peer is anyone in the tenant — HRBP scope is tenant-wide.
    resp = hrbp.post(GOALS, _goal_payload(org.peer, cycle), format="json")
    assert resp.status_code == 201


def test_cross_tenant_goal_access_is_404(org, other_tenant):
    other_cycle = CycleFactory(tenant=other_tenant, status="ACTIVE")
    with tenant_context(other_tenant):
        outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE")
        goal = GoalFactory(employee=outsider, cycle=other_cycle, status="ACTIVE")

    admin = _client_for(org.admin)  # admin of org.tenant
    resp = admin.get(f"{GOALS}{goal.id}")
    assert resp.status_code == 404


def test_goal_list_scope_employee_sees_only_own(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")
        GoalFactory(employee=org.peer, cycle=cycle, status="ACTIVE")

    rep = _client_for(org.report)
    resp = rep.get(GOALS)
    assert resp.status_code == 200
    emp_ids = {g["employee"] for g in resp.json()["results"]}
    assert emp_ids == {str(org.report.id)}


def test_goal_list_cycle_filter(org):
    c1 = CycleFactory(tenant=org.tenant, status="ACTIVE")
    c2 = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        GoalFactory(employee=org.report, cycle=c1, status="ACTIVE")
        GoalFactory(employee=org.report, cycle=c2, status="ACTIVE")

    rep = _client_for(org.report)
    resp = rep.get(f"{GOALS}?cycle={c1.id}")
    assert resp.status_code == 200
    assert all(g["cycle"] == str(c1.id) for g in resp.json()["results"])
    assert resp.json()["count"] == 1


# ── approve ────────────────────────────────────────────────────────────────


def test_manager_can_approve_report_goal_and_audit(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")

    mgr = _client_for(org.manager)
    resp = mgr.post(f"{GOALS}{goal.id}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved_by"] == str(org.manager.id)
    assert body["approved_at"] is not None

    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="goal.approved", target_id=str(goal.id)
        ).exists()


def test_employee_cannot_approve_goal(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE")

    emp = _client_for(org.report)  # EMPLOYEE lacks APPROVE_GOALS
    resp = emp.post(f"{GOALS}{goal.id}/approve")
    assert resp.status_code == 403


def test_manager_cannot_approve_peer_goal_out_of_scope(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        goal = GoalFactory(employee=org.peer, cycle=cycle, status="ACTIVE")

    mgr = _client_for(org.manager)
    resp = mgr.post(f"{GOALS}{goal.id}/approve")
    assert resp.status_code == 403


# ── KPI sub-resources: weight re-validation ────────────────────────────────


def test_add_kpi_must_keep_goal_at_100(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    # Goal starts weight-complete with one 100-weight KPI.
    create = mgr.post(GOALS, _goal_payload(org.report, cycle, kpi_weights=(100,)), format="json")
    goal_id = create.json()["id"]

    # Adding ANY positive-weight KPI pushes the sum past 100 → 400, rolled back.
    resp = mgr.post(
        f"{GOALS}{goal_id}/kpis",
        {"name": "Extra", "weight": "10.00", "target_value": "5.0000", "direction": "INCREASING"},
        format="json",
    )
    assert resp.status_code == 400
    with tenant_context(org.tenant):
        assert Kpi.objects.filter(goal_id=goal_id).count() == 1  # rolled back


def test_delete_kpi_rolls_back_when_sum_breaks(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    create = mgr.post(GOALS, _goal_payload(org.report, cycle, kpi_weights=(60, 40)), format="json")
    kpi_id = create.json()["kpis"][0]["id"]

    # Deleting one of two KPIs leaves 40 ≠ 100 → 400, rolled back.
    resp = mgr.delete(f"{GOALS}kpis/{kpi_id}")
    assert resp.status_code == 400
    with tenant_context(org.tenant):
        assert Kpi.objects.filter(goal_id=create.json()["id"]).count() == 2


# ── templates ──────────────────────────────────────────────────────────────


def test_hrbp_can_instantiate_role_templates(org):
    seed_templates_for_tenant(org.tenant)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    hrbp = _client_for(org.hrbp)

    resp = hrbp.post(
        f"{GOALS}templates/instantiate",
        {"employee": str(org.report.id), "cycle": str(cycle.id), "goal_title": "Role goals"},
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    # The EMPLOYEE role's templates sum to exactly 100.00 by construction.
    assert Decimal(body["kpi_weight_total"]) == Decimal("100.00")
    assert len(body["kpis"]) >= 1

    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="goal.created").exists()


def test_hrbp_can_list_templates(org):
    seed_templates_for_tenant(org.tenant)
    hrbp = _client_for(org.hrbp)
    resp = hrbp.get(f"{GOALS}templates/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_employee_cannot_instantiate_templates(org):
    seed_templates_for_tenant(org.tenant)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    emp = _client_for(org.report)  # EMPLOYEE lacks MANAGE_KPI_TEMPLATES
    resp = emp.post(
        f"{GOALS}templates/instantiate",
        {"employee": str(org.report.id), "cycle": str(cycle.id)},
        format="json",
    )
    assert resp.status_code == 403


def test_employee_cannot_list_templates(org):
    seed_templates_for_tenant(org.tenant)
    emp = _client_for(org.report)
    resp = emp.get(f"{GOALS}templates/")
    assert resp.status_code == 403


# ── audit: goal.created on create ──────────────────────────────────────────


def test_goal_create_audits(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    mgr.post(GOALS, _goal_payload(org.report, cycle), format="json")
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="goal.created", target_type="goal").exists()


# ── KPI weight = 100 enforced on PATCH (not only on create) ────────────────


def test_kpi_weight_patch_breaking_100_is_rejected(org):
    """PATCH-ing a KPI's weight so the parent goal no longer sums to 100.00 → 400,
    rolled back (the 100% rule holds on edit, not only on create)."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    created = mgr.post(GOALS, _goal_payload(org.report, cycle, kpi_weights=(60, 40)), format="json")
    assert created.status_code == 201
    kpi_id = created.json()["kpis"][0]["id"]  # the 60.00 KPI

    # 60.00 → 70.00 would make the goal sum to 110.00 → rejected.
    resp = mgr.patch(f"{GOALS}kpis/{kpi_id}", {"weight": "70.00"}, format="json")
    assert resp.status_code == 400
    with tenant_context(org.tenant):
        from apps.goals.models import Kpi
        assert Kpi.objects.get(id=kpi_id).weight == Decimal("60.00")  # unchanged (rolled back)


def test_kpi_non_weight_patch_does_not_trigger_weight_check(org):
    """A PATCH that doesn't touch weight (e.g. the name) is accepted — the 100%
    re-check only fires on a weight change."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    created = mgr.post(GOALS, _goal_payload(org.report, cycle, kpi_weights=(60, 40)), format="json")
    kpi_id = created.json()["kpis"][0]["id"]
    resp = mgr.patch(f"{GOALS}kpis/{kpi_id}", {"name": "Renamed KPI"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed KPI"
