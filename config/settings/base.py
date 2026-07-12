"""
Base settings shared by every environment.

Environment-specific modules (dev/prod/test) import * from here and override.
All secrets and environment-dependent values are read from the environment via
django-environ; see .env.example for the full documented variable list.
"""
import os
from datetime import timedelta
from pathlib import Path

import environ

# project root: .../config/settings/base.py -> parents[2]
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
# Load .env if present (no-op when absent, e.g. inside containers using env vars).
# The path is overridable via PMS_DOTENV_PATH so hermetic tests (e.g. the prod
# "fails closed without a secret" checks) can point it at a nonexistent file and
# NOT silently inherit a developer's local .env. Default behaviour is unchanged.
environ.Env.read_env(os.environ.get("PMS_DOTENV_PATH", str(BASE_DIR / ".env")))

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
    # RW_BUILD_2 — Recognition (kudos card + feed)
    "apps.recognition.apps.RecognitionConfig",
    # RW_BUILD_3 — Weekly Check-ins
    "apps.checkins.apps.CheckinsConfig",
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
    # Record per-request metrics (route-class + status) into the cross-worker
    # counter for /metrics. Best-effort, never affects the response.
    "apps.core.middleware.MetricsMiddleware",
    # Clear the read-after-write DB-routing flag at the start of each request.
    "apps.core.dbrouter.DBRoutingResetMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Apply the X_FRAME_OPTIONS=DENY header (anti-clickjacking); the setting was
    # already DENY but the header needs this middleware to emit it (security.W002).
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

# ─── Read replica (BUILD_3) — replica-ready, default-fallback ──────────────
# The `replica` alias takes reads (see apps.core.dbrouter). With NO replica DSN
# configured (today) it is a SECOND connection to the SAME primary — so the
# read/write router is active + tested now, and provisioning a real replica is
# purely setting DB_REPLICA_HOST (+ optional DB_REPLICA_* overrides), never a
# code change. In tests the replica MIRRORS the primary's test DB, so the runner
# never builds a second test database. See docs/RUNBOOK.md.
_REPLICA_HOST = env("DB_REPLICA_HOST", default="")
DATABASES["replica"] = {
    **DATABASES["default"],
    "HOST": _REPLICA_HOST or DATABASES["default"]["HOST"],
    "PORT": env("DB_REPLICA_PORT", default=DATABASES["default"]["PORT"]),
    "USER": env("DB_REPLICA_USER", default=DATABASES["default"]["USER"]),
    "PASSWORD": env("DB_REPLICA_PASSWORD", default=DATABASES["default"]["PASSWORD"]),
    # The replica is read-only in prod; in tests it mirrors the primary's test DB.
    "TEST": {"MIRROR": "default"},
}

DATABASE_ROUTERS = ["apps.core.dbrouter.PrimaryReplicaRouter"]

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
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # DEGRADE, don't error: if Redis is unreachable, cache reads return a
            # miss (→ recompute from the DB) and writes no-op, rather than 500ing
            # the request. The hot-read caches are an optimisation, never a hard
            # dependency. Ignored failures are logged (below).
            "IGNORE_EXCEPTIONS": True,
        },
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
# Log every ignored cache exception (above) so a Redis outage is visible in the
# logs/Sentry even though requests keep serving from the DB.
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

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
    # Maps DRF-unhandled Django ValidationError (e.g. a malformed UUID query param
    # filtering a UUIDField) to a 400 instead of a 500; see apps.core.exception_handler.
    "EXCEPTION_HANDLER": "apps.core.exception_handler.exception_handler",
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

# ─── Email / SMTP (password reset + notifications) ─────────────────────
# Default is the console backend (dev: mail prints to the web container log).
# PRODUCTION sets EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend plus
# the EMAIL_HOST/PORT/USER/PASSWORD/TLS of a real provider — password reset for
# local (non-SSO) accounts depends on this being configured.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="TalbotIQ PMS <no-reply@localhost>")
#: The public base URL of the SPA — used to build password-reset links in email.
PUBLIC_APP_URL = env("PUBLIC_APP_URL", default="http://localhost:8080")

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
# Normally False (real async via the worker). The FREE demo deploy sets this True so AI
# jobs run inline in the web process — Render's free tier has no free background worker
# (see DEPLOY_DEMO.md). Demo-only; production runs a real Celery worker.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)

