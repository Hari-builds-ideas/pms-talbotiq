"""
HTTP tests for the READ-ONLY Audit Console, hitting the REAL ``/api/audit/logs``
route (production urlconf, no ``@pytest.mark.urls``).

Themes:
  * the console is HRBP (scoped) + Admin (tenant) — both read paginated rows;
  * filtering by action / actor / a future date_from;
  * scope: an Employee and a Manager lack VIEW_AUDIT_CONSOLE → 403;
  * tenant isolation: another tenant's rows never appear;
  * READ-ONLY: a POST to the console is a 405 (no write route), and — re-proving
    the Module-1 immutability — a queryset ``update()`` on the audit log raises
    ``AuditLogImmutableError``;
  * the unauthenticated 401.
"""
import pytest
from rest_framework.test import APIClient

from apps.audit.exceptions import AuditLogImmutableError
from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGS = "/api/audit/logs"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _seed(org):
    """Seed a couple of audit rows in org's tenant; return them."""
    with tenant_context(org.tenant):
        a = record(
            action="x.did",
            actor=org.admin,
            target_type="t",
            target_id="1",
            tenant=org.tenant,
        )
        b = record(
            action="y.happened",
            actor=org.hrbp,
            target_type="t",
            target_id="2",
            tenant=org.tenant,
        )
    return a, b


@pytest.mark.parametrize("role", ["ADMIN", "HRBP"])
def test_management_reads_paginated_logs(org, role):
    _seed(org)
    actor = org.admin if role == "ADMIN" else org.hrbp
    resp = _client_for(actor).get(LOGS)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "results" in body  # paginated
    actions = {row["action"] for row in body["results"]}
    assert {"x.did", "y.happened"} <= actions


def test_filter_by_action(org):
    _seed(org)
    resp = _client_for(org.admin).get(LOGS, {"action": "x.did"})
    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"]
    assert rows  # non-empty
    assert all(r["action"] == "x.did" for r in rows)


def test_filter_by_actor(org):
    _seed(org)
    resp = _client_for(org.admin).get(LOGS, {"actor": str(org.admin.id)})
    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"]
    assert rows
    assert all(r["actor"] == str(org.admin.id) for r in rows)


def test_future_date_from_returns_empty(org):
    _seed(org)
    resp = _client_for(org.admin).get(LOGS, {"date_from": "2999-01-01T00:00:00+00:00"})
    assert resp.status_code == 200, resp.content
    assert resp.json()["results"] == []


@pytest.mark.parametrize("role", ["EMPLOYEE", "MANAGER"])
def test_non_management_is_forbidden(org, role):
    _seed(org)
    actor = org.report if role == "EMPLOYEE" else org.manager
    resp = _client_for(actor).get(LOGS)
    assert resp.status_code == 403


def test_tenant_isolation(org, other_tenant):
    _seed(org)
    other_hrbp = UserFactory(tenant=other_tenant, role="HRBP")
    with tenant_context(other_tenant):
        record(action="other.secret", tenant=other_tenant)
    # org's HRBP must not see the other tenant's rows.
    resp = _client_for(org.hrbp).get(LOGS)
    assert resp.status_code == 200, resp.content
    actions = {row["action"] for row in resp.json()["results"]}
    assert "other.secret" not in actions
    # And the other tenant's HRBP does not see org's rows.
    resp = _client_for(other_hrbp).get(LOGS)
    assert resp.status_code == 200, resp.content
    other_actions = {row["action"] for row in resp.json()["results"]}
    assert "x.did" not in other_actions
    assert "other.secret" in other_actions


def test_console_is_read_only_post_is_405(org):
    """The console is a ListAPIView — only GET is exposed; a POST is a 405 and
    there is no write route at all."""
    resp = _client_for(org.admin).post(LOGS, {"action": "tamper"}, format="json")
    assert resp.status_code == 405


def test_audit_log_update_is_immutable(org):
    """Re-prove the Module-1 immutability: a queryset update() is forbidden."""
    _seed(org)
    with tenant_context(org.tenant):
        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(action="x.did").update(action="tampered")


def test_unauthenticated_is_401(org):
    assert APIClient().get(LOGS).status_code == 401
