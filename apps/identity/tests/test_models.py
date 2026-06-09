import pytest
from django.db import IntegrityError, transaction

from apps.identity.models import User
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_password_is_argon2_hashed():
    user = UserFactory(password="s3cretpass!")
    assert user.password.startswith("argon2")
    assert user.check_password("s3cretpass!")
    assert not user.check_password("wrong")


def test_email_unique_per_tenant_but_shared_across_tenants():
    t1 = TenantFactory()
    t2 = TenantFactory()
    UserFactory(tenant=t1, email="dup@x.com")
    # Same email under a different tenant is fine.
    UserFactory(tenant=t2, email="dup@x.com")
    # Duplicate within the same tenant is rejected by the unique constraint.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            UserFactory(tenant=t1, email="dup@x.com")


def test_create_user_requires_tenant():
    with pytest.raises(ValueError):
        User.objects.create_user(email="x@y.com", password="p")


def test_create_user_requires_email():
    t = TenantFactory()
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="p", tenant=t)


def test_user_reads_are_tenant_scoped():
    t1 = TenantFactory()
    t2 = TenantFactory()
    u1 = UserFactory(tenant=t1)
    u2 = UserFactory(tenant=t2)
    with tenant_context(t1):
        assert set(User.objects.values_list("id", flat=True)) == {u1.id}
    with tenant_context(t2):
        assert set(User.objects.values_list("id", flat=True)) == {u2.id}


def test_role_predicates():
    admin = UserFactory(role="ADMIN")
    employee = UserFactory(role="EMPLOYEE")
    assert admin.is_admin and not admin.is_employee
    assert employee.is_employee and not employee.is_admin


def test_reporting_line_relationship():
    t = TenantFactory()
    boss = UserFactory(tenant=t, role="MANAGER")
    report = UserFactory(tenant=t, role="EMPLOYEE", manager=boss)
    assert report.manager_id == boss.id
    # Reverse relations go through the tenant-scoped manager, so they require a
    # bound tenant (always present on a request path; explicit in system/tests).
    with tenant_context(t):
        assert list(boss.reports.values_list("id", flat=True)) == [report.id]