# Celery beat: the approval-escalation sweep reassigns overdue PENDING steps to
# their escalation target (Module 5). Interval in seconds (default 5 min).
CELERY_BEAT_SCHEDULE = {
    "approvals-escalate-overdue-routes": {
        "task": "apps.approvals.tasks.escalate_overdue_routes",
        "schedule": env.int("APPROVALS_ESCALATION_INTERVAL_SECONDS", default=300),
    },
}

# ─── AI seams (Module 10 go-live: point at the real LangGraph agents) ──
# Each agent provider's ``configured`` delegates to ``llm_configured()`` (the
# Groq gateway), so with NO key these seams STILL report unconfigured → a loud
# 503 and NEVER fabricate (tests pin LLM_PROVIDER off, so they 503 as before).
# With the Groq key present (the running stack), they produce real AI output
# through the safety pipeline, locked PENDING_HUMAN_REVIEW.
REVIEW_ASSISTANT_PROVIDER = env(
    "REVIEW_ASSISTANT_PROVIDER",
    default="apps.ai.agents.review.ReviewAssistantProvider",
)
FEEDBACK_SUMMARIZER_PROVIDER = env(
    "FEEDBACK_SUMMARIZER_PROVIDER",
    default="apps.ai.agents.feedback.FeedbackSummarizerProvider",
)
JD_GENERATOR_PROVIDER = env(
    "JD_GENERATOR_PROVIDER",
    default="apps.ai.agents.jd.JDGeneratorProvider",
)
SUCCESSION_ANALYZER_PROVIDER = env(
    "SUCCESSION_ANALYZER_PROVIDER",
    default="apps.ai.agents.succession.SuccessionAnalyzerProvider",
)
CAREER_ROADMAP_PROVIDER = env(
    "CAREER_ROADMAP_PROVIDER",
    default="apps.ai.agents.career.CareerRoadmapProvider",
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
# LangSmith tracing is opt-in: a no-op until a key is set.
LANGSMITH_API_KEY = env("LANGSMITH_API_KEY", default="")

# Provider keys + base URLs. Both providers are OpenAI-compatible Chat Completions;
# the active one is chosen by LLM_PROVIDER. A key is read from env (never hardcoded);
# unset → that provider's ``configured`` is False so the agents stay on the graceful
# 503 path. The running stack points LLM_PROVIDER at ``apps.ai.openai_provider.
# OpenAIProvider`` (see docker-compose); switch back to Groq by config (set
# LLM_PROVIDER=apps.ai.groq.GroqProvider + GROQ_API_KEY + the Groq LLM_MODEL_* names).
# Tests pin NotConfigured (and override to FakeLLMProvider) — no network in CI.
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default="https://api.openai.com/v1")
GROQ_API_KEY = env("GROQ_API_KEY", default="")
# Gemini (Google) via its OpenAI-compatible endpoint — the free-tier provider for the
# demo deploy (LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider). Key pasted into the
# host secret store, never committed.
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_BASE_URL = env("GEMINI_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta/openai")
# Gemini two-model strategy (enterprise key): a strong model for the human-read agents
# (review/feedback/succession/JD/career) and a fast model for chat/default — the same
# split as the OpenAI map below. Both env-overridable so the exact model id can change
# without a code edit (e.g. if the account exposes a different name).
# NOTE: `gemini-2.5-pro` is blocked for new API projects ("no longer available to new
# users"), so the default best is the stable `gemini-pro-latest` alias (a "thinking"
# model — see LLM_MAX_TOKENS below). Override per env if your project exposes another id.
GEMINI_MODEL_BEST = env("GEMINI_MODEL_BEST", default="gemini-pro-latest")
GEMINI_MODEL_FAST = env("GEMINI_MODEL_FAST", default="gemini-2.5-flash")
# Optional single-model override for EVERY agent (advanced/legacy). Empty = use the
# best/fast split above. Only honored if it names a Gemini model.
GEMINI_MODEL = env("GEMINI_MODEL", default="")
# Per-agent Gemini model map (mirrors LLM_MODEL_MAP). Honors the same LLM_MODEL_* env
# overrides — but the provider ignores any value that isn't a Gemini model, so a stray
# OpenAI name (from a shared override) never reaches Gemini.
# v1 product scope: hide the cohort-relative T-score NUMBER from user-facing agent
# TEXT too (the chat read answer + the KPI nudge messages), matching the frontend
# `V1_HIDE_TSCORE` flag. The number stays computed/stored; only the surfaced text drops
# it in favour of the plain risk status. Set False to restore it (v2).
V1_HIDE_TSCORE = env.bool("V1_HIDE_TSCORE", default=True)
GEMINI_MODEL_MAP = {
    "review": env("LLM_MODEL_REVIEW", default=GEMINI_MODEL_BEST),
    "feedback": env("LLM_MODEL_FEEDBACK", default=GEMINI_MODEL_BEST),
    "succession": env("LLM_MODEL_SUCCESSION", default=GEMINI_MODEL_BEST),
    "jd": env("LLM_MODEL_JD", default=GEMINI_MODEL_BEST),
    "career": env("LLM_MODEL_CAREER", default=GEMINI_MODEL_BEST),
    "chat": env("LLM_MODEL_CHAT", default=GEMINI_MODEL_FAST),
    "default": env("LLM_MODEL_DEFAULT", default=GEMINI_MODEL_FAST),
}
# Generic key fallback used by any provider when its specific key is unset.
LLM_API_KEY = env("LLM_API_KEY", default=OPENAI_API_KEY or GROQ_API_KEY or GEMINI_API_KEY)
LLM_BASE_URL = env("LLM_BASE_URL", default="https://api.groq.com/openai/v1")  # Groq only
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=30.0)
# 4096 gives headroom for Gemini "thinking" models (2.5/3.x pro + -latest aliases),
# which spend output tokens on reasoning before the JSON — 900 truncated them.
LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", default=4096)
# Run-wide safety ceiling (cache-counted across web + celery, 24h window): refuse
# further real LLM calls once reached. This is a DEPLOYMENT-WIDE runaway-loop backstop,
# NOT the per-tenant budget (that's DEFAULT_AGENT_BUDGETS / AgentBudget — the real cost
# control). Default 500 is sized for dev/QA: enough headroom that exercising every agent
# across the demo tenants won't trip it, low enough that a runaway loop is caught at
# roughly $5-10 worst case on OpenAI. PRODUCTION must size this to tenant count
# (≈ tenants × per-tenant daily cap × headroom) OR set 0 to disable it and rely on the
# per-tenant budgets + a provider-side spend limit (audit Finding B; see AI_GOLIVE.md).
LLM_MAX_CALLS = env.int("LLM_MAX_CALLS", default=500)

