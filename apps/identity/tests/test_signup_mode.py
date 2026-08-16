"""
Invite-only signup (C7).

Self-serve signup hands out a real workspace on a real plan that no invoice can
follow, because checkout cannot take money yet (C8). Closing it is the honest
posture until billing works; the switch back is one env var.

What must NOT change in either mode: the invitation flow. Existing customers
onboard their own people regardless.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.tenancy.models import Tenant
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

SIGNUP_URL = "/api/auth/signup"
CONFIG_URL = "/api/auth/public-config"
PW = "pw12345!"

BODY = {
    "org_name": "New Co",
    "display_name": "Jordan Lee",
    "email": "jordan@newco.test",
    "password": "a-long-enough-passphrase-9",
}


@pytest.fixture
def api():
    return APIClient()


def test_signup_is_closed_by_default(api):
    # No override: the shipped default must be the safe one.
    resp = api.post(SIGNUP_URL, BODY, format="json")
    assert resp.status_code == 403
    assert resp.json()["code"] == "signup_invite_only"
    # And nothing was created.
    assert not Tenant.objects.filter(slug="new-co").exists()


def test_the_refusal_tells_the_visitor_what_to_do(api):
    resp = api.post(SIGNUP_URL, BODY, format="json")
    detail = resp.json()["detail"]
    assert "invitation" in detail.lower()
    # A dead end with no next step is worse than a 404.
    assert "touch" in detail.lower() or "contact" in detail.lower()


@override_settings(SUPPORT_EMAIL="hello@example.com")
def test_the_support_address_is_included_when_configured(api):
    assert api.post(SIGNUP_URL, BODY, format="json").json()["support_email"] == (
        "hello@example.com"
    )


@override_settings(SUPPORT_EMAIL="")
def test_no_placeholder_address_is_invented(api):
    # Better to omit it than to print an address nobody reads.
    assert api.post(SIGNUP_URL, BODY, format="json").json()["support_email"] is None


@override_settings(SIGNUP_MODE="open")
def test_one_env_var_opens_it_again(api):
    resp = api.post(SIGNUP_URL, BODY, format="json")
    assert resp.status_code == 201
    assert Tenant.objects.filter(slug="new-co").exists()
    assert resp.json()["tenant_slug"] == "new-co"


def test_invitations_still_work_while_signup_is_closed(api):
    """The whole point: existing customers must keep onboarding their people."""
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        UserFactory(tenant=t, email="admin@acme.test", password=PW, role="ADMIN")
    tokens = api.post(
        "/api/auth/login",
        {"tenant_slug": "acme", "email": "admin@acme.test", "password": PW},
        format="json",
    ).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    resp = api.post(
        "/api/admin/invitations", {"email": "new@acme.test", "role": "EMPLOYEE"},
        format="json",
    )
    assert resp.status_code in (200, 201)


# ── the public config the SPA reads ───────────────────────────────────────────

def test_public_config_reports_signup_closed(api):
    body = api.get(CONFIG_URL).json()
    assert body["signup_open"] is False


@override_settings(SIGNUP_MODE="open")
def test_public_config_reports_signup_open(api):
    assert api.get(CONFIG_URL).json()["signup_open"] is True


def test_public_config_needs_no_auth(api):
    # It is what the login page reads before anyone has signed in.
    assert api.get(CONFIG_URL).status_code == 200


def test_public_config_leaks_nothing(api):
    """Only facts already visible to an anonymous visitor."""
    body = api.get(CONFIG_URL).json()
    assert set(body) == {"signup_open", "support_email", "google_sso", "app_name"}
