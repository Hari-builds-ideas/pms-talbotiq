"""
Base settings shared by every environment.

Environment-specific modules (dev/prod/test) import * from here and override.
All secrets and environment-dependent values are read from the environment via
django-environ; see .env.example for the full documented variable list.
"""
from datetime import timedelta
from pathlib import Path

import environ

# project root: .../config/settings/base.py -> parents[2]
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
# Load .env if present (no-op when absent, e.g. inside containers using env vars).
environ.Env.read_env(BASE_DIR / ".env")

# ─── Core ──────────────────────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Applications ──────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
    # Health/readiness probes (used by /readyz). The Celery broker check is a
    # custom backend registered in apps.core.apps.CoreConfig.ready().
    "health_check",
    "health_check.db",
    "health_check.cache",
    "health_check.contrib.migrations",
    "health_check.contrib.redis",
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.tenancy.apps.TenancyConfig",
    "apps.identity.apps.IdentityConfig",
    "apps.rbac.apps.RbacConfig",
    "apps.audit.apps.AuditConfig",
    "apps.billing.apps.BillingConfig",
    # Module 2 — Goals & KPI engine
    "apps.cycles.apps.CyclesConfig",
    "apps.goals.apps.GoalsConfig",
    # Module 3 — Reviews & Appraisal Cycles
    "apps.reviews.apps.ReviewsConfig",
    # Module 4 — 360° Feedback & anonymisation
    "apps.feedback.apps.FeedbackConfig",
    # Module 5 — Approval Workflows
    "apps.approvals.apps.ApprovalsConfig",
    # Module 6 — JD Library & AI JD Generator
    "apps.jd.apps.JdConfig",
    # Module 7 — Live Org Chart
    "apps.org.apps.OrgConfig",
    # Module 8 — Succession & Talent
    "apps.succession.apps.SuccessionConfig",
    # Module 9 — Career Development (Roadmap LITE)
    "apps.career.apps.CareerConfig",
    # Module 11 — Administration (Admin Hub: tenant/user/role config)
    "apps.administration.apps.AdministrationConfig",
    # Module A — Analytics & Reporting
    "apps.analytics.apps.AnalyticsConfig",
    # Module 12 — Integrations (Jira + Slack)
    "apps.integrations.apps.IntegrationsConfig",
    # Module 10 — AI Agents (LLM Gateway + LangGraph)
    "apps.ai.apps.AiConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ────────────────────────────────────────────────────────
# TenantMiddleware is last so it runs closest to the view: it resolves the
# current tenant from the cryptographically verified JWT *after* auth, sets the
# contextvar before the view executes, and resets it immediately afterwards.
MIDDLEWARE = [
    # Outermost: stamp a request id into a contextvar before anything else, so
    # every log line + Sentry event for this request is correlatable. Reset in
    # finally (no cross-request bleed).
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.tenancy.middleware.TenantMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ─── Database (MySQL 8) ────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", default="pms"),
        "USER": env("DB_USER", default="pms"),
        "PASSWORD": env("DB_PASSWORD", default="pmspw"),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="3306"),
        # Persistent connections (held per worker thread for up to 60s) reduce
        # connect churn under horizontal scaling; CONN_HEALTH_CHECKS revalidates
        # a reused connection before each request so a stale/killed connection is
        # transparently replaced instead of erroring.
        #
        # MySQL max_connections sizing (the mysql service caps at 100):
        #   peak_conns ≈ web_replicas × gunicorn_workers × threads
        #               + celery_worker_concurrency + headroom
        # e.g. 3 replicas × 9 workers × 2 threads = 54, + celery + buffer < 100.
        # Raise --max-connections (and DB resources) before scaling past that.
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "charset": "utf8mb4",
            # Strict mode: surface bad data as errors instead of silent truncation.
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "TEST": {
            "CHARSET": "utf8mb4",
            "COLLATION": "utf8mb4_unicode_ci",
        },
    }
}

