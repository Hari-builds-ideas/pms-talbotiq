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
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.tenancy.apps.TenancyConfig",
    "apps.identity.apps.IdentityConfig",
    "apps.rbac.apps.RbacConfig",
    "apps.audit.apps.AuditConfig",
    "apps.billing.apps.BillingConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ────────────────────────────────────────────────────────
# TenantMiddleware is last so it runs closest to the view: it resolves the
# current tenant from the cryptographically verified JWT *after* auth, sets the
# contextvar before the view executes, and resets it immediately afterwards.
MIDDLEWARE = [
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
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
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
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}
# Sessions live in Redis (per the Module 1 login workflow: "write session to Redis").
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

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
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="100/min"),
        "user": env("THROTTLE_USER", default="1000/min"),
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

# ─── Celery (Redis broker + result backend) ────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ALWAYS_EAGER = False

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

# ─── Logging (structured JSON to stdout) ───────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "pms": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
