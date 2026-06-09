"""
Statelessness verification (Phase 1.5a, decision 1).

The web tier must be safe to run as N identical replicas. The one piece of
per-request state — the current-tenant contextvar — is set by TenantMiddleware
from the verified JWT and reset in a ``finally``. These tests prove it does not
bleed between requests handled on the same worker thread.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import get_current_tenant_id, is_request_active
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.tenancy.tests.urls")]


def test_fresh_request_starts_with_no_tenant_bound():
    resp = APIClient().get("/whoami-tenant")
    assert resp.json()["tenant"] is None


def test_tenant_context_does_not_bleed_across_requests():
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="a@acme.test")
    access, _ = issue_tokens_for_user(user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r1 = client.get("/whoami-tenant")
    assert r1.json()["tenant"] == str(t.id)

    # Same client/thread, now unauthenticated: the previous request's tenant must
    # NOT still be bound (it was reset in finally).
    client.credentials()
    r2 = client.get("/whoami-tenant")
    assert r2.json()["tenant"] is None


def test_no_global_state_leaks_to_test_thread():
    # Outside any request, nothing is bound and no request is marked active —
    # i.e. the contextvars default to clean and are always reset.
    assert get_current_tenant_id() is None
    assert is_request_active() is False
