"""
Administration services — Admin-only user/role/tenant-config management, all
audited before effect; the reporting line reuses the Module-7 cycle check.
"""
import pytest

from apps.administration import services
from apps.administration.exceptions import InvalidAdminInput
from apps.administration.models import TenantConfig
from apps.audit.models import AuditLog
from apps.identity.models import User
from apps.org.exceptions import ReportingCycle
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


# ── user / role management ─────────────────────────────────────────────────────


def test_create_user_in_tenant_is_audited(org):
    user = services.create_user(
        org.admin, email="newhire@acme.test", role="EMPLOYEE", manager=org.manager
    )
    assert user.tenant_id == org.tenant.id
    assert user.role == "EMPLOYEE"
    assert user.manager_id == org.manager.id
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="admin.user_created").exists()
        # The new user can be looked up and authenticates (has a usable record).
        assert User.objects.filter(email="newhire@acme.test").exists()


def test_create_user_duplicate_email_is_422(org):
    services.create_user(org.admin, email="dupe@acme.test", role="EMPLOYEE")
    with pytest.raises(InvalidAdminInput):
        services.create_user(org.admin, email="dupe@acme.test", role="EMPLOYEE")


def test_create_user_unknown_role_is_422(org):
    with pytest.raises(InvalidAdminInput):
        services.create_user(org.admin, email="x@acme.test", role="WIZARD")


def test_set_role_is_audited(org):
    services.set_role(org.admin, org.report, "MANAGER")
    org.report.refresh_from_db()
    assert org.report.role == "MANAGER"
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="admin.role_assigned").exists()


def test_deactivate_user_is_audited(org):
    services.set_active(org.admin, org.report, is_active=False)
    org.report.refresh_from_db()
    assert org.report.is_active is False
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="admin.user_deactivated").exists()


def test_set_reporting_line_reuses_cycle_check(org):
    # Reassigning the manager to report to their own report is a cycle (Module 7).
    with pytest.raises(ReportingCycle):
        services.set_reporting_line(org.admin, org.manager, org.report)


def test_set_reporting_line_moves_a_user(org):
    # Move peer (under hrbp) to report to manager — no cycle.
    services.set_reporting_line(org.admin, org.peer, org.manager)
    org.peer.refresh_from_db()
    assert org.peer.manager_id == org.manager.id


def test_list_users_is_tenant_scoped(org, other_tenant):
    from apps.testsupport.factories import UserFactory

    UserFactory(tenant=other_tenant, role="EMPLOYEE", email="outsider@other.test")
    emails = {u.email for u in services.list_users(org.admin)}
    assert "outsider@other.test" not in emails
    assert "admin@acme.test" in emails


# ── tenant config ──────────────────────────────────────────────────────────────


def test_tenant_config_upsert_is_audited(org):
    config = services.update_tenant_config(org.admin, settings={"locale": "en-GB", "weekStart": "MON"})
    assert config.settings["locale"] == "en-GB"
    # Upsert: a second update replaces, does not duplicate.
    services.update_tenant_config(org.admin, settings={"locale": "en-US"})
    with tenant_context(org.tenant):
        assert TenantConfig.objects.count() == 1
        assert TenantConfig.objects.first().settings == {"locale": "en-US"}
        assert AuditLog.objects.filter(action="admin.tenant_config_updated").exists()


def test_tenant_config_non_object_is_422(org):
    with pytest.raises(InvalidAdminInput):
        services.update_tenant_config(org.admin, settings=["not", "a", "dict"])


def test_tenant_config_is_tenant_scoped(org, other_tenant):
    services.update_tenant_config(org.admin, settings={"x": 1})
    with tenant_context(other_tenant):
        assert TenantConfig.objects.count() == 0
