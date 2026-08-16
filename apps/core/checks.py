"""Deploy-time checks — the misconfigurations that boot happily and lose data.

These run under ``manage.py check --deploy`` only (``deploy=True``), so they gate a
release without firing during ordinary tests or local development.

Django's own ``--deploy`` checks cover the transport-security settings well. What it
cannot know is which of *this* app's settings are load-bearing for a real customer.
The ones below all share a shape: the process starts, every request succeeds, and a
user-visible promise is quietly broken.
"""
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

#: Backends that accept a message and never deliver it to a human.
_NON_DELIVERING = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
)


@register(Tags.security, deploy=True)
def email_backend_delivers(app_configs, **kwargs):
    """A production EMAIL_BACKEND that does not deliver is a locked front door.

    Password reset, email verification and invitations all go through ``send_mail``.
    On the console backend every one of them returns 200 and writes the link to the
    container log: nobody can join the product and nobody can recover an account, and
    nothing anywhere reports an error. This is the single most expensive setting to
    leave at its development default, so it is an Error rather than a Warning.
    """
    if settings.EMAIL_BACKEND in _NON_DELIVERING:
        return [Error(
            f"EMAIL_BACKEND is {settings.EMAIL_BACKEND!r}, which never delivers mail.",
            hint=("Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend plus "
                  "EMAIL_HOST/PORT/USER/PASSWORD. Without it, password reset, email "
                  "verification and invitations silently go nowhere."),
            id="pms.E001",
        )]
    missing = [n for n in ("EMAIL_HOST", "DEFAULT_FROM_EMAIL")
               if not getattr(settings, n, "")]
    if missing:
        return [Error(
            f"SMTP is selected but {', '.join(missing)} is unset.",
            hint="Mail will fail at send time, after the user has been told it was sent.",
            id="pms.E002",
        )]
    return []


@register(Tags.security, deploy=True)
def public_app_url_is_absolute(app_configs, **kwargs):
    """Reset and invite links are built from PUBLIC_APP_URL.

    Left at its default, the email goes out with a localhost link — delivered, opened,
    and useless. The failure lands on the recipient, not on us, so nothing alerts.
    """
    url = getattr(settings, "PUBLIC_APP_URL", "") or ""
    if not url.startswith(("http://", "https://")) or "localhost" in url or "127.0.0.1" in url:
        return [Error(
            f"PUBLIC_APP_URL is {url!r}, which will not resolve for a recipient.",
            hint="Set it to the public SPA origin, e.g. https://pms.your-company.com.",
            id="pms.E003",
        )]
    return []


@register(Tags.security, deploy=True)
def ai_call_ceiling_is_production_sized(app_configs, **kwargs):
    """The dev default (60/window) reads as a broken assistant in production.

    It is a runaway-loop backstop, not the cost control (that is the per-tenant
    AgentBudget). Shipping the dev value means the assistant starts refusing with
    "budget exhausted" partway through an ordinary day.
    """
    ceiling = int(getattr(settings, "LLM_MAX_CALLS", 0) or 0)
    if 0 < ceiling < 500:
        return [Warning(
            f"LLM_MAX_CALLS={ceiling} is the development-sized ceiling.",
            hint="Size it to tenants × daily cap × headroom, or 0 to rely on the "
                 "per-tenant AgentBudget plus a provider-side spend cap.",
            id="pms.W001",
        )]
    return []


@register(Tags.security, deploy=True)
def proxy_depth_is_declared(app_configs, **kwargs):
    """A wrong NUM_PROXIES silently disables the login brute-force throttle (C11).

    Behind a TLS edge every request arrives with REMOTE_ADDR set to the proxy, so
    DRF identifies anonymous clients from X-Forwarded-For instead. A proxy APPENDS
    to that header rather than replacing it, so with NUM_PROXIES unset DRF keys on
    the WHOLE header — and a client that sends its own X-Forwarded-For gets a
    different throttle bucket on every request. The per-IP limit protecting the
    login surface stops existing, and nothing reports an error: logins still work,
    the counter simply never fills.

    prod.py defaults it to 1, which is correct for Caddy alone. That default is
    the trap: put a CDN in front (Cloudflare, CloudFront) and the correct value
    becomes 2, but nothing changes, nothing errors, and the throttle silently
    becomes forgeable again. So this warns when the value was DEFAULTED rather
    than declared — the deployer is asked to confirm the topology once, out loud.
    """
    import os

    proxy_header = getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
    if not proxy_header:
        return []

    num_proxies = (getattr(settings, "REST_FRAMEWORK", {}) or {}).get("NUM_PROXIES")

    if num_proxies is None:
        return [Error(
            "A reverse proxy fronts this app (SECURE_PROXY_SSL_HEADER is set) but "
            "REST_FRAMEWORK['NUM_PROXIES'] is not configured.",
            hint=("DRF will key the anonymous throttle on the whole X-Forwarded-For "
                  "header, which a client can vary at will — the brute-force limit "
                  "on /api/auth/login stops working and nothing reports an error. "
                  "Set DJANGO_NUM_PROXIES."),
            id="pms.E004",
        )]

    if isinstance(num_proxies, int) and num_proxies < 1:
        return [Error(
            f"REST_FRAMEWORK['NUM_PROXIES'] is {num_proxies}, but a proxy fronts "
            "this app.",
            hint=("0 means 'trust REMOTE_ADDR', which behind a proxy is the proxy "
                  "itself — every anonymous client then shares one throttle bucket. "
                  "Set DJANGO_NUM_PROXIES to the real proxy count."),
            id="pms.E004",
        )]

    if "DJANGO_NUM_PROXIES" not in os.environ:
        return [Warning(
            f"DJANGO_NUM_PROXIES is not set, so the proxy depth defaulted to "
            f"{num_proxies}.",
            hint=("That default is right for Caddy alone and WRONG the moment a CDN "
                  "sits in front (Cloudflare/CloudFront → 2). Getting it wrong does "
                  "not error: too low throttles every anonymous user as one, too "
                  "high trusts a hop the client can forge, and the login "
                  "brute-force limit quietly stops protecting anything. Set "
                  "DJANGO_NUM_PROXIES explicitly to confirm the topology."),
            id="pms.W002",
        )]
    return []