# ─── Cache + sessions (Redis 7) ────────────────────────────────────────
# Redis is split by logical DB so cache pressure can never disturb queued work:
#   /0 → Celery broker + results   (must be noeviction — see docker-compose)
#   /1 → application cache          (TTL'd; safe to evict)
#   /2 → sessions
REDIS_CACHE_URL = env("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1")
REDIS_SESSION_URL = env("REDIS_SESSION_URL", default="redis://127.0.0.1:6379/2")
# health_check.contrib.redis pings this URL; point it at the cache DB.
REDIS_URL = REDIS_CACHE_URL

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "KEY_PREFIX": "pms",
        "TIMEOUT": 300,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
    "sessions": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_SESSION_URL,
        "KEY_PREFIX": "pms-sess",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
}
# Sessions live in their own Redis DB (per the Module 1 login workflow:
# "write session to Redis"), isolated from the application cache.
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "sessions"

# ─── Auth: users, password hashing (Argon2), validators ────────────────
AUTH_USER_MODEL = "identity.User"

AUTHENTICATION_BACKENDS = [
    # Tenant-aware: resolves the session principal by its globally-unique pk
    # before a tenant is bound (the scoped default manager fails closed).
    "apps.identity.backends.TenantModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Argon2 first per CLAUDE.md.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# email is unique *per tenant* (enforced by a UniqueConstraint on the User
# model), not globally — so the USERNAME_FIELD-must-be-globally-unique check
# is intentionally silenced. Tenant scoping makes per-tenant uniqueness correct.
SILENCED_SYSTEM_CHECKS = ["auth.E003", "auth.W004"]

# ─── Django REST Framework ─────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Per-tenant and per-user limits, both resolved from the tenant's entitlement
    # at request time (see apps/core/throttling.py). Anonymous requests fall
    # through these (handled by AnonRateThrottle on the login surface). AIThrottle
    # exists + is tested but is attached per-view (Module 10), not globally.
    "DEFAULT_THROTTLE_CLASSES": (
        "apps.core.throttling.TenantThrottle",
        "apps.core.throttling.UserThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # Only the IP-based anon scope (login) reads its rate from here; the
        # tenant/user/ai rates come from rate_limits_for(tenant).
        "anon": env("THROTTLE_ANON", default="100/min"),
    },
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

# ─── simplejwt ─────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    # Custom claims (tenant_id, role, email) are stamped on the refresh token and
    # simplejwt's RefreshToken.access_token copies them, so the default refresh
    # serializer already preserves them across rotation — no override needed.
}

# ─── allauth / OIDC ────────────────────────────────────────────────────
SITE_ID = 1
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = True
# Custom adapter maps a verified OIDC identity onto an existing tenant user.
SOCIALACCOUNT_ADAPTER = "apps.identity.adapters.TenantSocialAccountAdapter"
# Slug an OIDC identity falls back to when the login carries no tenant hint.
OIDC_DEFAULT_TENANT_SLUG = env("OIDC_DEFAULT_TENANT_SLUG", default="")
SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": env("OIDC_PROVIDER_ID", default="oidc-demo"),
                "name": env("OIDC_PROVIDER_NAME", default="Demo OIDC"),
                "client_id": env("OIDC_CLIENT_ID", default="demo-client-id"),
                "secret": env("OIDC_CLIENT_SECRET", default="demo-secret"),
                "settings": {
                    "server_url": env("OIDC_SERVER_URL", default="https://oidc.example.com"),
                },
            }
        ]
    }
}

LOGIN_REDIRECT_URL = "/api/auth/oidc/complete"

# ─── Celery (Redis broker + result backend, logical DB /0) ─────────────
# The broker DB MUST be configured noeviction (see docker-compose redis service)
# so memory pressure can never silently drop queued jobs.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ALWAYS_EAGER = False

# Celery beat: the approval-escalation sweep reassigns overdue PENDING steps to
# their escalation target (Module 5). Interval in seconds (default 5 min).
CELERY_BEAT_SCHEDULE = {
    "approvals-escalate-overdue-routes": {
        "task": "apps.approvals.tasks.escalate_overdue_routes",
        "schedule": env.int("APPROVALS_ESCALATION_INTERVAL_SECONDS", default=300),
    },
}

