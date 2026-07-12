"""
PHASE2 L1.1 — self-service profile & account security. Self-scoped everywhere;
the avatar read uses the standard data-scope rule.
"""
import io

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

PROFILE = "/api/auth/profile"
LOCMEM = {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}

# Test-fixture credentials (not secrets).
PW_MGR = "pw-mgr-123!"
PW_EMP = "pw-emp-123!"
PW_PEER = "pw-peer-123!"
PW_ADMIN = "pw-adm-123!"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # magic bytes + padding


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@pytest.fixture
def org2():
    t = TenantFactory(slug="acme")
    mgr = UserFactory(tenant=t, email="m@acme.test", password=PW_MGR, role="MANAGER")
    emp = UserFactory(tenant=t, email="e@acme.test", password=PW_EMP, role="EMPLOYEE", manager=mgr)
    peer = UserFactory(tenant=t, email="p@acme.test", password=PW_PEER, role="EMPLOYEE")
    return t, mgr, emp, peer


def test_profile_get_and_self_edit(org2):
    t, mgr, emp, peer = org2
    c = _client(emp)
    body = c.get(PROFILE).json()
    assert body["email"] == "e@acme.test" and body["timezone"] == "UTC"
    r = c.patch(PROFILE, {"phone": "+60 12-345 6789", "timezone": "Asia/Kuala_Lumpur",
                          "language": "en", "preferences": {"notifications": {"email": True}}},
                format="json")
    assert r.status_code == 200, r.content
    assert r.json()["timezone"] == "Asia/Kuala_Lumpur"
    assert r.json()["preferences"]["notifications"]["email"] is True
    # Unknown timezone rejected; org-controlled fields NOT accepted here.
    assert c.patch(PROFILE, {"timezone": "Mars/Olympus"}, format="json").status_code == 400
    r = c.patch(PROFILE, {"title": "CEO"}, format="json")
    assert r.status_code == 200 and r.json()["title"] == ""  # silently ignored (not a field)


def test_photo_upload_validation_and_scoped_read(org2):
    t, mgr, emp, peer = org2
    c = _client(emp)
    # Not an image → 400. Too big → 400. Real PNG magic → 200.
    bad = io.BytesIO(b"#!/bin/sh evil")
    bad.name = "x.png"
    assert c.put("/api/auth/profile/photo", {"photo": bad}, format="multipart").status_code == 400
    big = io.BytesIO(PNG + b"\x00" * (2 * 1024 * 1024))
    big.name = "big.png"
    assert c.put("/api/auth/profile/photo", {"photo": big}, format="multipart").status_code == 400
    ok = io.BytesIO(PNG)
    ok.name = "avatar.png"
    assert c.put("/api/auth/profile/photo", {"photo": ok}, format="multipart").status_code == 200
    # The manager (in scope) can read it; the peer (out of scope) gets 404.
    assert _client(mgr).get(f"/api/auth/users/{emp.id}/photo").status_code == 200
    assert _client(peer).get(f"/api/auth/users/{emp.id}/photo").status_code == 404


def test_password_change_revokes_other_sessions(org2):
    t, mgr, emp, peer = org2
    api = APIClient()
    login = api.post("/api/auth/login", {"tenant_slug": "acme", "email": "e@acme.test",
                                         "password": PW_EMP}, format="json").json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    r = api.post("/api/auth/password-change",
                 {"current_password": PW_EMP, "new_password": "a-new-strong-pw-9!"},
                 format="json")
    assert r.status_code == 200 and "access" in r.json()
    # The OLD refresh token is dead; the returned fresh pair works.
    assert api.post("/api/auth/token/refresh", {"refresh": login["refresh"]}, format="json").status_code == 401
    assert api.post("/api/auth/token/refresh", {"refresh": r.json()["refresh"]}, format="json").status_code == 200
    # Wrong current password → 400.
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert api.post("/api/auth/password-change",
                    {"current_password": "nope", "new_password": "whatever-1!x"},
                    format="json").status_code == 400


@override_settings(**LOCMEM)
def test_email_change_flow(org2):
    from django.core import mail

    t, mgr, emp, peer = org2
    c = _client(emp)
    # Duplicate email in tenant rejected; wrong password rejected.
    assert c.post("/api/auth/email-change", {"new_email": "m@acme.test", "current_password": PW_EMP},
                  format="json").status_code == 400
    assert c.post("/api/auth/email-change", {"new_email": "new@acme.test", "current_password": "nope"},
                  format="json").status_code == 400
    r = c.post("/api/auth/email-change", {"new_email": "new@acme.test", "current_password": PW_EMP},
               format="json")
    assert r.status_code == 200 and len(mail.outbox) == 1 and mail.outbox[0].to == ["new@acme.test"]
    token = mail.outbox[0].body.split("email_change_token=")[1].split()[0]
    ok = c.post("/api/auth/email-change/confirm", {"token": token}, format="json")
    assert ok.status_code == 200 and ok.json()["email"] == "new@acme.test"
    emp.refresh_from_db()
    assert emp.email == "new@acme.test"
    # Replays with a tampered token fail generically.
    assert c.post("/api/auth/email-change/confirm", {"token": token + "x"}, format="json").status_code == 400


def test_my_activity_is_self_only(org2):
    t, mgr, emp, peer = org2
    c = _client(emp)
    c.patch(PROFILE, {"phone": "123"}, format="json")  # creates an audited action
    acts = c.get("/api/auth/my-activity").json()
    assert any(a["action"] == "profile.updated" for a in acts)
    # The peer's activity list does NOT contain emp's action.
    peer_acts = _client(peer).get("/api/auth/my-activity").json()
    assert all(a["action"] != "profile.updated" for a in peer_acts)


def test_admin_sets_org_fields(org2):
    t, mgr, emp, peer = org2
    admin = UserFactory(tenant=t, email="ad@acme.test", password=PW_ADMIN, role="ADMIN")
    r = _client(admin).patch(f"/api/admin/users/{emp.id}/profile",
                             {"title": "Engineer II", "department": "Engineering", "employee_id": "E-042"},
                             format="json")
    assert r.status_code == 200, r.content
    emp.refresh_from_db()
    assert emp.title == "Engineer II" and emp.employee_id == "E-042"
    # A manager cannot (Admin-only capability).
    assert _client(mgr).patch(f"/api/admin/users/{emp.id}/profile", {"title": "X"},
                              format="json").status_code == 403
