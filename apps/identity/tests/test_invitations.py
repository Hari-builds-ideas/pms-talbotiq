"""
PHASE2 L1.2 — invitation-based onboarding. Proofs: the full invite→accept loop,
role/capability gating (HRBP+ invite; Employee 403), revocation beats a sent
link, seat enforcement at accept, tenant isolation, single-use.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.invite_views import _invite_token
from apps.identity.models import Invitation, User
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

ADMIN_INVITES = "/api/admin/invitations"
PW_HRBP = "pw-hrbp-123!"
NEW_PW = "welcome-strong-1!"
LOCMEM = {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@pytest.fixture
def org3():
    t = TenantFactory(slug="acme")
    hrbp = UserFactory(tenant=t, email="h@acme.test", password=PW_HRBP, role="HRBP")
    emp = UserFactory(tenant=t, email="e@acme.test", password=PW_HRBP, role="EMPLOYEE")
    # Generous seats by default (tests that need a tight limit set it themselves).
    from apps.billing.services import get_or_create_entitlement, set_seats
    with tenant_context(t):
        get_or_create_entitlement(t.id)
        set_seats(t, 50)
    return t, hrbp, emp


@override_settings(**LOCMEM)
def test_full_invite_accept_loop(org3):
    from django.core import mail

    t, hrbp, emp = org3
    c = _client(hrbp)
    r = c.post(ADMIN_INVITES, {"email": "newhire@acme.test", "role": "EMPLOYEE"}, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["emailed"] is True and "accept-invite?token=" in body["invite_url"]
    assert mail.outbox[0].to == ["newhire@acme.test"]
    token = body["invite_url"].split("token=")[1]

    api = APIClient()
    # Public detail shows what they're joining.
    detail = api.get(f"/api/auth/invitations/{token}").json()
    assert detail == {"email": "newhire@acme.test", "tenant_name": t.name, "role": "EMPLOYEE"}
    # Accept → the user exists in THIS tenant with the invited role and can log in.
    ok = api.post(f"/api/auth/invitations/{token}/accept",
                  {"display_name": "New Hire", "password": NEW_PW}, format="json")
    assert ok.status_code == 201, ok.content
    login = api.post("/api/auth/login", {"tenant_slug": "acme", "email": "newhire@acme.test",
                                         "password": NEW_PW}, format="json")
    assert login.status_code == 200 and "access" in login.json()
    with tenant_context(t):
        u = User.objects.get(email="newhire@acme.test")
        assert u.role == "EMPLOYEE" and u.display_name == "New Hire"
    # Single-use: the link is dead after acceptance.
    assert api.post(f"/api/auth/invitations/{token}/accept",
                    {"password": NEW_PW}, format="json").status_code == 404


def test_only_hrbp_up_can_invite_and_revocation_wins(org3):
    t, hrbp, emp = org3
    assert _client(emp).post(ADMIN_INVITES, {"email": "x@acme.test"}, format="json").status_code == 403
    c = _client(hrbp)
    body = c.post(ADMIN_INVITES, {"email": "x@acme.test", "role": "MANAGER"}, format="json").json()
    token = body["invite_url"].split("token=")[1]
    assert c.post(f"{ADMIN_INVITES}/{body['id']}/revoke", {}, format="json").status_code == 200
    # The already-sent link no longer works (revocation beats delivery).
    api = APIClient()
    assert api.get(f"/api/auth/invitations/{token}").status_code == 404
    assert api.post(f"/api/auth/invitations/{token}/accept",
                    {"password": NEW_PW}, format="json").status_code == 404


@override_settings(**LOCMEM)
def test_resend_reissues_a_working_link_and_is_pending_only(org3):
    from django.core import mail

    t, hrbp, emp = org3
    c = _client(hrbp)
    body = c.post(ADMIN_INVITES, {"email": "slow@acme.test", "role": "EMPLOYEE"}, format="json").json()
    # Employee cannot resend (capability gate).
    assert _client(emp).post(f"{ADMIN_INVITES}/{body['id']}/resend", {}, format="json").status_code == 403
    r = c.post(f"{ADMIN_INVITES}/{body['id']}/resend", {}, format="json")
    assert r.status_code == 200, r.content
    resent = r.json()
    assert resent["emailed"] is True and len(mail.outbox) == 2
    assert mail.outbox[1].to == ["slow@acme.test"]
    # The re-sent link is valid and accepts.
    token = resent["invite_url"].split("token=")[1]
    api = APIClient()
    assert api.get(f"/api/auth/invitations/{token}").status_code == 200
    assert api.post(f"/api/auth/invitations/{token}/accept",
                    {"password": NEW_PW}, format="json").status_code == 201
    # Non-pending (now ACCEPTED) can NOT be resent — no revival.
    assert c.post(f"{ADMIN_INVITES}/{body['id']}/resend", {}, format="json").status_code == 409
    # A revoked invite can't be resent either.
    body2 = c.post(ADMIN_INVITES, {"email": "gone@acme.test"}, format="json").json()
    c.post(f"{ADMIN_INVITES}/{body2['id']}/revoke", {}, format="json")
    assert c.post(f"{ADMIN_INVITES}/{body2['id']}/resend", {}, format="json").status_code == 409


def test_duplicate_email_and_pending_dup_rejected(org3):
    t, hrbp, emp = org3
    c = _client(hrbp)
    assert c.post(ADMIN_INVITES, {"email": "e@acme.test"}, format="json").status_code == 422
    assert c.post(ADMIN_INVITES, {"email": "y@acme.test"}, format="json").status_code == 201
    assert c.post(ADMIN_INVITES, {"email": "y@acme.test"}, format="json").status_code == 422


def test_seats_enforced_at_accept(org3):
    from apps.billing.services import set_seats

    t, hrbp, emp = org3
    with tenant_context(t):
        set_seats(t, 2)  # exactly the two existing users — tenant is full
    c = _client(hrbp)
    body = c.post(ADMIN_INVITES, {"email": "z@acme.test"}, format="json").json()
    token = body["invite_url"].split("token=")[1]
    r = APIClient().post(f"/api/auth/invitations/{token}/accept",
                         {"password": NEW_PW}, format="json")
    assert r.status_code == 409
    assert "seat" in r.json()["detail"].lower()


def test_tampered_token_is_generic_404(org3):
    t, hrbp, emp = org3
    with tenant_context(t):
        inv = Invitation.objects.create(
            tenant_id=t.id, email="q@acme.test", invited_by=hrbp
        )
    token = _invite_token(inv)
    api = APIClient()
    assert api.get(f"/api/auth/invitations/{token}x").status_code == 404
    assert api.post(f"/api/auth/invitations/{token}x/accept",
                    {"password": NEW_PW}, format="json").status_code == 404
