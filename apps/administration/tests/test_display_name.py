"""
User display_name (FE #10): optional, nullable, NOT unique. Wired into admin
create/edit, the identity `me` response, and the org person card + search; falls
back to email (via ``User.display``) when empty.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

ADMIN_USERS = "/api/admin/users"
ME = "/api/auth/me"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


# ── model fallback ─────────────────────────────────────────────────────────


def test_display_property_falls_back_to_email(org):
    with tenant_context(org.tenant):
        u = User.objects.get(id=org.report.id)
        assert u.display_name is None
        assert u.display == u.email  # empty → email fallback
        u.display_name = "Reporta Smith"
        u.save(update_fields=["display_name", "updated_at"])
        assert u.display == "Reporta Smith"


# ── admin create / edit ─────────────────────────────────────────────────────


def test_create_user_with_display_name(org):
    resp = _client_for(org.admin).post(
        ADMIN_USERS,
        {"email": "newhire@acme.test", "role": "EMPLOYEE", "display_name": "New Hire"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["display_name"] == "New Hire"
    assert body["display"] == "New Hire"


def test_create_user_without_display_name_uses_email(org):
    resp = _client_for(org.admin).post(
        ADMIN_USERS, {"email": "plain@acme.test", "role": "EMPLOYEE"}, format="json"
    )
    body = resp.json()
    assert body["display_name"] is None
    assert body["display"] == "plain@acme.test"  # fallback


def test_set_display_name_endpoint_sets_then_clears(org):
    admin = _client_for(org.admin)
    set_resp = admin.post(
        f"{ADMIN_USERS}/{org.report.id}/display-name",
        {"display_name": "Reporta Smith"}, format="json",
    )
    assert set_resp.status_code == 200, set_resp.content
    assert set_resp.json()["display"] == "Reporta Smith"
    # Clearing (blank) → falls back to email.
    clear_resp = admin.post(
        f"{ADMIN_USERS}/{org.report.id}/display-name", {"display_name": ""}, format="json"
    )
    assert clear_resp.json()["display_name"] is None
    assert clear_resp.json()["display"] == org.report.email


def test_non_admin_cannot_set_display_name(org):
    resp = _client_for(org.hrbp).post(
        f"{ADMIN_USERS}/{org.report.id}/display-name", {"display_name": "X"}, format="json"
    )
    assert resp.status_code == 403


# ── identity `me` ─────────────────────────────────────────────────────────


def test_me_returns_display_name_and_display(org):
    _client_for(org.admin).post(
        f"{ADMIN_USERS}/{org.report.id}/display-name",
        {"display_name": "Reporta Smith"}, format="json",
    )
    me = _client_for(org.report).get(ME).json()
    assert me["display_name"] == "Reporta Smith"
    assert me["display"] == "Reporta Smith"


def test_me_falls_back_to_email_when_unset(org):
    me = _client_for(org.report).get(ME).json()
    assert me["display_name"] is None
    assert me["display"] == org.report.email


# ── org person card + search ─────────────────────────────────────────────────


def test_person_card_returns_display(org):
    _client_for(org.admin).post(
        f"{ADMIN_USERS}/{org.report.id}/display-name",
        {"display_name": "Reporta Smith"}, format="json",
    )
    card = _client_for(org.admin).get(f"/api/org/people/{org.report.id}").json()
    assert card["display_name"] == "Reporta Smith"
    assert card["display"] == "Reporta Smith"


def test_person_card_falls_back_to_email(org):
    card = _client_for(org.admin).get(f"/api/org/people/{org.manager.id}").json()
    assert card["display_name"] is None
    assert card["display"] == org.manager.email


def test_search_returns_display(org):
    _client_for(org.admin).post(
        f"{ADMIN_USERS}/{org.report.id}/display-name",
        {"display_name": "Reporta Smith"}, format="json",
    )
    results = _client_for(org.admin).get("/api/org/search", {"q": "report@acme"}).json()["results"]
    row = next(r for r in results if r["id"] == str(org.report.id))
    assert row["display_name"] == "Reporta Smith"
    assert row["display"] == "Reporta Smith"
