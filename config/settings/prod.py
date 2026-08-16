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

# ── HTTPS / transport security ───────────────────────────────────────────────
#
# ONE variable decides the transport posture: DOMAIN.
#
# Let's Encrypt cannot issue a certificate for a bare IP address, so a deployment
# that has no DNS name yet is necessarily HTTP-only. Every TLS-dependent setting
# below therefore derives from whether DOMAIN is set, and each is still individually
# overridable for the odd topology (TLS terminated at a load balancer, say).
#
# The alternative — leave these on and deploy on an IP — is worse than it looks.
# SECURE_SSL_REDIRECT=True on plain HTTP is an infinite redirect loop, and Secure
# cookies are simply never sent, so the admin and the whole allauth SSO session
# stop working. Not "less secure": not working. The failure would be blamed on the
# app rather than on the missing DNS record.
#
# Turning them off is a real reduction in security, so it is not silent: the
# tls_is_terminated check (apps/core/checks.py) warns at every `check --deploy`
# while DOMAIN is unset. See docs/BUILD/ENABLE_TLS.md for the switch-on steps.
PUBLIC_DOMAIN = env.str("DOMAIN", default="").strip()
_HAS_TLS = bool(PUBLIC_DOMAIN)


def _tls_flag(name, *, default):
    """Read a TLS override, treating an unset OR EMPTY value as 'not overridden'.

    Compose passes ``DJANGO_SECURE_SSL_REDIRECT: ${DJANGO_SECURE_SSL_REDIRECT:-}``
    so the deployer *can* override it, which means the variable arrives as an empty
    string when they have not. ``env.bool`` raises on ``""``; the whole stack would
    then fail to boot because someone declined to override a default.
    """
    raw = env.str(name, default="").strip().lower()
    if raw == "":
        return default
    return raw in {"1", "true", "yes", "on"}


SECURE_SSL_REDIRECT = _tls_flag("DJANGO_SECURE_SSL_REDIRECT", default=_HAS_TLS)
# Kept unconditionally. Caddy sends X-Forwarded-Proto in both modes ("http" on a
# bare IP), so Django reads the real scheme either way — and the header must
# already be trusted at the instant TLS is switched on.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = _tls_flag("DJANGO_SESSION_COOKIE_SECURE", default=_HAS_TLS)
# Pin the session-cookie hardening explicitly (Django's defaults happen to match,
# but the SSO/allauth session cookie must not depend on defaults staying put).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = _tls_flag("DJANGO_CSRF_COOKIE_SECURE", default=_HAS_TLS)
# HSTS tells a browser to refuse plain HTTP to this host for a year. Sending it
# before TLS works would lock users out of their own deployment, and RFC 6797
# forbids sending it over a non-secure transport at all — so it is 0 until DOMAIN
# exists, then the full year.
_hsts_override = env.str("DJANGO_HSTS_SECONDS", default="").strip()
SECURE_HSTS_SECONDS = int(_hsts_override) if _hsts_override else (31536000 if _HAS_TLS else 0)
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
