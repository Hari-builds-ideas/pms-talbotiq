"""
Hot-read caching properties (BUILD_4 4.4).

The billing reads (entitlement → feature flags / rate limits) are cached in Redis
under tenant-embedded keys with a TTL, and BUSTED by the writes that change them
(an entitlement upgrade). This asserts the four properties the contract requires:
a cache HIT does no DB work, the busting write INVALIDATES, keys are TENANT-
ISOLATED, and a cache OUTAGE degrades to a live query (never an error).
"""
import pytest
from django.test import override_settings

from apps.billing.services import (
    feature_flags_for,
    get_or_create_entitlement,
    rate_limits_for,
    upgrade_to_full_ai,
)

pytestmark = pytest.mark.django_db


def test_cache_hit_does_no_db_work(tenant, django_assert_num_queries):
    get_or_create_entitlement(tenant)
    rate_limits_for(tenant.id)  # miss → reads entitlement, populates cache
    with django_assert_num_queries(0):
        rate_limits_for(tenant.id)  # hit → served from Redis, zero DB queries


def test_upgrade_invalidates_the_cache(tenant):
    get_or_create_entitlement(tenant)
    before = feature_flags_for(tenant)  # STARTER flags (now cached)
    assert before.get("chat") is False or "chat" in before  # baseline present
    upgrade_to_full_ai(tenant)  # the busting write → invalidate_tenant_cache
    after = feature_flags_for(tenant)  # recomputed, not the stale cached map
    assert after != before  # the upgrade is reflected immediately, not after TTL


def test_cache_keys_are_tenant_isolated(tenant, other_tenant):
    get_or_create_entitlement(tenant)
    get_or_create_entitlement(other_tenant)
    upgrade_to_full_ai(other_tenant)  # only the OTHER tenant is lifted
    mine = rate_limits_for(tenant.id)  # STARTER (cached under my key)
    theirs = rate_limits_for(other_tenant.id)  # FULL_AI (cached under their key)
    assert mine != theirs  # one tenant's cached value is never served to another


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "redis://127.0.0.1:6399/0",  # nothing listening → refused
            "KEY_PREFIX": "pms",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,
            },
        },
        "sessions": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sess",
        },
    }
)
def test_cache_outage_degrades_to_a_live_query(tenant):
    get_or_create_entitlement(tenant)
    # Redis unreachable → IGNORE_EXCEPTIONS makes reads/writes no-op, so the read
    # recomputes from the DB and returns correct data WITHOUT raising.
    flags = feature_flags_for(tenant)
    assert "chat" in flags  # correct, recomputed value — not a 500
