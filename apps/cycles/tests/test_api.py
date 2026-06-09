"""
HTTP tests for the cycle API — cycle CRUD plus the score read / recompute
endpoints — hitting the REAL ``/api/cycles/...`` routes (they live in the
production urlconf, so no ``@pytest.mark.urls`` is needed).

Covers JWT auth + ``TenantMiddleware`` binding, the MANAGE_CYCLES / VIEW_*
gates, the scope branching on the score reads (manager subtree vs HRBP tenant),
cross-tenant isolation (404), and that ``scores.recomputed`` is audited.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.goals.services import record_actual
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, KpiFactory

pytestmark = pytest.mark.django_db

CYCLES = "/api/cycles/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _active_goal_with_actual(employee, cycle, *, actual):
    """Build an ACTIVE goal with one weight-100 KPI and a recorded actual, so the
    scoring engine produces a CycleScore for ``employee``."""
    with tenant_context(employee.tenant_id):
        goal = GoalFactory(employee=employee, cycle=cycle, status="ACTIVE")
        kpi = KpiFactory(goal=goal, weight=Decimal("100.00"), target_value=Decimal("100.0000"))
        record_actual(kpi, Decimal(str(actual)))
    return goal


# ── cycle CRUD + RBAC ──────────────────────────────────────────────────────


def test_hrbp_can_create_and_list_cycles(org):
    client = _client_for(org.hrbp)
    resp = client.post(
        CYCLES,
        {"name": "H1 2026", "start_date": "2026-01-01", "end_date": "2026-06-30"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "H1 2026"
    assert resp.json()["status"] == "DRAFT"  # default

    list_resp = client.get(CYCLES)
    assert list_resp.status_code == 200
    assert any(c["name"] == "H1 2026" for c in list_resp.json())


def test_admin_can_create_cycle(org):
    client = _client_for(org.admin)
    resp = client.post(
        CYCLES,
        {"name": "FY26", "start_date": "2026-01-01", "end_date": "2026-12-31"},
        format="json",
    )
    assert resp.status_code == 201


def test_employee_cannot_create_cycle(org):
    client = _client_for(org.report)  # EMPLOYEE lacks MANAGE_CYCLES
    resp = client.post(
        CYCLES,
        {"name": "Nope", "start_date": "2026-01-01", "end_date": "2026-06-30"},
        format="json",
    )
    assert resp.status_code == 403


def test_manager_cannot_create_cycle(org):
    client = _client_for(org.manager)  # MANAGER lacks MANAGE_CYCLES
    resp = client.post(
        CYCLES,
        {"name": "Nope", "start_date": "2026-01-01", "end_date": "2026-06-30"},
        format="json",
    )
    assert resp.status_code == 403


def test_cycle_create_audits_before_write(org):
    client = _client_for(org.hrbp)
    client.post(
        CYCLES,
        {"name": "Audited", "start_date": "2026-01-01", "end_date": "2026-06-30"},
        format="json",
    )
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="cycle.created", target_type="cycle").exists()


def test_cross_tenant_cycle_is_not_found(org, other_tenant):
    # A cycle owned by another tenant is 404 to org's admin (scoped manager).
    outside = CycleFactory(tenant=other_tenant)
    client = _client_for(org.admin)
    resp = client.get(f"{CYCLES}{outside.id}")
    assert resp.status_code == 404


def test_cycle_patch_and_soft_delete(org):
    client = _client_for(org.hrbp)
    cycle = CycleFactory(tenant=org.tenant, status="DRAFT")
    patch = client.patch(f"{CYCLES}{cycle.id}", {"status": "ACTIVE"}, format="json")
    assert patch.status_code == 200
    assert patch.json()["status"] == "ACTIVE"

    delete = client.delete(f"{CYCLES}{cycle.id}")
    assert delete.status_code == 204
    # Soft-deleted → no longer resolvable via the default manager.
    assert client.get(f"{CYCLES}{cycle.id}").status_code == 404


# ── recompute ──────────────────────────────────────────────────────────────


def test_manager_can_recompute_and_audit_row_written(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _active_goal_with_actual(org.report, cycle, actual=80)
    _active_goal_with_actual(org.manager, cycle, actual=60)

    client = _client_for(org.manager)
    resp = client.post(f"{CYCLES}{cycle.id}/recompute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cycle_id"] == str(cycle.id)
    assert body["scored"] == 2  # report + manager both have an active goal

    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="scores.recomputed", target_id=str(cycle.id)
        ).exists()


def test_employee_cannot_recompute(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    client = _client_for(org.report)  # EMPLOYEE lacks VIEW_TEAM_SCORES
    resp = client.post(f"{CYCLES}{cycle.id}/recompute")
    assert resp.status_code == 403


def test_recompute_cross_tenant_cycle_is_404(org, other_tenant):
    outside = CycleFactory(tenant=other_tenant, status="ACTIVE")
    client = _client_for(org.manager)
    resp = client.post(f"{CYCLES}{outside.id}/recompute")
    assert resp.status_code == 404


# ── score reads ────────────────────────────────────────────────────────────


def test_employee_reads_own_score_after_recompute(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _active_goal_with_actual(org.report, cycle, actual=90)
    _active_goal_with_actual(org.peer, cycle, actual=40)

    # Manager triggers the recompute (employee can't), then employee reads /me.
    _client_for(org.manager).post(f"{CYCLES}{cycle.id}/recompute")

    client = _client_for(org.report)
    resp = client.get(f"{CYCLES}{cycle.id}/scores/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["employee"] == str(org.report.id)
    assert "raw_score" in body and "t_score" in body and "risk_status" in body


def test_my_score_404_when_none_computed(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    client = _client_for(org.report)
    resp = client.get(f"{CYCLES}{cycle.id}/scores/me")
    assert resp.status_code == 404


def test_manager_scores_show_subtree_not_peer(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _active_goal_with_actual(org.report, cycle, actual=80)  # in manager subtree
    _active_goal_with_actual(org.peer, cycle, actual=50)    # reports to hrbp — NOT subtree
    _active_goal_with_actual(org.manager, cycle, actual=70)  # self

    _client_for(org.manager).post(f"{CYCLES}{cycle.id}/recompute")

    client = _client_for(org.manager)
    resp = client.get(f"{CYCLES}{cycle.id}/scores")
    assert resp.status_code == 200
    emp_ids = {row["employee"] for row in resp.json()}
    assert str(org.report.id) in emp_ids   # subtree
    assert str(org.manager.id) in emp_ids  # self
    assert str(org.peer.id) not in emp_ids  # outside subtree → hidden


def test_hrbp_scores_show_everyone_in_tenant(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _active_goal_with_actual(org.report, cycle, actual=80)
    _active_goal_with_actual(org.peer, cycle, actual=50)

    _client_for(org.manager).post(f"{CYCLES}{cycle.id}/recompute")

    client = _client_for(org.hrbp)
    resp = client.get(f"{CYCLES}{cycle.id}/scores")
    assert resp.status_code == 200
    emp_ids = {row["employee"] for row in resp.json()}
    assert {str(org.report.id), str(org.peer.id)} <= emp_ids  # tenant-wide


def test_cross_tenant_scores_never_appear(org, other_tenant):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _active_goal_with_actual(org.report, cycle, actual=80)
    _client_for(org.manager).post(f"{CYCLES}{cycle.id}/recompute")

    # A separate cycle + scored employee in another tenant.
    other_cycle = CycleFactory(tenant=other_tenant, status="ACTIVE")
    from apps.testsupport.factories import UserFactory

    with tenant_context(other_tenant):
        outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE")
    _active_goal_with_actual(outsider, other_cycle, actual=80)
    # The other tenant cannot be recomputed here, but even if it were, org's HRBP
    # reads only org.tenant. Confirm the outsider never shows in org's scores.
    client = _client_for(org.hrbp)
    resp = client.get(f"{CYCLES}{cycle.id}/scores")
    assert resp.status_code == 200
    emp_ids = {row["employee"] for row in resp.json()}
    assert str(outsider.id) not in emp_ids


def test_unauthenticated_cycle_list_is_401(org):
    resp = APIClient().get(CYCLES)
    assert resp.status_code == 401
