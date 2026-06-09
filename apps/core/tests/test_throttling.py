"""
Tests for the entitlement-driven throttles.

The global ``DEFAULT_THROTTLE_CLASSES`` are disabled in the test settings, so the
throttles are exercised explicitly here. ``rate_limits_for`` is patched to tiny,
deterministic limits so a bucket trips in a handful of requests rather than
hundreds. The conftest autouse fixture flushes the real-redis cache between
tests, so the rolling-window counters reset per test.

Coverage:
  * a bucket allows N requests then raises ``RateLimited`` (a real 429) on N+1;
  * the tenant bucket carries an upgrade hint; the user bucket does not;
  * the user bucket is isolated per user, and the tenant bucket per tenant
    (cross-tenant counter isolation — a tenant-isolation security control);
  * the AI bucket trips at its own limit with an upgrade hint;
  * an end-to-end HTTP 429 with a ``Retry-After`` header and the hint in the body;
  * the anon login throttle caps unauthenticated bursts per IP.
"""
import copy
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.core.throttling import AIThrottle, RateLimited, TenantThrottle, UserThrottle
from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

# Tiny, deterministic limits so buckets trip fast.
_FAKE_LIMITS = {"tenant": "3/min", "user": "5/min", "ai": "2/min"}
_PATCH_TARGET = "apps.core.throttling.rate_limits_for"


def _drf_request(user):
    request = APIRequestFactory().get("/probe/")
    force_authenticate(request, user=user)
    request.user = user  # APIRequestFactory doesn't run auth middleware
    return request


def _drain(throttle, user, limit):
    """Allow exactly ``limit`` requests, asserting each is permitted."""
    for _ in range(limit):
        assert throttle.allow_request(_drf_request(user), view=None) is True


def test_tenant_throttle_trips_on_n_plus_one_with_upgrade_hint():
    user = UserFactory()
    with patch(_PATCH_TARGET, return_value=_FAKE_LIMITS):
        throttle = TenantThrottle()
        _drain(throttle, user, 3)

        with pytest.raises(RateLimited) as exc:
            throttle.allow_request(_drf_request(user), view=None)

    err = exc.value
    assert err.status_code == 429
    assert err.wait is not None
    assert "upgrade_hint" in err.detail
    assert err.detail["scope"] == "tenant"


def test_user_throttle_independent_per_user_and_has_no_upgrade_hint():
    tenant = TenantFactory()
    noisy = UserFactory(tenant=tenant)
    quiet = UserFactory(tenant=tenant)

    with patch(_PATCH_TARGET, return_value=_FAKE_LIMITS):
        throttle = UserThrottle()
        # Exhaust the noisy user's personal bucket (limit 5).
        _drain(throttle, noisy, 5)
        with pytest.raises(RateLimited) as exc:
            throttle.allow_request(_drf_request(noisy), view=None)

        # A different user in the same tenant is unaffected (distinct cache key).
        assert throttle.allow_request(_drf_request(quiet), view=None) is True

    assert "upgrade_hint" not in exc.value.detail
    assert exc.value.status_code == 429


def test_tenant_throttle_counters_isolated_across_tenants():
    tenant_a = TenantFactory()
    tenant_b = TenantFactory()
    user_a = UserFactory(tenant=tenant_a)
    user_b = UserFactory(tenant=tenant_b)

    with patch(_PATCH_TARGET, return_value=_FAKE_LIMITS):
        throttle = TenantThrottle()
        # Trip tenant A's shared bucket.
        _drain(throttle, user_a, 3)
        with pytest.raises(RateLimited):
            throttle.allow_request(_drf_request(user_a), view=None)

        # Tenant B's bucket is a separate key — still allowed.
        assert throttle.allow_request(_drf_request(user_b), view=None) is True


def test_ai_throttle_trips_at_its_own_limit_with_upgrade_hint():
    user = UserFactory()
    with patch(_PATCH_TARGET, return_value=_FAKE_LIMITS):
        throttle = AIThrottle()
        _drain(throttle, user, 2)  # ai limit is 2/min
        with pytest.raises(RateLimited) as exc:
            throttle.allow_request(_drf_request(user), view=None)

    assert exc.value.status_code == 429
    assert "upgrade_hint" in exc.value.detail
    assert exc.value.detail["scope"] == "ai"


def test_anonymous_request_is_not_throttled():
    """Anonymous callers fall through these throttles (handled by AnonRateThrottle
    on the login surface), so allow_request returns True regardless of count."""

    class _Anon:
        is_authenticated = False
        pk = None
        tenant_id = None

    request = APIRequestFactory().get("/probe/")
    request.user = _Anon()
    throttle = TenantThrottle()
    for _ in range(10):
        assert throttle.allow_request(request, view=None) is True


@pytest.mark.urls("apps.core.tests.throttle_urls")
def test_end_to_end_429_has_retry_after_header_and_upgrade_hint():
    user = UserFactory()
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    probe = "/throttle-test/probe/"
    with patch(_PATCH_TARGET, return_value={"tenant": "2/min", "user": "5/min", "ai": "2/min"}):
        # Hot-loop until the tenant bucket trips (limit 2).
        resp = None
        for _ in range(6):
            resp = client.get(probe)
            if resp.status_code == 429:
                break

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.json().get("upgrade_hint")


def test_anon_login_throttle_caps_unauthenticated_bursts():
    from rest_framework.throttling import AnonRateThrottle

    # DRF binds SimpleRateThrottle.THROTTLE_RATES as a CLASS attribute at import
    # time, so override_settings(DEFAULT_THROTTLE_RATES=...) never reaches it.
    # Patch the class attribute directly to force a low anon rate. Throttling
    # runs in initial() before the serializer, so the trip is a 429 regardless of
    # the (empty) body; the autouse cache fixture resets the per-IP counter.
    with patch.object(AnonRateThrottle, "THROTTLE_RATES", {"anon": "3/min"}):
        client = APIClient()
        statuses = [
            client.post("/api/auth/login", {}, format="json").status_code
            for _ in range(4)
        ]

    # The 4th request from the same IP exceeds the 3/min anon rate.
    assert statuses[-1] == 429
