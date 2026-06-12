"""
HTTP tests for the Module-11 billing endpoints — feature flags + the upgrade
prompt — hitting the REAL ``/api/billing/...`` routes (production urlconf, no
``@pytest.mark.urls``).

These are the two NEW endpoints (MANAGE_ENTITLEMENTS — Admin-only) that ride on
top of the existing entitlement/upgrade/seats surface. The headline properties:
  * a STARTER tenant reads ``agent4: False``; an upgrade over HTTP flips it to
    ``True`` (the cache is cleared on the entitlement change);
  * the upgrade prompt lists the locked features + what FULL_AI would unlock;
  * the endpoints are Admin-only (non-admins 403; unauthenticated 401);
  * cross-tenant isolation: upgrading one tenant does not flip another's flags.
"""
import pytest
from rest_framework.test import APIClient

from apps.billing.packs import AGENT4
from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db

FEATURE_FLAGS = "/api/billing/feature-flags"
UPGRADE_PROMPT = "/api/billing/upgrade-prompt"
UPGRADE = "/api/billing/upgrade"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_feature_flags_locked_then_flipped_by_upgrade_over_http(org):
    """A STARTER tenant reads agent4 locked; POST /upgrade (over HTTP) flips it."""
    admin = _client_for(org.admin)

    resp = admin.get(FEATURE_FLAGS)
    assert resp.status_code == 200, resp.content
    flags = resp.json()
    assert flags[AGENT4] is False  # STARTER locks agents 3-5

    # Upgrade over the wire, then re-read the flags — the flip is instant.
    assert admin.post(UPGRADE).status_code == 200
    flags_after = admin.get(FEATURE_FLAGS).json()
    assert flags_after[AGENT4] is True


def test_upgrade_prompt_lists_locked_and_would_unlock(org):
    admin = _client_for(org.admin)
    resp = admin.get(UPGRADE_PROMPT)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert AGENT4 in body["locked_features"]
    assert AGENT4 in body["upgrade"]["would_unlock"]


@pytest.mark.parametrize("role", ["HRBP", "MANAGER", "EMPLOYEE"])
def test_non_admin_is_forbidden(org, role):
    actor = {"HRBP": org.hrbp, "MANAGER": org.manager, "EMPLOYEE": org.report}[role]
    client = _client_for(actor)
    assert client.get(FEATURE_FLAGS).status_code == 403
    assert client.get(UPGRADE_PROMPT).status_code == 403


def test_cross_tenant_upgrade_does_not_flip_other_tenants_flags(org, other_tenant):
    """Upgrading tenant A must not unlock anything for tenant B."""
    admin_a = _client_for(org.admin)
    other_admin = UserFactory(tenant=other_tenant, role="ADMIN")
    admin_b = _client_for(other_admin)

    assert admin_a.post(UPGRADE).status_code == 200

    assert admin_a.get(FEATURE_FLAGS).json()[AGENT4] is True
    assert admin_b.get(FEATURE_FLAGS).json()[AGENT4] is False


def test_unauthenticated_is_401(org):
    assert APIClient().get(FEATURE_FLAGS).status_code == 401
    assert APIClient().get(UPGRADE_PROMPT).status_code == 401