# ─── AI seams (the real providers land in Module 10) ──────────────────
# The JD Generator provider is resolved by import-string at call time
# (apps.jd.generator.get_provider). Unset -> NotConfiguredProvider, which makes
# the generate endpoint surface a loud 503 and NEVER fabricates a JD body.
JD_GENERATOR_PROVIDER = env(
    "JD_GENERATOR_PROVIDER",
    default="apps.jd.generator.NotConfiguredProvider",
)

# The Agent-4 (Successor Planning) enrichment provider. Unset ->
# NotConfiguredProvider, so the enrich endpoint surfaces a loud 503 and the
# DETERMINISTIC plan stays intact; the real agent lands in Module 10.
SUCCESSION_ANALYZER_PROVIDER = env(
    "SUCCESSION_ANALYZER_PROVIDER",
    default="apps.succession.agent4.NotConfiguredProvider",
)

# The Career Roadmap agent (Module 10). Unset -> NotConfiguredProvider, so the
# AI-enrich endpoint surfaces a loud 503 and the DETERMINISTIC roadmap (the
# working baseline) stays intact; the real agent lands in Module 10.
CAREER_ROADMAP_PROVIDER = env(
    "CAREER_ROADMAP_PROVIDER",
    default="apps.career.roadmap_agent.NotConfiguredProvider",
)

# The analytics insights agent (Module 10 — the Fast-AI anomaly/at-risk narrative
# on top of the deterministic rollup). Unset -> NotConfiguredProvider.
ANALYTICS_INSIGHTS_PROVIDER = env(
    "ANALYTICS_INSIGHTS_PROVIDER",
    default="apps.analytics.insights_agent.NotConfiguredProvider",
)

# ─── Integrations (Module 12 — Jira + Slack) ──────────────────────────
# JIRA_ACTUAL_PROVIDER is deliberately LEFT UNSET in base settings so production
# stays on the Module-2 NotConfigured/log-and-skip path. To activate the real
# integration, set it to "apps.integrations.jira_provider.JiraActualProvider"
# (tests set it explicitly). The HTTP/Slack client factories are injectable so
# tests substitute deterministic fakes — no real network call ever runs in tests.
JIRA_HTTP_CLIENT_FACTORY = env(
    "JIRA_HTTP_CLIENT_FACTORY", default="apps.integrations.clients.build_jira_client"
)
SLACK_CLIENT_FACTORY = env(
    "SLACK_CLIENT_FACTORY", default="apps.integrations.clients.build_slack_client"
)

# ─── AI / LLM Gateway (Module 10) ─────────────────────────────────────
# The single LLM provider, resolved by the LLMGateway (CLAUDE.md rule 6: all LLM
# calls go through the gateway). DEFAULTS TO NotConfiguredProvider, so PRODUCTION
# stays on a loud 503 (no fabricated AI output) until Hari sets a real provider +
# key — see NEEDS_HARI_llm_provider.md. Tests set this to the deterministic
# FakeLLMProvider to exercise the full agent graphs with no network call.
LLM_PROVIDER = env("LLM_PROVIDER", default="apps.ai.providers.NotConfiguredProvider")
# LangSmith tracing is opt-in: a no-op until a key is set (it is unset tonight).
LANGSMITH_API_KEY = env("LANGSMITH_API_KEY", default="")

# ─── i18n / tz ─────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ─── Static ────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ─── Logging (structured JSON to stdout, request-correlated) ───────────
# RequestContextFilter injects request_id (+ tenant_id when bound) onto every
# record; they appear in the JSON because they're named in the format string.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": "apps.core.logging.RequestContextFilter"},
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(tenant_id)s %(message)s",
        },
        "plain": {
            "format": "%(asctime)s %(levelname)s %(name)s [req=%(request_id)s tenant=%(tenant_id)s] %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "pms": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}

# ─── Sentry (optional; disabled when SENTRY_DSN is unset) ──────────────
# init_sentry no-ops without a DSN so the app boots normally. PII is scrubbed
# (send_default_pii=False + before_send drops Authorization/JWTs); events are
# tagged with tenant_id + request_id from the contextvars.
from apps.core.observability import init_sentry  # noqa: E402

init_sentry(
    dsn=env("SENTRY_DSN", default=""),
    environment=env("SENTRY_ENVIRONMENT", default="dev"),
    traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
)
