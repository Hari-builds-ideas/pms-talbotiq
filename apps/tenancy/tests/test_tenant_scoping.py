import pytest

from apps.tenancy.context import (
    mark_request_active,
    reset_request_active,
    tenant_context,
)
from apps.testsupport.factories import ScopedThingFactory, TenantFactory
from apps.testsupport.models import ScopedThing

pytestmark = pytest.mark.django_db


def test_reads_are_scoped_to_current_tenant():
    a = TenantFactory()
    b = TenantFactory()
    thing_a = ScopedThingFactory(tenant=a, name="a-thing")
    thing_b = ScopedThingFactory(tenant=b, name="b-thing")

    with tenant_context(a):
        assert set(ScopedThing.objects.values_list("id", flat=True)) == {thing_a.id}
    with tenant_context(b):
        assert set(ScopedThing.objects.values_list("id", flat=True)) == {thing_b.id}


def test_no_context_fails_closed():
    a = TenantFactory()
    ScopedThingFactory(tenant=a)
    # Nothing bound -> zero rows. Never the whole table.
    assert ScopedThing.objects.count() == 0
    assert list(ScopedThing.objects.all()) == []


def test_cross_tenant_read_is_impossible():
    a = TenantFactory()
    b = TenantFactory()
    thing_b = ScopedThingFactory(tenant=b, name="secret-b")
    with tenant_context(a):
        assert not ScopedThing.objects.filter(id=thing_b.id).exists()
        assert ScopedThing.objects.filter(name="secret-b").count() == 0


def test_cross_tenant_write_blocked():
    a = TenantFactory()
    b = TenantFactory()
    with tenant_context(a):
        with pytest.raises(PermissionError):
            ScopedThing.objects.create(tenant=b, name="evil")


def test_write_without_context_or_tenant_fails_closed():
    with pytest.raises(ValueError):
        ScopedThing(name="orphan").save()


def test_save_auto_stamps_current_tenant():
    a = TenantFactory()
    with tenant_context(a):
        thing = ScopedThing(name="auto")
        thing.save()
    assert str(thing.tenant_id) == str(a.id)


def test_explicit_tenant_without_context_is_system_path():
    a = TenantFactory()
    # No context, explicit tenant -> allowed (system/provisioning path).
    thing = ScopedThing.objects.create(tenant=a, name="provisioned")
    assert str(thing.tenant_id) == str(a.id)


def test_soft_delete_hides_rows_but_keeps_them():
    a = TenantFactory()
    thing = ScopedThingFactory(tenant=a)
    with tenant_context(a):
        thing.delete()  # soft
        assert ScopedThing.objects.filter(id=thing.id).count() == 0
        assert ScopedThing.all_objects.filter(id=thing.id).count() == 1
        assert ScopedThing.objects.with_deleted().filter(id=thing.id).count() == 1
    # Physically still present.
    assert ScopedThing.all_objects.all_tenants().filter(id=thing.id).exists()


def test_hard_delete_removes_row():
    a = TenantFactory()
    thing = ScopedThingFactory(tenant=a)
    with tenant_context(a):
        thing.delete(hard=True)
    assert not ScopedThing.objects.all_tenants().filter(id=thing.id).exists()


def test_all_tenants_is_blocked_on_request_path():
    token = mark_request_active()
    try:
        with pytest.raises(RuntimeError):
            ScopedThing.objects.all_tenants()
    finally:
        reset_request_active(token)


def test_all_tenants_allowed_for_system_code():
    a = TenantFactory()
    b = TenantFactory()
    ScopedThingFactory(tenant=a)
    ScopedThingFactory(tenant=b)
    assert ScopedThing.objects.all_tenants().count() == 2
