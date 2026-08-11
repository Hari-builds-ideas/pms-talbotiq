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
