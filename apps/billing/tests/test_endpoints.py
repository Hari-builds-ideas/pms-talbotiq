"""
HTTP tests for the admin billing endpoints, hitting the REAL ``/api/billing/...``
routes (they live in the production urlconf — no ``@pytest.mark.urls`` needed).

Covers JWT auth + ``TenantMiddleware`` binding + the MANAGE_TENANT admin gate,
and proves the upgrade unlocks agents 3-5 over the wire while leaving seats
untouched.
"""
import pytest
from rest_framework.test import APIClient

from apps.billing.packs import AGENT3, AGENT4, AGENT5
from apps.identity.tokens import issue_tokens_for_user

pytestmark = pytest.mark.django_db

ENTITLEMENT = "/api/billing/entitlement"
UPGRADE = "/api/billing/upgrade"
SEATS = "/api/billing/seats"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_admin_get_entitlement_returns_defaults(org):
    client = _client_for(org.admin)
    resp = client.get(ENTITLEMENT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["seat_count"] == 0
    assert body["feature_packs"] == ["STARTER"]
    assert set(body["unlocked_agents"]) == {"agent2"}  # Agent 1 is now PREMIUM (FULL_AI)
    assert body["tier_label"] == "Starter"


def test_admin_upgrade_unlocks_agents_3_to_5_without_changing_seats(org):
    client = _client_for(org.admin)
    # Set seats first so we can prove the upgrade leaves them alone.
    seats_resp = client.patch(SEATS, {"seat_count": 30}, format="json")
    assert seats_resp.status_code == 200
    assert seats_resp.json()["seat_count"] == 30

    resp = client.post(UPGRADE)
    assert resp.status_code == 200
    body = resp.json()
    assert {AGENT3, AGENT4, AGENT5} <= set(body["unlocked_agents"])
    assert body["seat_count"] == 30  # unchanged by the upgrade
    assert body["tier_label"] == "Full AI"


def test_patch_seats_moves_independently_of_packs(org):
    client = _client_for(org.admin)
    client.post(UPGRADE)  # now FULL_AI
    resp = client.patch(SEATS, {"seat_count": 7}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["seat_count"] == 7
    assert "FULL_AI" in body["feature_packs"]  # packs preserved


def test_patch_seats_rejects_non_integer(org):
    client = _client_for(org.admin)
    resp = client.patch(SEATS, {"seat_count": "lots"}, format="json")
    assert resp.status_code == 400


def test_non_admin_get_entitlement_is_forbidden(org):
    client = _client_for(org.report)  # EMPLOYEE
    resp = client.get(ENTITLEMENT)
    assert resp.status_code == 403


def test_non_admin_upgrade_is_forbidden(org):
    client = _client_for(org.report)  # EMPLOYEE
    resp = client.post(UPGRADE)
    assert resp.status_code == 403


def test_unauthenticated_entitlement_is_unauthorized(org):
    resp = APIClient().get(ENTITLEMENT)
    assert resp.status_code == 401


def test_unauthenticated_upgrade_is_unauthorized(org):
    resp = APIClient().post(UPGRADE)
    assert resp.status_code == 401
