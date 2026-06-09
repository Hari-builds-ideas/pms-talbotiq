"""
End-to-end HTTP test proving the RBAC permission classes integrate over real
HTTP: JWT auth, ``TenantMiddleware`` binding the tenant from the verified token,
``HasCapability`` (role gate) and ``WithinScope`` (data-scope gate) yielding
200 / 403 / 401.

Routes come from the test-only urlconf (``apps.rbac.tests.urls``) activated with
``@pytest.mark.urls`` so nothing in the production urlconf is touched.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.rbac.tests.urls")]

DETAIL = "/rbac-test/users/{}/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_manager_hitting_own_report_gets_200(org):
    client = _client_for(org.manager)
    resp = client.get(DETAIL.format(org.report.id))
    assert resp.status_code == 200
    assert resp.json()["email"] == org.report.email


def test_manager_hitting_peer_gets_403(org):
    # Capability passes (manager has view_team_analytics) but peer is out of scope.
    client = _client_for(org.manager)
    resp = client.get(DETAIL.format(org.peer.id))
    assert resp.status_code == 403


def test_employee_hitting_another_user_gets_403(org):
    # Employee lacks view_team_analytics entirely -> capability gate denies first.
    client = _client_for(org.report)
    resp = client.get(DETAIL.format(org.manager.id))
    assert resp.status_code == 403


def test_employee_hitting_self_still_403_on_capability(org):
    # Even self is denied here: the endpoint gates view_team_analytics, which an
    # employee never holds, regardless of scope.
    client = _client_for(org.report)
    resp = client.get(DETAIL.format(org.report.id))
    assert resp.status_code == 403


def test_hrbp_can_reach_anyone_in_tenant(org):
    client = _client_for(org.hrbp)
    resp = client.get(DETAIL.format(org.peer.id))
    assert resp.status_code == 200
    assert resp.json()["email"] == org.peer.email


def test_unauthenticated_request_gets_401(org):
    resp = APIClient().get(DETAIL.format(org.report.id))
    assert resp.status_code == 401


def test_cross_tenant_target_is_not_found(org, other_tenant, make_user):
    # An admin of org.tenant cannot even resolve a user from another tenant: the
    # tenant-scoped manager (bound from the admin's JWT) filters it out -> 404.
    from apps.tenancy.context import tenant_context

    with tenant_context(other_tenant):
        outsider = make_user(tenant=other_tenant, role="EMPLOYEE", email="out@other.test")
    client = _client_for(org.admin)
    resp = client.get(DETAIL.format(outsider.id))
    assert resp.status_code == 404
