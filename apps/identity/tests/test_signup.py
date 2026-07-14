"""PROD_B — public self-serve workspace signup.

Covers the abuse/tenant-isolation boundary: signup is public + throttled, creates a
new tenant and first ADMIN server-side, provisions Starter seats/subscription, and
returns tenant-scoped JWTs.  A new tenant must not see existing tenant data.
"""
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Entitlement, Subscription
from apps.identity.models import User
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

SIGNUP = "/api/auth/signup"


def test_public_signup_creates_isolated_tenant_first_admin_and_tokens(settings, mailoutbox):
    settings.SIGNUP_DEFAULT_SEATS = 7
    existing = TenantFactory(slug="acme", name="Acme")
    UserFactory(tenant=existing, email="ghost@acme.test", role="ADMIN")

    resp = APIClient().post(
        SIGNUP,
        {
            "org_name": "Beta Works",
            "display_name": "Bea Admin",
            "email": "bea@beta.example",
            "password": "Str0ngSignup!234",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["tenant_slug"] == "beta-works"
    assert body["workspace_name"] == "Beta Works"
    assert body["access"] and body["refresh"]

    tenant = Tenant.objects.get(slug="beta-works")
    token = AccessToken(body["access"])
    assert str(token["tenant_id"]) == str(tenant.id)
    assert token["role"] == User.Role.ADMIN

    with tenant_context(tenant.id):
        admin = User.objects.get(email="bea@beta.example")
        assert admin.role == User.Role.ADMIN
        assert admin.display_name == "Bea Admin"
        assert User.objects.count() == 1  # no existing-tenant leakage
        assert Entitlement.objects.get().seat_count == 7
        assert Subscription.objects.get().plan == Subscription.Plan.STARTER

    with tenant_context(existing.id):
        assert User.objects.filter(email="ghost@acme.test").exists()
        assert User.objects.filter(email="bea@beta.example").count() == 0

    assert len(mailoutbox) == 1
    assert "Workspace ID: beta-works" in mailoutbox[0].body


def test_signup_duplicate_or_reserved_slug_gets_safe_unique_slug():
    TenantFactory(slug="acme")
    resp = APIClient().post(
        SIGNUP,
        {
            "org_name": "ACME",
            "display_name": "Ada Admin",
            "email": "ada@newacme.example",
            "password": "Str0ngSignup!234",
            "workspace_slug": "acme",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["tenant_slug"] == "acme-2"
    assert Tenant.objects.filter(slug="acme").count() == 1
    assert Tenant.objects.filter(slug="acme-2").exists()


def test_signup_rejects_weak_password_and_does_not_create_tenant():
    before = Tenant.objects.count()
    resp = APIClient().post(
        SIGNUP,
        {
            "org_name": "Weak Co",
            "display_name": "Weak Admin",
            "email": "weak@example.com",
            "password": "password",
        },
        format="json",
    )

    assert resp.status_code == 400
    assert Tenant.objects.count() == before


def test_signup_endpoint_uses_atomic_anon_throttle():
    from apps.core.throttling import AtomicAnonThrottle
    from apps.identity.signup_views import SignupView

    assert SignupView.throttle_classes == [AtomicAnonThrottle]
