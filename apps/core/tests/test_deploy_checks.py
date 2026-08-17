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


# ── the transport switch (C14) ────────────────────────────────────────────────
# One variable, DOMAIN, decides whether the stack runs HTTP-only on a bare IP or
# with TLS end to end. The check exists so the HTTP-only half stays a decision
# somebody made rather than a state everybody forgot.


@override_settings(PUBLIC_DOMAIN="")
def test_http_only_deployment_warns_every_deploy():
    """Planned, but it must not go quiet. On a bare IP every JWT and every
    password crosses the network readable and alterable; the risk is that this
    becomes permanent because nothing ever mentions it again."""
    results = checks.tls_is_terminated(None)
    assert "pms.W003" in _ids(results)
    assert "ENABLE_TLS" in results[0].hint


@override_settings(PUBLIC_DOMAIN="pms.example.com", SECURE_SSL_REDIRECT=True,
                   PUBLIC_APP_URL="https://pms.example.com")
def test_a_domain_with_tls_on_is_quiet():
    assert checks.tls_is_terminated(None) == []


@override_settings(PUBLIC_DOMAIN="pms.example.com", SECURE_SSL_REDIRECT=False,
                   PUBLIC_APP_URL="https://pms.example.com")
def test_a_domain_with_the_redirect_switched_off_warns():
    """The silent downgrade: a certificate exists, everything looks healthy, and
    anything arriving over http:// simply stays there for the whole session."""
    assert "pms.W003" in _ids(checks.tls_is_terminated(None))


@override_settings(PUBLIC_DOMAIN="pms.example.com", SECURE_SSL_REDIRECT=True,
                   PUBLIC_APP_URL="http://pms.example.com")
def test_a_domain_with_http_reset_links_warns():
    """Reset and invitation links carry a single-use token. Built over http://,
    the token crosses the network in the clear before the redirect upgrades it —
    and the redirect happens after the request that already leaked it."""
    results = checks.tls_is_terminated(None)
    assert "pms.W003" in _ids(results)
    assert "https://pms.example.com" in results[0].hint


# ── the gate has to stay readable ─────────────────────────────────────────────


def test_the_deploy_check_is_not_buried_in_known_noise(settings):
    """A gate nobody reads is not a gate.

    Adding drf-spectacular (F6) put 209 warnings into `manage.py check --deploy`
    — 193 "unable to guess serializer" plus 16 operationId collisions. They are
    real and documented, and none of them blocks a deploy. What they did block is
    the deployer noticing `pms.W003`, the one that says this deployment is
    serving plain HTTP, which had been pushed to somewhere around line 180.

    So they are silenced, and this test pins the silencing. If a future change
    starts emitting a NEW class of warning by the hundred, that one is not on the
    list and the gate goes noisy again — which is when somebody should look at
    it, rather than a year later.
    """
    assert "drf_spectacular.W001" in settings.SILENCED_SYSTEM_CHECKS
    assert "drf_spectacular.W002" in settings.SILENCED_SYSTEM_CHECKS


def test_our_own_checks_are_never_silenced(settings):
    """The pms.* checks exist precisely because they catch what boots happily and
    breaks a promise. Silencing one would be indistinguishable from deleting it."""
    assert not any(
        code.startswith("pms.") for code in settings.SILENCED_SYSTEM_CHECKS
    ), "a pms.* deploy check has been silenced — delete it or fix it, do not mute it"
