"""
Tests for the append-only audit log.

Covers: tenant-scoped reads (fail closed + cross-tenant isolation), app-level
immutability (update/delete/save), DB-level immutability enforced by MySQL
triggers even against raw SQL, the writer's tenant resolution, and the
``all_tenants()`` system escape hatch.
"""
import pytest
from django.db import OperationalError, connection

from apps.audit.exceptions import AuditLogImmutableError
from apps.audit.models import AuditLog
from apps.audit.services import audit_action, record
from apps.tenancy.context import (
    mark_request_active,
    reset_request_active,
    tenant_context,
)
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# 1. INSERT + SELECT, scoping, fail-closed                                    #
# --------------------------------------------------------------------------- #
def test_record_inserts_and_is_readable_within_tenant():
    t = TenantFactory()
    actor = UserFactory(tenant=t)
    entry = record(
        action="review.approved",
        actor=actor,
        target_type="Review",
        target_id="abc-123",
        justification="Looks good",
        metadata={"score": 5},
        tenant=t,
    )
    assert entry.pk is not None
    assert str(entry.tenant_id) == str(t.id)
    assert entry.actor_id == actor.id
    assert entry.metadata == {"score": 5}

    with tenant_context(t):
        rows = list(AuditLog.objects.all())
        assert [r.id for r in rows] == [entry.id]
        assert AuditLog.objects.get(id=entry.id).action == "review.approved"


def test_reads_are_isolated_across_tenants():
    a = TenantFactory()
    b = TenantFactory()
    entry_a = record(action="a.event", tenant=a)
    record(action="b.event", tenant=b)

    with tenant_context(a):
        assert set(AuditLog.objects.values_list("id", flat=True)) == {entry_a.id}
        assert AuditLog.objects.filter(action="b.event").count() == 0
    with tenant_context(b):
        assert not AuditLog.objects.filter(id=entry_a.id).exists()


def test_no_context_fails_closed():
    a = TenantFactory()
    record(action="a.event", tenant=a)
    # Nothing bound -> zero rows. Never the whole table.
    assert AuditLog.objects.count() == 0
    assert list(AuditLog.objects.all()) == []


def test_target_id_is_coerced_to_str():
    t = TenantFactory()
    entry = record(action="thing.touched", target_id=42, tenant=t)
    assert entry.target_id == "42"


# --------------------------------------------------------------------------- #
# 2. App-level immutability                                                   #
# --------------------------------------------------------------------------- #
def test_queryset_update_is_forbidden():
    t = TenantFactory()
    record(action="x.event", tenant=t)
    with tenant_context(t):
        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(action="x.event").update(action="tampered")


def test_queryset_delete_is_forbidden():
    t = TenantFactory()
    record(action="x.event", tenant=t)
    with tenant_context(t):
        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(action="x.event").delete()


def test_resaving_an_existing_row_is_forbidden():
    t = TenantFactory()
    entry = record(action="x.event", tenant=t)
    with tenant_context(t):
        loaded = AuditLog.objects.get(id=entry.id)
        loaded.action = "tampered"
        with pytest.raises(AuditLogImmutableError):
            loaded.save()


# --------------------------------------------------------------------------- #
# 3. DB-level immutability — MySQL triggers fire even on raw SQL               #
# --------------------------------------------------------------------------- #
# Regular (rolled-back) django_db, NOT transaction=True: the SIGNAL is what
# proves immutability, and a TransactionTestCase teardown would itself try to
# flush audit_log and collide with the BEFORE DELETE trigger. The row is read
# back via the same connection — MySQL keeps the transaction alive after a
# statement error, so the row is provably unchanged. UUIDs are stored as 32-char
# hex WITHOUT dashes, so raw SQL must match on ``.hex``.
def test_raw_update_is_blocked_by_trigger(db):
    t = TenantFactory()
    entry = record(action="x.event", tenant=t)
    with connection.cursor() as cursor:
        with pytest.raises(OperationalError):
            cursor.execute(
                "UPDATE audit_log SET action=%s WHERE id=%s",
                ["tampered", entry.id.hex],
            )
    with tenant_context(t):
        assert AuditLog.objects.get(id=entry.id).action == "x.event"


def test_raw_delete_is_blocked_by_trigger(db):
    t = TenantFactory()
    entry = record(action="x.event", tenant=t)
    with connection.cursor() as cursor:
        with pytest.raises(OperationalError):
            cursor.execute("DELETE FROM audit_log WHERE id=%s", [entry.id.hex])
    with tenant_context(t):
        assert AuditLog.objects.filter(id=entry.id).exists()


# --------------------------------------------------------------------------- #
# 4. Writer tenant resolution                                                 #
# --------------------------------------------------------------------------- #
def test_record_stamps_current_tenant_when_arg_omitted():
    t = TenantFactory()
    with tenant_context(t):
        entry = record(action="from.context")
    assert str(entry.tenant_id) == str(t.id)


def test_record_without_tenant_or_context_raises():
    with pytest.raises(ValueError):
        record(action="orphan")


def test_record_accepts_tenant_id_string():
    t = TenantFactory()
    entry = record(action="by.id", tenant=str(t.id))
    assert str(entry.tenant_id) == str(t.id)


def test_audit_action_writes_record_before_yield():
    t = TenantFactory()
    actor = UserFactory(tenant=t)
    with tenant_context(t):
        with audit_action(action="review.approved", actor=actor, target_id="r1") as entry:
            # The record already exists before the body (the side effect) runs.
            assert AuditLog.objects.filter(id=entry.id).exists()
    assert entry.action == "review.approved"
    assert entry.target_id == "r1"


# --------------------------------------------------------------------------- #
# 5. all_tenants() escape hatch                                               #
# --------------------------------------------------------------------------- #
def test_all_tenants_blocked_on_request_path():
    token = mark_request_active()
    try:
        with pytest.raises(RuntimeError):
            AuditLog.objects.all_tenants()
    finally:
        reset_request_active(token)


def test_all_tenants_returns_cross_tenant_rows_for_system_code():
    a = TenantFactory()
    b = TenantFactory()
    record(action="a.event", tenant=a)
    record(action="b.event", tenant=b)
    assert AuditLog.objects.all_tenants().count() == 2
