"""
``apps.core.mail`` — the single sender.

The escaping test below is the one that matters. Django autoescapes for HTML by
default, which in a PLAINTEXT body is not merely pointless but actively breaks
the thing the email exists to deliver: a reset URL carries query parameters, so
``&`` renders as ``&amp;`` and the link a recipient copies out of the text part
arrives with a parameter literally named ``amp;uid``. The reset then fails with
an invalid-token error pointing at the token rather than at the escaping.

It was caught by the existing password-reset tests when these templates were
introduced. It is pinned here so the next template does not reintroduce it.
"""
import pytest
from django.core import mail

from apps.core.mail import is_delivering, send_templated_email

pytestmark = pytest.mark.django_db

URL_WITH_PARAMS = "https://pms.acme.test/reset-password?tenant=acme&uid=abc&token=xyz"


@pytest.fixture(autouse=True)
def locmem(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.PUBLIC_APP_URL = "https://pms.acme.test"
    mail.outbox.clear()


def _send():
    return send_templated_email(
        "password_reset",
        to="someone@acme.test",
        subject="Reset your password",
        context={"tenant_name": "Acme", "url": URL_WITH_PARAMS},
    )


def test_the_plaintext_link_is_not_html_escaped():
    assert _send() is True
    body = mail.outbox[0].body
    assert URL_WITH_PARAMS in body
    assert "&amp;" not in body, (
        "the plaintext link was HTML-escaped; a recipient who copies it gets a "
        "parameter named 'amp;uid' and the link fails"
    )


def test_the_html_link_IS_escaped_because_that_is_correct_there():
    """The same ampersand must be escaped in the HTML part — an unescaped ``&``
    in an href is invalid markup and some clients mangle it."""
    _send()
    html = mail.outbox[0].alternatives[0][0]
    assert "&amp;uid=" in html
    # And it still renders as the real URL to the reader.
    assert "uid=abc" in html


def test_both_parts_are_always_present():
    _send()
    message = mail.outbox[0]
    assert message.body.strip()
    assert len(message.alternatives) == 1
    assert message.alternatives[0][1] == "text/html"


def test_a_send_failure_returns_false_rather_than_raising():
    """Every caller is on a request path where the mail is a side effect. A raise
    here would 500 a password-reset request — which also discloses that the
    account exists, since the no-account path cannot fail the same way."""
    from unittest.mock import patch

    with patch(
        "django.core.mail.EmailMultiAlternatives.send",
        side_effect=OSError("connection refused"),
    ):
        assert _send() is False


def test_a_missing_template_returns_false_rather_than_raising():
    assert send_templated_email(
        "no_such_template", to="a@b.test", subject="x", context={}
    ) is False


def test_is_delivering_reports_the_backend_honestly(settings):
    assert is_delivering() is False  # locmem, from the fixture
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    assert is_delivering() is True


def test_the_reply_to_is_omitted_when_unset(settings):
    settings.EMAIL_REPLY_TO = ""
    _send()
    assert mail.outbox[0].reply_to == []
