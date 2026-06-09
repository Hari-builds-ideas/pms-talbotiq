"""
Test settings.

The database stays MySQL on purpose — the audit-log immutability triggers are
raw MySQL DDL and must be exercised for real (no SQLite shortcut). The cache is
real django-redis (not locmem) so cache behaviour — including django-redis-only
features like delete_pattern used for tenant cache invalidation — is exercised
exactly as in production. Dedicated scratch DBs (15/14) keep test data off the
dev cache/session DBs, and an autouse fixture (see conftest) flushes them per
test. The suite runs only inside the Docker stack, where Redis is always up.
"""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, REDIS_CACHE_URL, REST_FRAMEWORK

DEBUG = False

# Concrete fixtures (e.g. a concrete TenantScopedModel) — test-only app.
INSTALLED_APPS = [*INSTALLED_APPS, "apps.testsupport.apps.TestSupportConfig"]


def _redis_db(url, db):
    # Swap the logical DB number on a redis://host:port/N URL.
    base, _, _ = url.rpartition("/")
    return f"{base}/{db}"


# Real django-redis on dedicated scratch DBs so delete_pattern et al. behave as
# in prod; the autouse cache-clearing fixture in conftest isolates each test.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _redis_db(REDIS_CACHE_URL, 15),
        "KEY_PREFIX": "pms-test",
        "TIMEOUT": 300,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
    "sessions": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _redis_db(REDIS_CACHE_URL, 14),
        "KEY_PREFIX": "pms-test-sess",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
}

# Run Celery tasks inline so async flows are deterministic in tests.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Throttling off in tests to avoid order-dependent flakiness.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": (), "DEFAULT_THROTTLE_RATES": {}}

# Fixed key so signed MFA tokens etc. are stable across the run.
SECRET_KEY = "test-secret-key-not-for-production"
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY  # noqa: F405
