"""
PHASE2 L1.3 — device sessions, login history, account lockout. All ADDITIVE on the
existing JWT scheme (rotation+blacklist untouched); these tests prove the additions
and that nothing pre-existing regressed.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.models import DeviceSession, LoginEvent
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

LOGIN = "/api/auth/login"
REFRESH = "/api/auth/token/refresh"
SESSIONS = "/api/auth/sessions"
HISTORY = "/api/auth/login-history"


@pytest.fixture
def api():
    return APIClient()


def _mk(pw="login-pw-123!"):
    t = TenantFactory(slug="acme")
    u = UserFactory(tenant=t, email="a@acme.test", password=pw, role="EMPLOYEE")
    return t, u, pw


def _login(api, pw):
    r = api.post(LOGIN, {"tenant_slug": "acme", "email": "a@acme.test", "password": pw}, format="json")
    assert r.status_code == 200, r.content
    return r.json()


def test_login_creates_device_session_and_history(api):
    t, u, pw = _mk()
    body = _login(api, pw)
    with tenant_context(t):
        assert DeviceSession.objects.filter(user=u, revoked_at__isnull=True).count() == 1
        assert LoginEvent.objects.filter(user=u, event="LOGIN_OK").count() == 1
    # The sessions endpoint lists it, marked current.
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    rows = api.get(SESSIONS).json()
    assert len(rows) == 1 and rows[0]["current"] is True
    # History shows the successful login.
    events = [e["event"] for e in api.get(HISTORY).json()]
    assert "LOGIN_OK" in events


def test_failed_logins_recorded_and_locked_out_then_reset_on_success(api):
    t, u, pw = _mk()
    with override_settings(LOGIN_LOCKOUT_ATTEMPTS=3):
        for _ in range(3):  # attempts 1-3 (all failures) stay 401
            r = api.post(LOGIN, {"tenant_slug": "acme", "email": "a@acme.test", "password": "wrong"}, format="json")
            assert r.status_code == 401
        # attempt 4 is over the limit → 429 BEFORE credentials are checked
        r = api.post(LOGIN, {"tenant_slug": "acme", "email": "a@acme.test", "password": pw}, format="json")
        assert r.status_code == 429
    with tenant_context(t):
        assert LoginEvent.objects.filter(email="a@acme.test", event="LOGIN_FAILED").count() == 3
        assert LoginEvent.objects.filter(email="a@acme.test", event="LOCKOUT").count() == 1
    # With the default (higher) limit the same account logs in fine, which resets
    # the window (clear_attempts) — then subsequent logins keep working.
    _login(api, pw)
    _login(api, pw)


def test_lockout_does_not_reveal_account_existence(api):
    _mk()
    with override_settings(LOGIN_LOCKOUT_ATTEMPTS=2):
        for _ in range(2):
            api.post(LOGIN, {"tenant_slug": "acme", "email": "ghost@acme.test", "password": "x"}, format="json")
        r = api.post(LOGIN, {"tenant_slug": "acme", "email": "ghost@acme.test", "password": "x"}, format="json")
        # Unknown account locks out with the SAME 429 as a real one.
        assert r.status_code == 429


def test_revoked_session_cannot_refresh(api):
    t, u, pw = _mk()
    body = _login(api, pw)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    sid = api.get(SESSIONS).json()[0]["id"]
    assert api.post(f"{SESSIONS}/{sid}/revoke", {}, format="json").status_code == 200
    # The revoked session's refresh token can no longer rotate.
    r = api.post(REFRESH, {"refresh": body["refresh"]}, format="json")
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"].lower()


def test_revoke_others_keeps_current_session_alive(api):
    t, u, pw = _mk()
    first = _login(api, pw)   # session A
    second = _login(api, pw)  # session B (current)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {second['access']}")
    out = api.post(f"{SESSIONS}/revoke-others", {}, format="json").json()
    assert out["revoked"] == 1
    # A cannot refresh; B still can.
    assert api.post(REFRESH, {"refresh": first["refresh"]}, format="json").status_code == 401
    assert api.post(REFRESH, {"refresh": second["refresh"]}, format="json").status_code == 200


def test_sessions_are_self_only(api):
    t, u, pw = _mk()
    other = UserFactory(tenant=t, email="b@acme.test", password=pw, role="EMPLOYEE")
    body = _login(api, pw)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    sid = api.get(SESSIONS).json()[0]["id"]
    # The OTHER user cannot see or revoke it (404 — no existence leak).
    r2 = api.post(LOGIN, {"tenant_slug": "acme", "email": "b@acme.test", "password": pw}, format="json").json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r2['access']}")
    assert all(row["id"] != sid for row in api.get(SESSIONS).json())
    assert api.post(f"{SESSIONS}/{sid}/revoke", {}, format="json").status_code == 404
