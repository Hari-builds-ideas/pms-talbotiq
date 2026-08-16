"""
The one way this product sends email.

Before this existed, four flows (password reset, invitation, email change,
signup welcome) each built a plaintext body inline and wrapped ``send_mail`` in
its own try/except. That is four copies of the same decisions, and they had
already drifted: the same failure was logged four different ways, and adding a
brand or a reply-to meant editing four call sites and remembering all of them.

Everything here exists because of how these messages actually get read.

**HTML and plaintext, always both.** A multipart message lets each client pick;
sending HTML alone means a plaintext reader gets nothing, and sending plaintext
alone means a reset link arrives looking like a phishing attempt.

**Sending never raises.** Every caller is on a request path where the mail is a
side effect: a password-reset endpoint that 500s because SMTP is down tells the
user their account does not exist, and an invitation that 500s after the
Invitation row was written leaves an invite nobody can resend. Failures are
logged and reported as ``False`` so the caller can tell the user honestly.

**The link is always passed in whole.** Callers build it from
``PUBLIC_APP_URL``; this module never assembles a URL, so there is one place
that can get the hostname wrong instead of five.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context
from django.template.loader import get_template, render_to_string

logger = logging.getLogger("pms.mail")

#: Backends that accept a message and never deliver it to a human. Used to log
#: honestly rather than to refuse: on the console backend a developer still wants
#: the mail, they just should not believe it was delivered.
_NON_DELIVERING = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
)


def is_delivering() -> bool:
    """False when the configured backend cannot reach a human."""
    return settings.EMAIL_BACKEND not in _NON_DELIVERING


def _render_plaintext(template: str, ctx: dict) -> str:
    """Render the ``.txt`` half with autoescaping OFF.

    Django autoescapes for HTML by default, which in a plaintext body is not
    merely pointless but wrong: a reset URL carries query parameters, so ``&``
    becomes ``&amp;`` and the link a recipient copies out of the text part arrives
    with a parameter literally named ``amp;uid``. The reset then fails with an
    invalid-token error that points at the token, not at the escaping.

    Handled here rather than by an ``{% autoescape off %}`` wrapper in each
    template, because the wrapper is a thing every future template has to
    remember and this is not.
    """
    return get_template(f"emails/{template}.txt").template.render(
        Context(ctx, autoescape=False)
    )


def send_templated_email(template: str, *, to, subject: str, context: dict) -> bool:
    """Render ``emails/<template>.{txt,html}`` and send it. Never raises.

    Returns True when the backend accepted the message — which is not the same as
    delivered, and the caller must not tell a user otherwise.
    """
    recipients = [to] if isinstance(to, str) else list(to)
    ctx = {
        "app_name": settings.APP_NAME,
        "support_email": settings.SUPPORT_EMAIL,
        **context,
    }
    try:
        text_body = _render_plaintext(template, ctx)
        html_body = render_to_string(f"emails/{template}.html", ctx)
    except Exception:  # noqa: BLE001 — a template error must not 500 the request
        logger.exception("mail: could not render template %s", template)
        return False

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=None,  # DEFAULT_FROM_EMAIL
        to=recipients,
        reply_to=[settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None,
    )
    message.attach_alternative(html_body, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("mail: %s to %s failed to send", template, recipients)
        return False

    if not is_delivering():
        logger.info(
            "mail: %s written to the %s backend — NOT delivered to %s",
            template, settings.EMAIL_BACKEND, recipients,
        )
    return True
