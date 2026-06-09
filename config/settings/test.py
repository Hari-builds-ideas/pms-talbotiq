"""
Test settings.

The database stays MySQL on purpose — the audit-log immutability triggers are
raw MySQL DDL and must be exercised for real (no SQLite shortcut). Cache and
Celery are made hermetic so the suite does not depend on a running Redis.
"""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, REST_FRAMEWORK

DEBUG = False

# Concrete fixtures (e.g. a concrete TenantScopedModel) — test-only app.
INSTALLED_APPS = [*INSTALLED_APPS, "apps.testsupport.apps.TestSupportConfig"]

# Hermetic, in-process cache + sessions — no external Redis needed for tests.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

# Run Celery tasks inline so async flows are deterministic in tests.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Throttling off in tests to avoid order-dependent flakiness.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": (), "DEFAULT_THROTTLE_RATES": {}}

# Fixed key so signed MFA tokens etc. are stable across the run.
SECRET_KEY = "test-secret-key-not-for-production"
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY  # noqa: F405
