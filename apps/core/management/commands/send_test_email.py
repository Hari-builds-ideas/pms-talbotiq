"""
``manage.py send_test_email <address>`` — prove mail works, from the deployment.

SMTP is the setting most likely to be wrong in a way nothing notices. Every flow
that depends on it (password reset, invitation, email-change confirmation) is
deliberately best-effort and never raises, precisely so an outage cannot 500 a
request or leak whether an account exists — which means a misconfiguration
produces silence rather than an error. The first symptom is a customer who
cannot get into their account.

So there is one command that goes the whole way and tells you what happened.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.mail import _NON_DELIVERING, send_templated_email


class Command(BaseCommand):
    help = "Send a test email to verify the SMTP configuration of this deployment."

    def add_arguments(self, parser):
        parser.add_argument("address", help="Where to send the test message.")
        parser.add_argument(
            "--allow-console",
            action="store_true",
            help=(
                "Send even when the backend cannot deliver to a human. Without "
                "this the command refuses, because a console-backend 'success' is "
                "the exact false confidence it exists to prevent."
            ),
        )

    def handle(self, *args, **options):
        address = options["address"]
        backend = settings.EMAIL_BACKEND

        self.stdout.write("Configuration:")
        for label, value in (
            ("EMAIL_BACKEND", backend),
            ("EMAIL_HOST", settings.EMAIL_HOST or "(unset)"),
            ("EMAIL_PORT", settings.EMAIL_PORT),
            ("EMAIL_HOST_USER", settings.EMAIL_HOST_USER or "(unset)"),
            # Never the value. Whether it is set is the useful fact, and it is the
            # whole fact — a password printed into a deploy log is a leaked
            # password, and this command is run from exactly such a shell.
            ("EMAIL_HOST_PASSWORD", "set" if settings.EMAIL_HOST_PASSWORD else "(unset)"),
            ("EMAIL_USE_TLS", settings.EMAIL_USE_TLS),
            ("EMAIL_USE_SSL", settings.EMAIL_USE_SSL),
            ("EMAIL_TIMEOUT", settings.EMAIL_TIMEOUT),
            ("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL),
            ("EMAIL_REPLY_TO", settings.EMAIL_REPLY_TO or "(unset)"),
            ("PUBLIC_APP_URL", settings.PUBLIC_APP_URL),
        ):
            self.stdout.write(f"  {label:22} {value}")
        self.stdout.write("")

        if backend in _NON_DELIVERING and not options["allow_console"]:
            raise CommandError(
                f"EMAIL_BACKEND is {backend!r}, which never delivers to a human. "
                "This command would print a message to the log and report success, "
                "which is the false confidence it exists to prevent.\n"
                "Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend plus "
                "EMAIL_HOST/PORT/USER/PASSWORD, or pass --allow-console to send "
                "anyway and inspect the rendered message."
            )

        if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
            raise CommandError(
                "EMAIL_USE_TLS and EMAIL_USE_SSL are both on. They are different "
                "things — STARTTLS on 587 and implicit TLS on 465 — and Django "
                "refuses to guess. Turn off whichever does not match your provider."
            )

        sent = send_templated_email(
            "test",
            to=address,
            subject=f"{settings.APP_NAME} SMTP test",
            context={
                "sent_at": timezone.now().isoformat(timespec="seconds"),
                "backend": backend,
                "from_email": settings.DEFAULT_FROM_EMAIL,
                "public_app_url": settings.PUBLIC_APP_URL,
            },
        )

        if not sent:
            raise CommandError(
                f"The send FAILED. The exception is in the application log under "
                f"the 'pms.mail' logger — it names the SMTP error, which is almost "
                f"always authentication, a blocked port, or a From address the "
                f"provider will not accept."
            )

        self.stdout.write(self.style.SUCCESS(f"✓ accepted for delivery to {address}"))
        self.stdout.write(
            "\nAccepted is not delivered. Check the inbox, and check spam — a From "
            "address on a domain with no SPF or DKIM record is usually accepted by "
            "the relay and then filtered on arrival, which looks identical from here."
        )
        if settings.PUBLIC_APP_URL.startswith("http://localhost"):
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠ PUBLIC_APP_URL is still localhost. Mail will send and every "
                    "link inside it will be dead for the recipient."
                )
            )
