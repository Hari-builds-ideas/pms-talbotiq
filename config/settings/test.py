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

# Don't persist DB connections in tests. The BUILD_3 read-replica alias adds a
# second connection; with CONN_MAX_AGE=60 (prod) a long suite could accumulate
# them. 0 = close after each use → no accumulation, no exhaustion. (close_old_
# connections is also skipped in eager Celery, so it can't tear down a test txn.)
for _db in DATABASES.values():  # noqa: F405
    _db["CONN_MAX_AGE"] = 0

# Global Tenant/User throttles OFF in tests (they'd add an entitlement lookup to
# every authed request and could trip on hot-loop tests); individual throttle
# tests enable what they need. KEEP the base "anon" rate so the AnonRateThrottle
# attached to the login views resolves a rate (an empty rates map makes
# SimpleRateThrottle.get_rate raise ImproperlyConfigured). The autouse cache-clear
# fixture resets throttle counters between tests; the anon-throttle test overrides
# the rate low to force a trip.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": ()}

# Fixed key so signed MFA tokens etc. are stable across the run.
SECRET_KEY = "test-secret-key-not-for-production"
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY  # noqa: F405

# AI is HERMETIC in tests: pin the default provider to NotConfigured and clear any
# real key the runtime env might carry, so the suite NEVER makes a real Groq call.
# Individual AI tests still @override_settings(LLM_PROVIDER=FakeLLMProvider).
LLM_PROVIDER = "apps.ai.providers.NotConfiguredProvider"
GROQ_API_KEY = ""
LLM_API_KEY = ""
LLM_MAX_CALLS = 0

# base.py points the agent seams at the real LangGraph agent providers (Module 10
# go-live). In tests we pin them back to each seam's NotConfiguredProvider so the
# "default → not configured → 503" seam tests stay true and no agent ever runs
# unless a test explicitly @override_settings the seam + a Fake provider.
REVIEW_ASSISTANT_PROVIDER = "apps.reviews.agent1.NotConfiguredProvider"
FEEDBACK_SUMMARIZER_PROVIDER = "apps.feedback.agent3.NotConfiguredProvider"
JD_GENERATOR_PROVIDER = "apps.jd.generator.NotConfiguredProvider"
SUCCESSION_ANALYZER_PROVIDER = "apps.succession.agent4.NotConfiguredProvider"
CAREER_ROADMAP_PROVIDER = "apps.career.roadmap_agent.NotConfiguredProvider"
