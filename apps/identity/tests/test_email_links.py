"""
Every link in every email is built from ``PUBLIC_APP_URL`` (E3).

This is the setting that breaks silently. Wrong, mail still sends, the endpoint
still returns 200, the log still says "sent" — and the recipient gets a link to
somebody's laptop. Nothing on our side ever reports an error, because from the
application's point of view nothing went wrong. The only signal is a user saying
"the link doesn't work", days later, about an email they can no longer find.

So these tests read the RENDERED message and check the hostname, for all four
flows, rather than trusting that each call site remembered to use the setting.

They also check both bodies. The messages are multipart, and it is entirely
possible to fix a link in the plaintext part and leave the HTML one pointing at
localhost — the HTML part is the one almost everyone actually clicks.
"""
import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.identity.models import Invitation
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

PUBLIC_URL = "https://pms.acme-corp.test"


@pytest.fixture(autouse=True)
def public_url(settings):
    settings.PUBLIC_APP_URL = PUBLIC_URL
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()
    return PUBLIC_URL


@pytest.fixture
def tenant(db):
    return TenantFactory(slug="acme", name="Acme")


@pytest.fixture
def admin(tenant):
    return UserFactory(tenant=tenant, email="admin@acme.test", role="ADMIN")


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _bodies(message):
    """The plaintext body and every alternative, so neither half can be missed."""
    return [message.body] + [content for content, _ in message.alternatives]


def _links(message):
    return {
        url
        for body in _bodies(message)
        for url in re.findall(r"https?://[^\s\"'<>)]+", body)
    }


def _assert_links_are_public(message):
    links = _links(message)
    assert links, "the message contains no link at all"
    for link in links:
        assert link.startswith(PUBLIC_URL), (
            f"{link!r} does not start with PUBLIC_APP_URL — the recipient cannot "
            f"reach it, and nothing on our side reports an error"
        )
    # Present in BOTH parts, not just the plaintext one.
    for body in _bodies(message):
        assert PUBLIC_URL in body


# ── the four flows ────────────────────────────────────────────────────────────


def test_password_reset_link_uses_the_public_url(tenant, admin):
    resp = APIClient().post(
        "/api/auth/password-reset",
        {"email": admin.email, "tenant_slug": tenant.slug},
        format="json",
    )
    assert resp.status_code == 200
    assert len(mail.outbox) == 1
    _assert_links_are_public(mail.outbox[0])
    assert "/reset-password" in mail.outbox[0].body


def test_invitation_link_uses_the_public_url(tenant, admin):
    resp = _client_for(admin).post(
        "/api/admin/invitations",
        {"email": "newhire@acme.test", "role": "EMPLOYEE"},
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    assert len(mail.outbox) == 1
    _assert_links_are_public(mail.outbox[0])
    with tenant_context(tenant):
        assert Invitation.objects.filter(email="newhire@acme.test").exists()


def test_email_change_link_uses_the_public_url(tenant, admin):
    admin.set_password("correct-horse-battery")
    admin.save(update_fields=["password"])
    resp = _client_for(admin).post(
        "/api/auth/email-change",
        {"new_email": "admin.new@acme.test", "current_password": "correct-horse-battery"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 1
    _assert_links_are_public(mail.outbox[0])
    # Sent to the NEW address: confirming an address you cannot read proves
    # nothing, and it is the whole point of the step.
    assert mail.outbox[0].to == ["admin.new@acme.test"]


def test_welcome_link_uses_the_public_url(settings, db):
    settings.SIGNUP_MODE = "open"
    resp = APIClient().post(
        "/api/auth/signup",
        {
            "org_name": "Newco",
            "display_name": "Dana Founder",
            "email": "founder@newco.test",
            "password": "correct-horse-battery-staple",
        },
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    assert len(mail.outbox) == 1
    _assert_links_are_public(mail.outbox[0])


# ── the properties that hold for every message ────────────────────────────────


@pytest.fixture
def any_message(tenant, admin):
    APIClient().post(
        "/api/auth/password-reset",
        {"email": admin.email, "tenant_slug": tenant.slug},
        format="json",
    )
    return mail.outbox[0]


def test_every_message_is_multipart(any_message):
    """Plaintext alone arrives looking like a phishing attempt; HTML alone leaves
    a plaintext reader with nothing. Both, always."""
    assert any_message.body.strip()
    assert len(any_message.alternatives) == 1
    content, mimetype = any_message.alternatives[0]
    assert mimetype == "text/html"
    assert "<html" in content.lower()


def test_every_message_carries_the_brand(settings, tenant, admin):
    """APP_NAME is a real setting, not decoration — a rebranded deployment must
    not send mail signed with a different product's name."""
    settings.APP_NAME = "Talbotiq PMS"
    mail.outbox.clear()
    APIClient().post(
        "/api/auth/password-reset",
        {"email": admin.email, "tenant_slug": tenant.slug},
        format="json",
    )
    message = mail.outbox[0]
    assert "Talbotiq PMS" in message.subject
    for body in _bodies(message):
        assert "Talbotiq PMS" in body


def test_the_raw_link_is_printed_next_to_the_button(any_message):
    """Some corporate gateways rewrite or strip an href, and a plaintext-preferring
    client shows no button at all. Somebody locked out of their account has to be
    able to copy the URL."""
    html = any_message.alternatives[0][0]
    assert html.count(PUBLIC_URL) >= 2, "the URL appears only inside the button href"


def test_a_reply_goes_somewhere_a_human_reads(settings, tenant, admin):
    """Replies to a no-reply address vanish — which is how a support request gets
    lost at the exact moment somebody cannot get into their account."""
    settings.EMAIL_REPLY_TO = "support@acme-corp.test"
    mail.outbox.clear()
    APIClient().post(
        "/api/auth/password-reset",
        {"email": admin.email, "tenant_slug": tenant.slug},
        format="json",
    )
    assert mail.outbox[0].reply_to == ["support@acme-corp.test"]


# ── failure never reaches the caller ──────────────────────────────────────────


def test_a_broken_smtp_server_does_not_break_the_endpoint(tenant, admin, settings):
    """A 500 here would be worse than a lost email: this endpoint returns the same
    response whether or not the account exists, and an exception on the send path
    would separate the two."""
    from unittest.mock import patch

    with patch(
        "django.core.mail.EmailMultiAlternatives.send",
        side_effect=OSError("connection refused"),
    ):
        resp = APIClient().post(
            "/api/auth/password-reset",
            {"email": admin.email, "tenant_slug": tenant.slug},
            format="json",
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_an_unknown_account_and_a_failed_send_are_indistinguishable(tenant, admin):
    known = APIClient().post(
        "/api/auth/password-reset",
        {"email": admin.email, "tenant_slug": tenant.slug},
        format="json",
    )
    unknown = APIClient().post(
        "/api/auth/password-reset",
        {"email": "nobody@acme.test", "tenant_slug": tenant.slug},
        format="json",
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
