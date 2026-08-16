"""
Suspending a tenant must end its sessions (C3).

Before this, ``Tenant.status`` was checked at login, SSO and password reset and
NOWHERE else. Suspending a tenant therefore did nothing to anyone already signed
in: their access token kept working for its full 15 minutes and their refresh
token kept rotating for up to 7 days. For suspend-for-non-payment or
suspend-for-breach, that window is the entire point of suspending.

The two tests that matter are the first two: a token that worked a moment ago
stops working, and the refresh endpoint refuses to mint a new one.
"""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.tenancy.models import Tenant
from apps.tenancy.status import tenant_is_active, tenant_status
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

PW = "pw12345!"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def signed_in(api):
    """A tenant, a user, and a live session (access + refresh)."""
    t = TenantFactory(slug="acme", status=Tenant.Status.ACTIVE)
    with tenant_context(t.id):
        UserFactory(tenant=t, email="u@acme.test", password=PW, role="ADMIN")
    tokens = api.post(
        "/api/auth/login",
        {"tenant_slug": "acme", "email": "u@acme.test", "password": PW},
        format="json",
    ).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return t, tokens


def _suspend(tenant, status=Tenant.Status.SUSPENDED):
    tenant.status = status
    tenant.save(update_fields=["status"])


# ── the two that matter ───────────────────────────────────────────────────────

def test_suspension_kills_a_live_access_token(api, signed_in):
    t, _tokens = signed_in
    # Works right now.
    assert api.get("/api/auth/me").status_code == 200

    _suspend(t)

    resp = api.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "tenant_inactive"


def test_suspension_blocks_refresh(api, signed_in):
    t, tokens = signed_in
    _suspend(t)

    fresh = APIClient()
    resp = fresh.post(
        "/api/auth/token/refresh", {"refresh": tokens["refresh"]}, format="json"
    )
    # Otherwise a suspended tenant could keep rotating a working session for the
    # refresh token's full 7-day lifetime.
    assert resp.status_code == 401
    assert resp.json()["code"] == "tenant_inactive"


# ── the shape of the refusal ──────────────────────────────────────────────────

def test_refusal_takes_effect_immediately_not_after_a_cache_ttl(api, signed_in):
    """The post_save signal invalidates the cached status, so the next request
    already sees it. Without that, "we suspended them" and "they stopped being
    served" are up to five minutes apart."""
    t, _tokens = signed_in
    # Warm the cache with the ACTIVE value.
    assert api.get("/api/auth/me").status_code == 200
    assert tenant_is_active(t.id) is True

    _suspend(t)

    # No sleep, no cache.clear() — the signal did it.
    assert tenant_is_active(t.id) is False
    assert api.get("/api/auth/me").status_code == 401


def test_cancelled_is_refused_too_not_just_suspended(api, signed_in):
    t, _tokens = signed_in
    _suspend(t, Tenant.Status.CANCELLED)
    assert api.get("/api/auth/me").status_code == 401


def test_reactivating_restores_access(api, signed_in):
    """Suspension has to be reversible without anyone re-issuing tokens."""
    t, _tokens = signed_in
    _suspend(t)
    assert api.get("/api/auth/me").status_code == 401

    t.status = Tenant.Status.ACTIVE
    t.save(update_fields=["status"])

    assert api.get("/api/auth/me").status_code == 200


def test_the_message_blames_the_workspace_not_the_person(api, signed_in):
    t, _tokens = signed_in
    _suspend(t)
    detail = api.get("/api/auth/me").json()["detail"]
    # An employee of a suspended tenant has done nothing wrong, and needs to know
    # who to ask rather than thinking their own account is in trouble.
    assert "workspace" in detail.lower()
    assert "administrator" in detail.lower() or "support" in detail.lower()


# ── the cost ──────────────────────────────────────────────────────────────────

def test_the_check_is_cached_so_it_does_not_add_a_query_per_request(api, signed_in):
    """This runs on every authenticated request, so it has to be a cache read."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    t, _tokens = signed_in
    tenant_status(t.id)  # warm

    with CaptureQueriesContext(connection) as ctx:
        for _ in range(5):
            tenant_status(t.id)
    assert len(ctx.captured_queries) == 0


def test_an_unknown_tenant_id_is_not_a_query_amplifier(signed_in):
    """A bogus tenant id in a token must not turn every request into a database
    lookup — that is a cheap way to make the auth path expensive."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    import uuid

    bogus = uuid.uuid4()
    assert tenant_is_active(bogus) is False
    with CaptureQueriesContext(connection) as ctx:
        for _ in range(5):
            tenant_is_active(bogus)
    assert len(ctx.captured_queries) == 0


# ── fail closed ───────────────────────────────────────────────────────────────

def test_status_fails_closed_when_it_cannot_be_read():
    """"Is this customer allowed to use the product" is not a question to answer
    optimistically when we do not know."""
    import apps.tenancy.models as tenancy_models

    cache.clear()

    class ExplodingManager:
        def filter(self, *a, **k):
            raise RuntimeError("database is having a moment")

    saved = tenancy_models.Tenant.objects
    try:
        tenancy_models.Tenant.objects = ExplodingManager()
        assert tenant_is_active("some-id") is False
    finally:
        tenancy_models.Tenant.objects = saved


# ── what must NOT break ───────────────────────────────────────────────────────

def test_unauthenticated_endpoints_are_untouched(api):
    """The check only applies to requests that carry a tenant-bound token, so the
    login surface and the probes keep working for a suspended tenant — otherwise
    nobody could ever be told why they are locked out."""
    t = TenantFactory(slug="acme", status=Tenant.Status.SUSPENDED)
    with tenant_context(t.id):
        UserFactory(tenant=t, email="u@acme.test", password=PW, role="ADMIN")

    assert api.get("/healthz").status_code == 200
    # Login itself already refused a non-ACTIVE tenant before C3, and still does.
    resp = api.post(
        "/api/auth/login",
        {"tenant_slug": "acme", "email": "u@acme.test", "password": PW},
        format="json",
    )
    assert resp.status_code in (400, 401)


def test_an_active_tenant_is_unaffected(api, signed_in):
    _t, _tokens = signed_in
    for _ in range(3):
        assert api.get("/api/auth/me").status_code == 200
