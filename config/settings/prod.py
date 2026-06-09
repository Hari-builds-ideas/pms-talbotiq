"""Production settings: secure defaults, secrets strictly from the environment."""
from .base import *  # noqa: F401,F403
from .base import SIMPLE_JWT, env

DEBUG = False

# Secret key is REQUIRED in production — no fallback. `env("…")` with no default
# raises ImproperlyConfigured at startup if DJANGO_SECRET_KEY is unset, so a
# prod process can never silently boot on the public dev default and sign JWTs
# with a known key. (Mirrors the ALLOWED_HOSTS fail-closed pattern below.)
SECRET_KEY = env("DJANGO_SECRET_KEY")
# SIMPLE_JWT was assembled in base.py against base's SECRET_KEY; re-point the
# signing key at the production secret.
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY

# Must be provided explicitly in production — no wildcard fallback.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# HTTPS / transport security
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
