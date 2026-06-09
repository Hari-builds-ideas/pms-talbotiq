"""
Tenant-aware caching helpers.

Cross-tenant cache isolation is a SECURITY control, not a convenience: every
cache key MUST embed the tenant id so one tenant can never read another tenant's
cached value by computing the same logical key. Build every key through
``tenant_cache_key`` and invalidate a tenant's entries through
``invalidate_tenant_cache``.
"""
from django.core.cache import caches

_TENANT_NAMESPACE = "tenant"


def tenant_cache_key(tenant_id, *parts):
    """Build a cache key namespaced to ``tenant_id``.

        tenant_cache_key("a1b2", "entitlement")   -> "tenant:a1b2:entitlement"
        tenant_cache_key("a1b2", "goals", 7)       -> "tenant:a1b2:goals:7"

    Two tenants computing the same logical ``parts`` always get distinct keys,
    so cached values cannot leak across the tenant boundary.
    """
    suffix = ":".join(str(p) for p in parts)
    return f"{_TENANT_NAMESPACE}:{tenant_id}:{suffix}"


def invalidate_tenant_cache(tenant_id, *parts, using="default"):
    """Delete cached entries for a tenant via glob pattern.

    With no ``parts`` this clears everything under ``tenant:<id>:`` for the given
    cache alias; pass ``parts`` to scope it (e.g. ``(tenant_id, "entitlement")``
    clears the exact ``tenant:<id>:entitlement`` key and any keys nested beneath
    it). Relies on django-redis ``delete_pattern`` (the configured cache backend).
    """
    # Append "*" to the exact key prefix so the glob matches BOTH the exact key
    # (tenant:<id>:entitlement) and any children (tenant:<id>:entitlement:...).
    # (Passing "*" as a trailing *part* would insert a ":" and miss the exact key.)
    base = tenant_cache_key(tenant_id, *parts)
    return caches[using].delete_pattern(f"{base}*")
