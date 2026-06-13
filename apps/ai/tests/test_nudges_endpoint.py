"""
GET /api/ai/nudges — Agent 2's KPI nudges over HTTP, scope-bounded: a Manager sees
their reporting subtree, HRBP/Admin the whole tenant, an Employee is 403
(VIEW_TEAM_SCORES). Reuses the team_nudges read service (no recompute).
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.goals.models import CycleScore
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory

pytestmark = pytest.mark.django_db

NUDGES = "/api/ai/nudges"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _score(tenant, employee, cycle, risk):
    with tenant_context(tenant):
        CycleScore.objects.create(
            tenant_id=tenant.id, employee=employee, cycle=cycle,
            raw_score=Decimal("0"), z_score=Decimal("0"), t_score=Decimal("35"),
            cohort_size=10, risk_status=risk, computed_at=timezone.now(),
        )


def _active_cycle(org):
    return CycleFactory(
        tenant=org.tenant, status="ACTIVE",
        end_date=timezone.now().date() + timezone.timedelta(days=60),  # >14 → STANDARD
    )


def test_manager_sees_own_tier_nudges_only(org):
    cycle = _active_cycle(org)
    _score(org.tenant, org.report, cycle, "AT_RISK")   # in the manager's subtree
    _score(org.tenant, org.peer, cycle, "AT_RISK")     # reports to hrbp — OUT of tier
    resp = _client_for(org.manager).get(NUDGES)
    assert resp.status_code == 200, resp.content
    employees = {n["employee"] for n in resp.json()}
    assert str(org.report.id) in employees
    assert str(org.peer.id) not in employees  # out-of-tier excluded


def test_hrbp_sees_tenant_wide(org):
    cycle = _active_cycle(org)
    _score(org.tenant, org.report, cycle, "AT_RISK")
    _score(org.tenant, org.peer, cycle, "AT_RISK")
    employees = {n["employee"] for n in _client_for(org.hrbp).get(NUDGES).json()}
    assert {str(org.report.id), str(org.peer.id)} <= employees


def test_employee_is_forbidden(org):
    assert _client_for(org.report).get(NUDGES).status_code == 403


def test_empty_when_none_at_risk(org):
    cycle = _active_cycle(org)
    _score(org.tenant, org.report, cycle, "ON_TRACK")  # on-track → no nudge
    assert _client_for(org.manager).get(NUDGES).json() == []


def test_cross_tenant_excluded(org, other_tenant):
    from apps.testsupport.factories import UserFactory

    other_emp = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="o@other.test")
    other_cycle = CycleFactory(
        tenant=other_tenant, status="ACTIVE",
        end_date=timezone.now().date() + timezone.timedelta(days=60),
    )
    _score(other_tenant, other_emp, other_cycle, "AT_RISK")
    # org's HRBP (tenant-wide) sees nothing from the other tenant.
    employees = {n["employee"] for n in _client_for(org.hrbp).get(NUDGES).json()}
    assert str(other_emp.id) not in employees


def test_unauthenticated_is_401(org):
    assert APIClient().get(NUDGES).status_code == 401
