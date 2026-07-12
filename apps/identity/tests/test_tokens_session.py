import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api():
    return APIClient()


def _login(api, slug="acme", email="a@acme.test", password="pw12345!"):
    return api.post(
        "/api/auth/login",
        {"tenant_slug": slug, "email": email, "password": password},
        format="json",
    ).json()


def test_me_returns_caller(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!", role="HRBP")
    data = _login(api)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
    resp = api.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "a@acme.test"
    assert body["role"] == "HRBP"
    assert body["tenant_id"] == str(user.tenant_id)


def test_me_includes_server_computed_capabilities(api):
    """/me carries the caller's capability grants from the SAME matrix the server
    enforces (FINAL D2) — the client gates controls off this list, so it must
    exactly mirror role_has_capability for the caller's role."""
    from apps.rbac.matrix import CAPABILITIES, capabilities_for_role, role_has_capability

    fixture_login = "pw12345!"  # the file-wide test fixture credential (not a secret)
    t = TenantFactory(slug="acme")
    for role, present, absent in [
        ("EMPLOYEE", "view_own_goals", "approve_review"),
        ("MANAGER", "approve_review", "manage_users_roles"),
        ("ADMIN", "manage_users_roles", "bypass_tenant_isolation"),
    ]:
        email = f"{role.lower()}@acme.test"
        UserFactory(tenant=t, email=email, password=fixture_login, role=role)
        data = _login(api, email=email)
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        caps = api.get("/api/auth/me").json()["capabilities"]
        assert caps == capabilities_for_role(role)
        assert present in caps and absent not in caps
        # exact mirror of the enforcement matrix — no drift possible
        assert set(caps) == {c for c in CAPABILITIES if role_has_capability(role, c)}


def test_me_requires_auth(api):
    resp = api.get("/api/auth/me")
    assert resp.status_code == 401


def test_invalid_bearer_token_is_rejected(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    resp = api.get("/api/auth/me")
    assert resp.status_code == 401


def test_refresh_preserves_tenant_and_role_claims(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!", role="MANAGER")
    data = _login(api)
    resp = api.post("/api/auth/token/refresh", {"refresh": data["refresh"]}, format="json")
    assert resp.status_code == 200
    token = AccessToken(resp.json()["access"])
    assert token["tenant_id"] == str(user.tenant_id)
    assert token["role"] == "MANAGER"


def test_logout_blacklists_refresh_token(api):
    t = TenantFactory(slug="acme")
    UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    data = _login(api)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
    resp = api.post("/api/auth/logout", {"refresh": data["refresh"]}, format="json")
    assert resp.status_code == 205
    # The blacklisted refresh token can no longer be used.
    api.credentials()
    again = api.post("/api/auth/token/refresh", {"refresh": data["refresh"]}, format="json")
    assert again.status_code == 401


def test_session_is_written_to_store(api):
    from django.contrib.sessions.backends.cache import SessionStore

    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    resp = api.post(
        "/api/auth/login",
        {"tenant_slug": "acme", "email": "a@acme.test", "password": "pw12345!"},
        format="json",
    )
    key = resp.cookies["sessionid"].value
    store = SessionStore(session_key=key)
    assert store.get("user_id") == str(user.id)
    assert store.get("tenant_id") == str(user.tenant_id)
    assert store.get("role") == user.role
