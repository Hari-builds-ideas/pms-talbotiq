"""
HTTP tests for the Analytics & Reporting API, hitting the REAL ``/api/analytics/``
routes (production urlconf — no ``@pytest.mark.urls``).

The headline theme is the MIN-COHORT SUPPRESSION boundary at 5: a department with
4 reports is returned aggregate-only (individuals suppressed) while a department
with 5 exposes them. The other themes mirror the rest of the system:

  * individual scope: own (200), a peer (404 out of scope), a manager → report (200);
  * an EMPLOYEE is barred from department analytics (403 — lacks the capability);
  * a Manager pulling an out-of-tier head → 404 (scope hides it);
  * the calibration grid (HRBP 200; Manager / Employee 403 — lack the capability);
  * export as text/plain and application/json;
  * a missing required ``cycle`` → 400;
  * cross-tenant isolation (404 — the head id never resolves in a foreign tenant);
  * unauthenticated → 401.
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.goals.models import CycleScore
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    NineBoxPlacementFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

AN = "/api/analytics/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _score(tenant, employee, cycle, t):
    """A CycleScore with T-score ``t`` for ``employee`` in ``cycle``."""
    with tenant_context(tenant):
        return CycleScore.objects.create(
            tenant_id=tenant.id,
            employee=employee,
            cycle=cycle,
            raw_score=Decimal("0"),
            z_score=Decimal("0"),
            t_score=Decimal(str(t)),
            cohort_size=10,
            computed_at=timezone.now(),
        )


def _department(tenant, n, *, reports_to):
    """A MANAGER head (reporting to ``reports_to``) + ``n`` scored EMPLOYEE
    reports in a fresh ACTIVE cycle. Returns (head, cycle, reports)."""
    head = UserFactory(tenant=tenant, role="MANAGER", manager=reports_to)
    cycle = CycleFactory(tenant=tenant, status="ACTIVE")
    reports = []
    for i in range(n):
        r = UserFactory(tenant=tenant, role="EMPLOYEE", manager=head)
        reports.append(r)
        _score(tenant, r, cycle, 45 + i * 3)
    return head, cycle, reports


# ── MIN-COHORT boundary (the headline) ────────────────────────────────────────


def test_department_four_reports_is_suppressed(org):
    """4 reports (< MIN_COHORT) → aggregate-only: suppressed True, individuals []."""
    head, cycle, _ = _department(org.tenant, 4, reports_to=org.hrbp)
    client = _client_for(head)  # the head pulls their OWN department
    resp = client.get(f"{AN}department?head={head.id}&cycle={cycle.id}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["suppressed"] is True
    assert body["individuals"] == []
    assert body["cohort_size"] == 4
    assert body["aggregate"]["headcount"] == 4  # aggregate is still present


def test_department_five_reports_exposes_individuals(org):
    """5 reports (== MIN_COHORT) → suppressed False with all 5 individuals."""
    head, cycle, reports = _department(org.tenant, 5, reports_to=org.hrbp)
    client = _client_for(head)
    resp = client.get(f"{AN}department?head={head.id}&cycle={cycle.id}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["suppressed"] is False
    assert body["cohort_size"] == 5
    assert len(body["individuals"]) == 5
    exposed = {row["employee"] for row in body["individuals"]}
    assert exposed == {str(r.id) for r in reports}


def test_department_defaults_head_to_caller(org):
    """Omitting ?head defaults to the caller (the head)."""
    head, cycle, _ = _department(org.tenant, 5, reports_to=org.hrbp)
    resp = _client_for(head).get(f"{AN}department?cycle={cycle.id}")
    assert resp.status_code == 200, resp.content
    assert resp.json()["head"] == str(head.id)


# ── individual analytics (scope) ──────────────────────────────────────────────


def test_individual_own_trend(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle, 60)
    resp = _client_for(org.report).get(f"{AN}individual")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["employee"] == str(org.report.id)
    assert len(body["trend"]) == 1
    assert body["trend"][0]["cycle"] == str(cycle.id)


def test_individual_out_of_scope_is_404(org):
    """org.report (an employee) cannot see org.peer's trend — out of scope → 404."""
    resp = _client_for(org.report).get(f"{AN}individual?employee={org.peer.id}")
    assert resp.status_code == 404, resp.content


