"""
Self-service password reset (FINAL F) — tenant-qualified, no-enumeration, audited,
and session-revoking. Email goes through Django's locmem backend in tests.
"""
import re

import pytest
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

REQUEST = "/api/auth/password-reset"
CONFIRM = "/api/auth/password-reset/confirm"
LOGIN = "/api/auth/login"
LOCMEM = {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


@pytest.fixture
def api():
    return APIClient()


def _mk_user(pw):
    t = TenantFactory(slug="acme")
    return t, UserFactory(tenant=t, email="a@acme.test", password=pw, role="EMPLOYEE")


def _link_params(body: str) -> dict:
    m = re.search(r"/reset-password\?tenant=(?P<tenant>[\w-]+)&uid=(?P<uid>[\w-]+)&token=(?P<token>[\w-]+)", body)
    assert m, f"no reset link in email body: {body!r}"
    return m.groupdict()


@override_settings(**LOCMEM)
def test_request_sends_link_and_confirm_resets_password(api):
    old_pw = "old-pw-12345!"
    t, user = _mk_user(old_pw)
    r = api.post(REQUEST, {"tenant_slug": "acme", "email": "a@acme.test"}, format="json")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["a@acme.test"]
    params = _link_params(mail.outbox[0].body)

    new_pw = "brand-new-pw-9!x"
    r = api.post(
        CONFIRM,
        {"tenant_slug": params["tenant"], "uid": params["uid"], "token": params["token"], "new_password": new_pw},
        format="json",
    )
    assert r.status_code == 200, r.content
    # New password logs in; the old one no longer does.
    ok = api.post(LOGIN, {"tenant_slug": "acme", "email": "a@acme.test", "password": new_pw}, format="json")
    assert ok.status_code == 200 and "access" in ok.json()
    bad = api.post(LOGIN, {"tenant_slug": "acme", "email": "a@acme.test", "password": old_pw}, format="json")
    assert bad.status_code == 401


@override_settings(**LOCMEM)
def test_request_never_enumerates_accounts(api):
    _mk_user("whatever-pw-1!")
    # Unknown email, unknown tenant: SAME 200 body, and no mail for unknown email.
    r1 = api.post(REQUEST, {"tenant_slug": "acme", "email": "ghost@acme.test"}, format="json")
    r2 = api.post(REQUEST, {"tenant_slug": "nope", "email": "a@acme.test"}, format="json")
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json() == {"ok": True}
    assert len(mail.outbox) == 0


@override_settings(**LOCMEM)
def test_confirm_rejects_bad_token_and_revokes_sessions_on_success(api):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

    pw = "old-pw-12345!"
    t, user = _mk_user(pw)
    # An active session (refresh token) exists before the reset.
    login = api.post(LOGIN, {"tenant_slug": "acme", "email": "a@acme.test", "password": pw}, format="json").json()
    refresh_before = login["refresh"]

    api.post(REQUEST, {"tenant_slug": "acme", "email": "a@acme.test"}, format="json")
    params = _link_params(mail.outbox[0].body)

    # Tampered token → the same generic 400 (no oracle).
    bad = api.post(
        CONFIRM,
        {"tenant_slug": "acme", "uid": params["uid"], "token": "tampered-token", "new_password": "another-pw-7!z"},
        format="json",
    )
    assert bad.status_code == 400

    # Real token → reset succeeds AND the pre-reset refresh token is dead.
    ok = api.post(
        CONFIRM,
        {"tenant_slug": "acme", "uid": params["uid"], "token": params["token"], "new_password": "another-pw-7!z"},
        format="json",
    )
    assert ok.status_code == 200
    assert BlacklistedToken.objects.filter(token__user=user).exists()
    refresh_try = api.post("/api/auth/token/refresh", {"refresh": refresh_before}, format="json")
    assert refresh_try.status_code == 401


@override_settings(**LOCMEM)
def test_confirm_enforces_password_validators(api):
    _mk_user("old-pw-12345!")
    api.post(REQUEST, {"tenant_slug": "acme", "email": "a@acme.test"}, format="json")
    params = _link_params(mail.outbox[0].body)
    r = api.post(
        CONFIRM,
        {"tenant_slug": "acme", "uid": params["uid"], "token": params["token"], "new_password": "short"},
        format="json",
    )
    assert r.status_code == 400
    assert "new_password" in r.json()
