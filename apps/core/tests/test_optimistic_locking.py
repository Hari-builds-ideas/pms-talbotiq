"""
Optimistic locking + the KPI weight-sum critical section (BUILD_4 4.3).

* Goal + TenantConfig carry a server-controlled ``version``; a PATCH/PUT that
  sends a STALE version → 409 STALE_VERSION (no silent last-writer-wins). A
  request that omits ``version`` still works (back-compat).
* The KPI weight-sum invariant is guarded by a ``SELECT ... FOR UPDATE`` row lock
  so concurrent weight changes on a goal can't both pass the = 100.00 check.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory

pytestmark = pytest.mark.django_db


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _goal(org):
    cycle = CycleFactory(tenant=org.tenant)
    with tenant_context(org.tenant):
        return GoalFactory(employee=org.report, cycle=cycle)


def test_goal_stale_version_is_409(org):
    goal = _goal(org)
    mgr = _client(org.manager)
    v = mgr.get(f"/api/goals/{goal.id}").json()["version"]

    # First edit with the version we read → 200, version bumps.
    r1 = mgr.patch(f"/api/goals/{goal.id}", {"title": "First", "version": v}, format="json")
    assert r1.status_code == 200, r1.content
    assert r1.json()["version"] == v + 1

    # Second edit STILL sending the old version → 409 (someone else saved first).
    r2 = mgr.patch(f"/api/goals/{goal.id}", {"title": "Second", "version": v}, format="json")
    assert r2.status_code == 409
    assert r2.json()["code"] == "STALE_VERSION"
    # DRF coerces APIException detail values to strings; the client parses it.
    assert int(r2.json()["current_version"]) == v + 1

    # Omitting version is still allowed (non-form / back-compat callers).
    r3 = mgr.patch(f"/api/goals/{goal.id}", {"title": "Third"}, format="json")
    assert r3.status_code == 200


def test_tenant_config_stale_version_is_409(org):
    admin = _client(org.admin)
    cfg = admin.get("/api/admin/tenant-config").json()
    v = cfg["version"]

    r1 = admin.put(
        "/api/admin/tenant-config", {"settings": {"locale": "en-GB"}, "version": v}, format="json"
    )
    assert r1.status_code == 200, r1.content
    assert r1.json()["version"] == v + 1

    r2 = admin.put(
        "/api/admin/tenant-config", {"settings": {"locale": "fr"}, "version": v}, format="json"
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "STALE_VERSION"


def test_kpi_weight_critical_section_locks_the_goal(org):
    """Adding a KPI re-validates the goal's weight sum under a row lock — assert
    the SELECT ... FOR UPDATE on the goal is issued (the DB then serialises
    concurrent weight changes; the lock can't be observed without it)."""
    goal = _goal(org)
    mgr = _client(org.manager)
    with tenant_context(org.tenant), CaptureQueriesContext(connection) as ctx:
        resp = mgr.post(
            f"/api/goals/{goal.id}/kpis",
            {"name": "K1", "weight": "100.00", "target_value": "10"},
            format="json",
        )
    assert resp.status_code == 201, resp.content
    assert any("FOR UPDATE" in q["sql"].upper() for q in ctx.captured_queries)