def test_manager_can_see_report_individual(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle, 50)
    resp = _client_for(org.manager).get(f"{AN}individual?employee={org.report.id}")
    assert resp.status_code == 200, resp.content
    assert resp.json()["employee"] == str(org.report.id)


# ── EMPLOYEE barred from department analytics (403) ───────────────────────────


def test_employee_barred_from_department(org):
    """An Employee lacks VIEW_DEPARTMENT_ANALYTICS → 403 (a capability denial)."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    resp = _client_for(org.report).get(f"{AN}department?cycle={cycle.id}")
    assert resp.status_code == 403, resp.content


def test_manager_out_of_tier_head_is_404(org):
    """A manager pulling an out-of-tier head's department → 404 (scope hides it)."""
    head, cycle, _ = _department(org.tenant, 5, reports_to=org.hrbp)
    # org.manager is a peer of `head` (both report to hrbp); head is not in their tier.
    resp = _client_for(org.manager).get(
        f"{AN}department?head={head.id}&cycle={cycle.id}"
    )
    assert resp.status_code == 404, resp.content


# ── calibration grid ──────────────────────────────────────────────────────────


def test_calibration_grid_hrbp(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    NineBoxPlacementFactory(
        employee=org.report, cycle=cycle, performance_band="HIGH",
        potential_band="HIGH", box=9,
    )
    NineBoxPlacementFactory(
        employee=org.peer, cycle=cycle, performance_band="MEDIUM",
        potential_band="MEDIUM", box=5,
    )
    resp = _client_for(org.hrbp).get(f"{AN}calibration?cycle={cycle.id}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["total"] == 2
    assert body["grid"]["9"] == 1
    assert body["grid"]["5"] == 1
    assert body["grid"]["1"] == 0


def test_calibration_barred_for_manager_and_employee(org):
    """Manager and Employee lack VIEW_CALIBRATION_GRID → 403."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    assert (
        _client_for(org.manager).get(f"{AN}calibration?cycle={cycle.id}").status_code
        == 403
    )
    assert (
        _client_for(org.report).get(f"{AN}calibration?cycle={cycle.id}").status_code
        == 403
    )


# ── export (text / JSON only) ─────────────────────────────────────────────────


def test_export_text_and_json(org):
    head, cycle, _ = _department(org.tenant, 5, reports_to=org.hrbp)
    hrbp = _client_for(org.hrbp)

    resp = hrbp.get(f"{AN}export?head={head.id}&cycle={cycle.id}&format=text")
    assert resp.status_code == 200, resp.content
    assert resp["Content-Type"].startswith("text/plain")
    assert b"Department rollup" in resp.content

    resp = hrbp.get(f"{AN}export?head={head.id}&cycle={cycle.id}&format=json")
    assert resp.status_code == 200, resp.content
    assert resp["Content-Type"].startswith("application/json")
    body = resp.json()
    assert body["head"] == str(head.id)
    assert body["cohort_size"] == 5


# ── missing required cycle → 400 ──────────────────────────────────────────────


def test_department_missing_cycle_is_400(org):
    head, _, _ = _department(org.tenant, 5, reports_to=org.hrbp)
    resp = _client_for(head).get(f"{AN}department?head={head.id}")
    assert resp.status_code == 400, resp.content
    assert "cycle" in resp.json()["detail"].lower()


# ── cross-tenant isolation (404) ──────────────────────────────────────────────


def test_cross_tenant_head_is_404(org, other_tenant):
    """An other-tenant manager pulling org's head → 404 (the head id never
    resolves in the foreign tenant's scoped manager)."""
    head, cycle, _ = _department(org.tenant, 5, reports_to=org.hrbp)
    other_mgr = UserFactory(tenant=other_tenant, role="MANAGER")
    resp = _client_for(other_mgr).get(
        f"{AN}department?head={head.id}&cycle={cycle.id}"
    )
    assert resp.status_code == 404, resp.content


# ── unauthenticated → 401 ─────────────────────────────────────────────────────


def test_unauthenticated_is_401(org):
    assert APIClient().get(f"{AN}individual").status_code == 401
