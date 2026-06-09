"""
Tests for ``rate_limits_for`` — the entitlement-derived rate map.

Proves the three halves of the contract:
  * the map is DERIVED from the entitlement (STARTER vs FULL_AI) and lifts after
    an upgrade — never hardcoded per call site;
  * the result is cached under a tenant-scoped key, so a warm second call issues
    ZERO DB queries (mirroring the entitlement-cache contract);
  * two tenants resolve INDEPENDENTLY (no cross-tenant bleed).

The conftest autouse fixture flushes the real-redis cache around every test, so
no warmed map leaks between tests.
"""
import pytest

from apps.billing.services import (
    _RATE_LIMITS_FULL_AI,
    _RATE_LIMITS_STARTER,
    rate_limits_for,
    set_seats,
    upgrade_to_full_ai,
)
from apps.core.cache import tenant_cache_key
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _rate_key(tenant):
    return tenant_cache_key(str(tenant.id), "rate_limits")


def test_starter_returns_starter_limits_full_ai_after_upgrade():
    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN")

    # STARTER default -> conservative limits.
    assert rate_limits_for(str(t.id)) == _RATE_LIMITS_STARTER

    # Upgrading invalidates the whole tenant namespace, so the next read derives
    # the FULL_AI (higher) limits — proving it's entitlement-driven, not static.
    upgrade_to_full_ai(t, actor=admin)
    after = rate_limits_for(str(t.id))
    assert after == _RATE_LIMITS_FULL_AI
    assert int(after["tenant"].split("/")[0]) > int(_RATE_LIMITS_STARTER["tenant"].split("/")[0])


def test_set_seats_invalidates_rate_limit_cache():
    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN")

    # Warm the rate-limit cache.
    rate_limits_for(str(t.id))
    from django.core.cache import cache

    assert cache.get(_rate_key(t)) is not None

    # set_seats clears the whole tenant namespace, so the rate-limit key is gone.
    set_seats(t, 10, actor=admin)
    assert cache.get(_rate_key(t)) is None


def test_warm_then_second_call_hits_cache_with_zero_queries(django_assert_num_queries):
    from django.core.cache import cache

    t = TenantFactory()

    # First call populates both the entitlement and rate-limit caches.
    rate_limits_for(str(t.id))
    assert cache.get(_rate_key(t)) is not None

    # Second call is served entirely from the cache: zero DB queries.
    with django_assert_num_queries(0):
        result = rate_limits_for(str(t.id))
    assert result == _RATE_LIMITS_STARTER


def test_two_tenants_resolve_independently():
    starter = TenantFactory()
    full = TenantFactory()
    admin = UserFactory(tenant=full, role="ADMIN")
    upgrade_to_full_ai(full, actor=admin)

    assert rate_limits_for(str(starter.id)) == _RATE_LIMITS_STARTER
    assert rate_limits_for(str(full.id)) == _RATE_LIMITS_FULL_AI
