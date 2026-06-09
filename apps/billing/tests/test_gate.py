"""
Tests for the entitlement gate (``requires_entitlement``).

Two angles:
  * a focused unit test of the permission class against a DRF request;
  * an end-to-end HTTP test through a test-only view mounted behind
    ``@pytest.mark.urls`` and guarded by ``requires_entitlement("agent3")``,
    proving 403 on STARTER and 200 after a FULL_AI upgrade.
"""
import pytest
from rest_framework.test import APIClient

from apps.billing.gate import requires_entitlement
from apps.billing.services import upgrade_to_full_ai
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

PROBE = "/billing-test/agent3/"


def test_permission_class_denies_on_starter_allows_after_upgrade():
    t = TenantFactory()
    with tenant_context(t):
        user = UserFactory(tenant=t, role="ADMIN", email="gate@unit.test")

    perm = requires_entitlement("agent3")()
    # The permission only reads request.user, so a minimal stand-in suffices.
    drf_request = type("R", (), {"user": user})()

    with tenant_context(t):
        assert perm.has_permission(drf_request, view=None) is False
        upgrade_to_full_ai(t)
        assert perm.has_permission(drf_request, view=None) is True


def test_permission_class_denies_unauthenticated():
    perm = requires_entitlement("agent3")()

    class _Anon:
        is_authenticated = False
        tenant = None

    drf_request = type("R", (), {"user": _Anon()})()
    assert perm.has_permission(drf_request, view=None) is False


@pytest.mark.urls("apps.billing.tests.urls")
def test_gate_http_403_on_starter_then_200_after_upgrade():
    t = TenantFactory()
    with tenant_context(t):
        user = UserFactory(tenant=t, role="ADMIN", email="gate@http.test")

    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    # STARTER: agent3 locked -> 403.
    assert client.get(PROBE).status_code == 403

    upgrade_to_full_ai(t)

    # FULL_AI: agent3 unlocked -> 200.
    resp = client.get(PROBE)
    assert resp.status_code == 200
    assert resp.json() == {"ran": "agent3"}
