"""
The auth-event retention sweep (D3).

``LoginEvent`` and ``DeviceSession`` hold an IP and a user agent per sign-in and
per device. Across a tenant that is a movement log of the whole workforce, kept
by default and useful for a few weeks.

The failure this guards against is the quiet one: a retention job that runs,
logs a cheerful count, and deletes nothing — either because the tenant-scoped
manager fails closed off the request path, or because ``.delete()`` here is a
SOFT delete that leaves every row and every IP address in the table.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import DeviceSession, LoginEvent
from apps.identity.tasks import purge_expired_auth_events
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _make(user, tenant, *, age_days):
    """A login event and a device session stamped `age_days` in the past.

    ``created_at`` is auto_now_add, so it has to be written after the fact with a
    queryset update — assigning it on create is silently ignored, and a test that
    did so would "pass" by purging rows that were all brand new.
    """
    when = timezone.now() - timedelta(days=age_days)
    with tenant_context(tenant):
        event = LoginEvent.objects.create(
            tenant=tenant, user=user, email=user.email, event="LOGIN_SUCCESS",
            ip="203.0.113.9", user_agent="Firefox",
        )
        session = DeviceSession.objects.create(
            tenant=tenant, user=user, ip="203.0.113.9", user_agent="Firefox",
            last_seen=when,
        )
        LoginEvent.objects.filter(pk=event.pk).update(created_at=when)
        DeviceSession.objects.filter(pk=session.pk).update(created_at=when)
    return event, session


@pytest.fixture
def tenant(db):
    return TenantFactory(slug="acme", name="Acme")


@pytest.fixture
def user(tenant):
    return UserFactory(tenant=tenant, email="someone@acme.test")


def test_rows_past_the_window_are_removed(tenant, user):
    old_event, old_session = _make(user, tenant, age_days=120)

    result = purge_expired_auth_events()

    assert result["login_events"] == 1
    assert result["device_sessions"] == 1
    with tenant_context(tenant):
        assert not LoginEvent.all_objects.filter(pk=old_event.pk).exists()
        assert not DeviceSession.all_objects.filter(pk=old_session.pk).exists()


def test_rows_inside_the_window_are_untouched(tenant, user):
    event, session = _make(user, tenant, age_days=30)

    purge_expired_auth_events()

    with tenant_context(tenant):
        assert LoginEvent.objects.filter(pk=event.pk).exists()
        assert DeviceSession.objects.filter(pk=session.pk).exists()


def test_the_rows_are_really_gone_not_soft_deleted(tenant, user):
    """Checked through ``all_objects``, which still sees soft-deleted rows.

    ``.delete()`` on a TenantScopedQuerySet stamps ``deleted_at`` and leaves the
    row — so a purge written the obvious way reports a healthy count while every
    IP address it claimed to remove is still in the table. Asserting through the
    default manager would pass in exactly that case.
    """
    event, session = _make(user, tenant, age_days=200)

    purge_expired_auth_events()

    with tenant_context(tenant):
        assert LoginEvent.all_objects.filter(pk=event.pk).count() == 0
        assert DeviceSession.all_objects.filter(pk=session.pk).count() == 0


def test_it_sweeps_every_tenant(user, tenant):
    """It runs off-request on celery-beat with no tenant bound. Through the
    ordinary scoped manager that fails closed — the sweep would delete nothing,
    for every tenant, forever, and report success."""
    other = TenantFactory(slug="globex", name="Globex")
    other_user = UserFactory(tenant=other, email="someone@globex.test")
    _make(user, tenant, age_days=120)
    _make(other_user, other, age_days=120)

    result = purge_expired_auth_events()

    assert result["login_events"] == 2
    assert result["device_sessions"] == 2


def test_a_revoked_session_is_still_kept_until_the_window_closes(tenant, user):
    """A session revoked yesterday is evidence about a possible compromise
    today. Purging on revocation instead of on age would delete precisely the
    row an investigation needs."""
    _, session = _make(user, tenant, age_days=2)
    with tenant_context(tenant):
        DeviceSession.objects.filter(pk=session.pk).update(revoked_at=timezone.now())

    purge_expired_auth_events()

    with tenant_context(tenant):
        assert DeviceSession.objects.filter(pk=session.pk).exists()


def test_the_window_is_configurable(tenant, user):
    _make(user, tenant, age_days=10)

    result = purge_expired_auth_events(retention_days=7)

    assert result["login_events"] == 1


def test_zero_disables_the_purge(tenant, user):
    """An explicit opt-out for a deployment under a legal hold. It must delete
    nothing rather than treating 0 as "older than now" and deleting everything —
    which is what a naive cutoff calculation would do."""
    event, session = _make(user, tenant, age_days=500)

    result = purge_expired_auth_events(retention_days=0)

    assert result == {"login_events": 0, "device_sessions": 0, "retention_days": 0}
    with tenant_context(tenant):
        assert LoginEvent.objects.filter(pk=event.pk).exists()
        assert DeviceSession.objects.filter(pk=session.pk).exists()


def test_the_beat_entry_points_at_a_task_that_exists(settings):
    """The schedule holds a DOTTED STRING, so a rename anywhere in the path fails
    at runtime on a worker rather than at import here — quietly, once a day, in a
    log nobody reads."""
    from importlib import import_module

    entry = settings.CELERY_BEAT_SCHEDULE["identity-purge-auth-events"]
    module_path, _, attr = entry["task"].rpartition(".")
    assert getattr(import_module(module_path), attr) is not None
    assert entry["schedule"] > 0
