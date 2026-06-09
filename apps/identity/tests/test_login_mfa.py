import pytest
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api():
    return APIClient()


def _enable_mfa(user):
    device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    user.mfa_enabled = True
    user.save(update_fields=["mfa_enabled", "updated_at"])
    return device


def _login(api, slug="acme", email="a@acme.test", password="pw12345!"):
    return api.post(
        "/api/auth/login",
        {"tenant_slug": slug, "email": email, "password": password},
        format="json",
    )


# ── credentials ───────────────────────────────────────────────────────────


def test_login_success_no_mfa(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!", role="MANAGER")
    resp = _login(api)
    assert resp.status_code == 200
    data = resp.json()
    assert data["mfa_required"] is False
    token = AccessToken(data["access"])
    assert token["tenant_id"] == str(user.tenant_id)
    assert token["role"] == "MANAGER"
    # Session was written to the session store (Redis in dev/prod).
    assert "sessionid" in resp.cookies


def test_login_wrong_password_is_401(api):
    t = TenantFactory(slug="acme")
    UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    resp = _login(api, password="nope")
    assert resp.status_code == 401
    assert "access" not in resp.json()


def test_login_unknown_user_is_401(api):
    TenantFactory(slug="acme")
    resp = _login(api, email="ghost@acme.test")
    assert resp.status_code == 401


def test_login_unknown_tenant_is_401(api):
    resp = _login(api, slug="nope")
    assert resp.status_code == 401


def test_login_inactive_tenant_is_401(api):
    t = TenantFactory(slug="susp", status="SUSPENDED")
    UserFactory(tenant=t, email="a@susp.test", password="pw12345!")
    resp = _login(api, slug="susp", email="a@susp.test")
    assert resp.status_code == 401


# ── MFA ─────────────────────────────────────────────────────────────────────


def test_login_with_mfa_returns_token_not_jwt(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    _enable_mfa(user)
    resp = _login(api)
    assert resp.status_code == 200
    data = resp.json()
    assert data["mfa_required"] is True
    assert "mfa_token" in data
    assert "access" not in data


def test_mfa_challenge_success_issues_jwt(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    device = _enable_mfa(user)
    mfa_token = _login(api).json()["mfa_token"]

    code = str(totp(device.bin_key))
    resp = api.post(
        "/api/auth/mfa/challenge",
        {"mfa_token": mfa_token, "code": code},
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert AccessToken(data["access"])["tenant_id"] == str(user.tenant_id)


def test_mfa_challenge_bad_code_is_401(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    _enable_mfa(user)
    mfa_token = _login(api).json()["mfa_token"]
    resp = api.post(
        "/api/auth/mfa/challenge",
        {"mfa_token": mfa_token, "code": "000000"},
        format="json",
    )
    assert resp.status_code == 401


def test_mfa_enroll_and_confirm_flow(api):
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    login = _login(api).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")

    enroll = api.post("/api/auth/mfa/enroll", {}, format="json")
    assert enroll.status_code == 200
    body = enroll.json()
    assert body["secret"]
    assert body["config_url"].startswith("otpauth://")

    device = TOTPDevice.objects.get(user=user, confirmed=False)
    confirm = api.post(
        "/api/auth/mfa/enroll/confirm",
        {"code": str(totp(device.bin_key))},
        format="json",
    )
    assert confirm.status_code == 200
    assert confirm.json()["mfa_enabled"] is True

    user.refresh_from_db()
    assert user.mfa_enabled is True
    assert TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def test_mfa_confirm_with_bad_code_is_rejected(api):
    t = TenantFactory(slug="acme")
    UserFactory(tenant=t, email="a@acme.test", password="pw12345!")
    login = _login(api).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    api.post("/api/auth/mfa/enroll", {}, format="json")
    confirm = api.post(
        "/api/auth/mfa/enroll/confirm", {"code": "000000"}, format="json"
    )
    assert confirm.status_code == 400
