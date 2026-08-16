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

# REQUIRED in production, no default (C4).
#
# This builds the links in password-reset and invitation emails. The base default
# is http://localhost:8080, which does not fail — it sends. Every recovery email
# would go out with a link to the recipient's own machine, they would all be dead,
# and the only signal would be users saying "the link doesn't work". A missing
# variable that breaks at startup is strictly better than one that breaks silently
# in someone else's inbox.
PUBLIC_APP_URL = env("PUBLIC_APP_URL")

# HTTPS / transport security
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
# Pin the session-cookie hardening explicitly (Django's defaults happen to match,
# but the SSO/allauth session cookie must not depend on defaults staying put).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# How many reverse proxies sit in front of Django — REQUIRED once one does.
#
# Behind the TLS edge every request arrives with REMOTE_ADDR set to the proxy, so
# DRF identifies anonymous clients from X-Forwarded-For instead. With NUM_PROXIES
# unset it keys on the WHOLE header, and a proxy APPENDS to that header rather
# than replacing it — so a client that sends its own X-Forwarded-For gets a
# different throttle key on every request and the per-IP limit protecting the
# login surface stops existing. Demonstrated: rotating a forged value yields the
# keys '1.1.1.1,203.0.113.9', '2.2.2.2,203.0.113.9', … one bucket each.
#
# Set to the number of proxies and DRF takes the address that many hops from the
# right — the one the outermost proxy actually observed, which a client cannot
# forge. 1 = Caddy alone. Put a CDN in front (Cloudflare, CloudFront) and this
# becomes 2; get it wrong and you either trust a forged hop (too high) or throttle
# every user as one (too low).
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": env.int("DJANGO_NUM_PROXIES", default=1)}  # noqa: F405
