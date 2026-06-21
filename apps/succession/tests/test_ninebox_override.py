"""
Nine-box human override (BUILD_7 Feature B) — HTTP tests over the REAL
``/api/succession/nine-box/<id>/override`` route.

Invariants:
  * HRBP/Admin only (OVERRIDE_NINE_BOX) — a Manager has VIEW/ASSESS but not this
    (403); an employee 404s at the succession participant gate;
  * the override sits ALONGSIDE the computed box (never rewrites it) and is fully
    reversible (DELETE → back to computed);
  * tenant isolation (another tenant's placement → 404);
  * every set/clear writes an audit row.
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.goals.models import CycleScore
from apps.identity.tokens import issue_tokens_for_user
from apps.succession.models import NineBoxPlacement
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db

SUCC = "/api/succession/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _score(tenant, employee, cycle, t):
    with tenant_context(tenant):
        return CycleScore.objects.create(
            tenant_id=tenant.id, employee=employee, cycle=cycle,
            raw_score=Decimal("0"), z_score=Decimal("0"), t_score=Decimal(str(t)),
            cohort_size=10, computed_at=timezone.now(),
        )


def _placement(org):
    """Create a 9-box placement for org.report (HRBP assesses); return (id, computed_box)."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle, 70)
    body = _client_for(org.hrbp).post(
        f"{SUCC}nine-box",
        {"employee": str(org.report.id), "cycle": str(cycle.id), "potential_band": "HIGH"},
        format="json",
    ).json()
    return body["id"], body["box"]


def _override_url(pid):
    return f"{SUCC}nine-box/{pid}/override"


def test_hrbp_sets_then_clears_override(org):
    pid, computed = _placement(org)
    new_box = 1 if computed != 1 else 2  # a different cell
    hrbp = _client_for(org.hrbp)

    setr = hrbp.put(_override_url(pid), {"box": new_box, "rationale": "calibrated down"}, format="json")
    assert setr.status_code == 200, setr.content
    d = setr.json()
    assert d["override_box"] == new_box
    assert d["box"] == computed  # computed box is NEVER rewritten
    assert d["effective_box"] == new_box and d["is_overridden"] is True
    assert d["override_rationale"] == "calibrated down"

    clr = hrbp.delete(_override_url(pid))
    assert clr.status_code == 200, clr.content
    d2 = clr.json()
    assert d2["override_box"] is None
    assert d2["effective_box"] == computed and d2["is_overridden"] is False


def test_manager_cannot_override(org):
    pid, _ = _placement(org)
    # the manager can VIEW/ASSESS the 9-box, but OVERRIDE is HRBP/Admin only.
    resp = _client_for(org.manager).put(_override_url(pid), {"box": 2}, format="json")
    assert resp.status_code == 403


def test_employee_override_is_404_participant_gate(org):
    pid, _ = _placement(org)
    resp = _client_for(org.report).put(_override_url(pid), {"box": 2}, format="json")
    assert resp.status_code == 404  # succession is invisible to employees


def test_override_cross_tenant_placement_is_404(org, other_tenant):
    other_user = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="o@other.test")
    with tenant_context(other_tenant):
        cycle = CycleFactory(tenant=other_tenant, status="ACTIVE")
        p = NineBoxPlacement.objects.create(
            tenant_id=other_tenant.id, employee=other_user, cycle=cycle,
            performance_band="HIGH", potential_band="HIGH", box=9, assessed_at=timezone.now(),
        )
    resp = _client_for(org.hrbp).put(_override_url(p.id), {"box": 5}, format="json")
    assert resp.status_code == 404


def test_override_invalid_box_is_rejected(org):
    pid, _ = _placement(org)
    hrbp = _client_for(org.hrbp)
    assert hrbp.put(_override_url(pid), {"box": 10}, format="json").status_code == 400
    assert hrbp.put(_override_url(pid), {"box": "abc"}, format="json").status_code == 400


def test_override_writes_audit_rows(org):
    pid, _ = _placement(org)
    hrbp = _client_for(org.hrbp)
    hrbp.put(_override_url(pid), {"box": 3}, format="json")
    hrbp.delete(_override_url(pid))
    with tenant_context(org.tenant):
        actions = set(
            AuditLog.objects.filter(target_type="ninebox").values_list("action", flat=True)
        )
    assert {"ninebox.override_set", "ninebox.override_cleared"} <= actions
