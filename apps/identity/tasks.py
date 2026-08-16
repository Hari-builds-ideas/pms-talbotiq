"""
Retention sweep for authentication events (D3).

``LoginEvent`` and ``DeviceSession`` hold an IP address and a user agent for
every sign-in and every device: across a tenant that is a movement log of the
whole workforce, and its only real use is answering "was this account reached by
somebody else, recently". After a few months it is a liability with no remaining
purpose, so it is deleted on a clock rather than kept by default.

``AUTH_EVENT_RETENTION_DAYS`` (90) is chosen to be longer than any plausible
incident investigation and much shorter than forever.

Registered on celery-beat via ``CELERY_BEAT_SCHEDULE["identity-purge-auth-events"]``
in ``config/settings/base.py``; the dotted name below must match that entry.

Like the approvals sweep, this runs OFF-REQUEST, so it uses the cross-tenant
escape hatch (``all_tenants()``) deliberately and once, at the top — the ordinary
scoped manager would fail closed with no tenant bound and the sweep would silently
delete nothing at all.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("pms.identity")


def purge_expired_auth_events(*, now=None, retention_days=None):
    """Delete auth events and sessions older than the retention window.

    Directly callable (the tests call it synchronously); the Celery task below is
    a thin wrapper.

    Two things are deliberate:

    **Sessions are cut on their own age, not on whether they are revoked.** A
    session revoked yesterday is evidence about a possible compromise today, and
    purging it immediately would remove exactly the row an investigation wants.

    **A revoked session is not kept past the window either.** Once it is older
    than the retention period the token that referenced it has long expired, so
    keeping the row protects nothing — see ``session_is_revoked``, which reads a
    missing row as "not revoked" precisely because such a token cannot exist.
    """
    from .models import DeviceSession, LoginEvent

    days = settings.AUTH_EVENT_RETENTION_DAYS if retention_days is None else retention_days
    if days <= 0:
        # 0 or negative means "keep everything" — an explicit opt-out for a
        # deployment under a legal hold. Silently deleting nothing is the right
        # behaviour here, but it is worth saying so in the log.
        logger.info("auth-event purge disabled (AUTH_EVENT_RETENTION_DAYS=%s)", days)
        return {"login_events": 0, "device_sessions": 0, "retention_days": days}

    cutoff = (now or timezone.now()) - timedelta(days=days)

    # hard_delete, not delete: `.delete()` on a TenantScopedQuerySet is a SOFT
    # delete that stamps deleted_at and leaves the IP and user agent in the table.
    # A retention job that soft-deletes is a retention job that does nothing.
    events, _ = LoginEvent.all_objects.all_tenants().filter(created_at__lt=cutoff).hard_delete()
    sessions, _ = (
        DeviceSession.all_objects.all_tenants().filter(created_at__lt=cutoff).hard_delete()
    )

    logger.info(
        "auth-event purge: removed %s login events and %s device sessions older than %s days",
        events, sessions, days,
    )
    return {"login_events": events, "device_sessions": sessions, "retention_days": days}


@shared_task
def purge_expired_auth_events_task():
    """Celery-beat entry point. Thin by design — the logic above is testable
    without a broker."""
    return purge_expired_auth_events()
