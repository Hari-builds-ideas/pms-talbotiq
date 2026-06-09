"""
Tests for the per-tenant entitlement cache.

Covers the two halves of the contract:
  * the READ path (``get_entitlement_cached`` / ``tenant_has_agent``) is served
    from a tenant-scoped cache key after the first load — a second read hits the
    cache and issues ZERO DB queries;
  * the MUTATION paths (``upgrade_to_full_ai``, ``set_seats``) invalidate that
    key via ``delete_pattern``, so the next read repopulates with fresh state.

The project conftest's autouse fixture flushes the (real-redis) cache around
every test, so these tests never see another test's cached entry.
"""
import pytest

from apps.billing.services import (
    get_entitlement_cached,
    set_seats,
    tenant_has_agent,
    upgrade_to_full_ai,
)
from apps.core.cache import tenant_cache_key
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _key(tenant):
    return tenant_cache_key(str(tenant.id), "entitlement")


def test_cached_read_populates_then_serves_without_db(django_assert_num_queries):
    from django.core.cache import cache

    t = TenantFactory()

    # First read populates the cache (STARTER default provisioned).
    get_entitlement_cached(t)
    assert cache.get(_key(t)) is not None

    # Second read is served entirely from the cache: zero DB queries.
    with django_assert_num_queries(0):
        get_entitlement_cached(t)


def test_upgrade_invalidates_cache_and_fresh_read_reflects_full_ai():
    from django.core.cache import cache

    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN")

    # Warm the cache on STARTER — agent3 is locked.
    get_entitlement_cached(t)
    assert tenant_has_agent(t, "agent3") is False
    assert cache.get(_key(t)) is not None

    # Mutating to FULL_AI invalidates the tenant's cached entitlement.
    upgrade_to_full_ai(t, actor=admin)
    assert cache.get(_key(t)) is None

    # A fresh read repopulates and reflects the unlocked agent.
    assert tenant_has_agent(t, "agent3") is True


def test_set_seats_invalidates_cache_and_fresh_read_reflects_new_seats():
    from django.core.cache import cache

    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN")

    # Warm the cache, then change seats.
    get_entitlement_cached(t)
    assert cache.get(_key(t)) is not None

    set_seats(t, 25, actor=admin)
    assert cache.get(_key(t)) is None

    assert get_entitlement_cached(t).seat_count == 25
