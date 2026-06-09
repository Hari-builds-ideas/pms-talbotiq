import pytest
from django.core.cache import cache

from apps.core.cache import invalidate_tenant_cache, tenant_cache_key


def test_same_logical_key_differs_across_tenants():
    # The core isolation guarantee: identical logical parts, different tenants,
    # NEVER collide.
    key_a = tenant_cache_key("tenant-a", "entitlement")
    key_b = tenant_cache_key("tenant-b", "entitlement")
    assert key_a != key_b
    assert "tenant-a" in key_a
    assert "tenant-b" in key_b


def test_key_includes_all_parts():
    assert tenant_cache_key("t1", "goals", 7) == "tenant:t1:goals:7"


@pytest.mark.django_db
def test_cached_values_are_isolated_per_tenant():
    cache.set(tenant_cache_key("a", "entitlement"), "A-value")
    cache.set(tenant_cache_key("b", "entitlement"), "B-value")
    # One tenant cannot read the other's value via the "same" logical key.
    assert cache.get(tenant_cache_key("a", "entitlement")) == "A-value"
    assert cache.get(tenant_cache_key("b", "entitlement")) == "B-value"


@pytest.mark.django_db
def test_invalidate_clears_only_that_tenant():
    cache.set(tenant_cache_key("a", "entitlement"), "A-value")
    cache.set(tenant_cache_key("a", "goals"), "A-goals")
    cache.set(tenant_cache_key("b", "entitlement"), "B-value")

    invalidate_tenant_cache("a")

    assert cache.get(tenant_cache_key("a", "entitlement")) is None
    assert cache.get(tenant_cache_key("a", "goals")) is None
    # Tenant B is untouched.
    assert cache.get(tenant_cache_key("b", "entitlement")) == "B-value"
