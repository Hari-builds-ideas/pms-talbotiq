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