# Two-model strategy (OpenAI): a strong model for the human-read agents (review/
# feedback/succession/JD/career), a fast/cheap one for chat + default. Per-agent →
# trivially re-tunable here or per env var. (Groq switch-back: set these to
# llama-3.3-70b-versatile / llama-3.1-8b-instant.)
LLM_MODEL_MAP = {
    "review": env("LLM_MODEL_REVIEW", default="gpt-4o"),
    "feedback": env("LLM_MODEL_FEEDBACK", default="gpt-4o"),
    "succession": env("LLM_MODEL_SUCCESSION", default="gpt-4o"),
    "jd": env("LLM_MODEL_JD", default="gpt-4o"),
    "career": env("LLM_MODEL_CAREER", default="gpt-4o"),
    "chat": env("LLM_MODEL_CHAT", default="gpt-4o-mini"),
    "default": env("LLM_MODEL_DEFAULT", default="gpt-4o-mini"),
}

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

# ─── Metrics (/metrics) ────────────────────────────────────────────────
# Bearer token for the Prometheus /metrics endpoint. Unset → the endpoint is
# DISABLED (404), so metrics are never exposed unauthenticated. Set in prod to a
# long random value the scraper presents.
METRICS_TOKEN = env("METRICS_TOKEN", default="")

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
