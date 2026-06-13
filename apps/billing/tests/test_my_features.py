"""
GET /api/billing/my-features — the caller's OWN tenant feature-flag map, readable by
EVERY authenticated role (not Admin-only, unlike /feature-flags). Cross-tenant
isolated; identical data to ``feature_flags_for``.
"""
import pytest
from rest_framework.test import APIClient

from apps.billing.services import feature_flags_for, get_or_create_entitlement, upgrade_to_full_ai
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

MY_FEATURES = "/api/billing/my-features"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_every_role_reads_its_tenant_flag_map(org):
    get_or_create_entitlement(org.tenant)  # STARTER default
    for user in (org.report, org.manager, org.hrbp, org.admin):
        resp = _client_for(user).get(MY_FEATURES)
        assert resp.status_code == 200, (user.role, resp.content)
        flags = resp.json()
        # STARTER: agent2 + chat on; agent1 (now premium) + agents 3-5 off.
        assert flags["agent2"] is True and flags["chat"] is True
        assert flags["agent1"] is False and flags["agent4"] is False


def test_matches_feature_flags_for(org):
    get_or_create_entitlement(org.tenant)
    with tenant_context(org.tenant):
        expected = feature_flags_for(org.tenant)
    resp = _client_for(org.report).get(MY_FEATURES)
    assert resp.json() == expected


def test_reflects_upgrade_for_a_non_admin(org):
    get_or_create_entitlement(org.tenant)
    upgrade_to_full_ai(org.tenant)
    # A non-admin employee sees the upgraded map (agent1 now unlocked).
    flags = _client_for(org.report).get(MY_FEATURES).json()
    assert flags["agent1"] is True and flags["agent4"] is True


def test_cross_tenant_isolation(org, other_tenant):
    get_or_create_entitlement(org.tenant)        # STARTER
    upgrade_to_full_ai(other_tenant)             # the OTHER tenant upgrades
    # org's employee still sees STARTER — never the other tenant's flags.
    flags = _client_for(org.report).get(MY_FEATURES).json()
    assert flags["agent1"] is False


def test_unauthenticated_is_401(org):
    assert APIClient().get(MY_FEATURES).status_code == 401
