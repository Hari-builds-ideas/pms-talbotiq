"""The deploy checks in ``apps/core/checks.py``.

Each guards a setting that boots happily and quietly breaks a promise to a user, so
the tests assert the check FIRES on the development default — a check that only ever
passes is indistinguishable from no check at all.
"""
from django.test import override_settings

from apps.core import checks

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


def _ids(results):
    return {r.id for r in results}


@override_settings(EMAIL_BACKEND=CONSOLE)
def test_console_email_backend_is_an_error():
    """The most expensive default to ship: reset/verify/invite all return 200 and
    write the link to a log nobody reads."""
    assert "pms.E001" in _ids(checks.email_backend_delivers(None))


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="", DEFAULT_FROM_EMAIL="a@b.c")
def test_smtp_without_a_host_is_an_error():
    assert "pms.E002" in _ids(checks.email_backend_delivers(None))


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.example.com",
                   DEFAULT_FROM_EMAIL="Axiom <no-reply@axiom.test>")
def test_a_configured_smtp_backend_passes():
    assert checks.email_backend_delivers(None) == []


@override_settings(PUBLIC_APP_URL="http://localhost:5173")
def test_localhost_public_url_is_an_error():
    """Delivered, opened, and useless — the failure lands on the recipient."""
    assert "pms.E003" in _ids(checks.public_app_url_is_absolute(None))


@override_settings(PUBLIC_APP_URL="https://pms.example.com")
def test_a_real_public_url_passes():
    assert checks.public_app_url_is_absolute(None) == []


@override_settings(LLM_MAX_CALLS=60)
def test_dev_sized_ai_ceiling_warns():
    assert "pms.W001" in _ids(checks.ai_call_ceiling_is_production_sized(None))


@override_settings(LLM_MAX_CALLS=2000)
def test_production_sized_ai_ceiling_is_quiet():
    assert checks.ai_call_ceiling_is_production_sized(None) == []


@override_settings(LLM_MAX_CALLS=0)
def test_a_disabled_ceiling_is_deliberate_not_a_warning():
    """0 means "rely on the per-tenant AgentBudget", which is a valid choice."""
    assert checks.ai_call_ceiling_is_production_sized(None) == []
