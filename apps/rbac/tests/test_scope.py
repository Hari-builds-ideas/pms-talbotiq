"""
Scope tests — data visibility per role, plus cross-tenant defence in depth.

All ORM/scope calls run inside ``with tenant_context(org.tenant):`` to simulate
what ``TenantMiddleware`` does on a real request (the tenant-scoped manager fails
closed otherwise).

The ``org`` fixture's reporting tree::

    admin, hrbp
    manager (reports to hrbp)
      └── report   (EMPLOYEE, reports to manager)
    peer           (EMPLOYEE, reports to hrbp — a PEER of `report`, not under manager)
"""
import pytest

from apps.identity.models import User
from apps.rbac.scope import (
    Scope,
    actor_can_access,
    reporting_subtree_ids,
    scope_for_role,
)
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


# ── scope_for_role ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "role, expected",
    [
        (User.Role.EMPLOYEE, Scope.OWN),
        (User.Role.MANAGER, Scope.TEAM),
        (User.Role.HRBP, Scope.TENANT),
        (User.Role.ADMIN, Scope.TENANT),
    ],
)
def test_scope_for_role(role, expected):
    assert scope_for_role(role) is expected


def test_scope_for_unknown_role_fails_closed():
    assert scope_for_role("WIZARD") is Scope.OWN


def test_hrbp_and_admin_share_data_scope():
    # By design, not a placeholder: the business-unit tier belonged to a separate
    # HRBP product that was discontinued (see scope.py docstring). The two roles
    # differ in capabilities, not in what rows they can see.
    assert scope_for_role(User.Role.HRBP) is scope_for_role(User.Role.ADMIN)


# ── reporting_subtree_ids ──────────────────────────────────────────────
def test_subtree_excludes_self_and_collects_transitive(org):
    with tenant_context(org.tenant):
        # hrbp -> manager -> report ; hrbp -> peer (transitive under hrbp).
        hrbp_subtree = reporting_subtree_ids(org.hrbp)
        assert org.manager.id in hrbp_subtree
        assert org.report.id in hrbp_subtree  # transitive (via manager)
        assert org.peer.id in hrbp_subtree
        assert org.hrbp.id not in hrbp_subtree  # self never included


def test_manager_subtree_is_only_direct_and_transitive_reports(org):
    with tenant_context(org.tenant):
        subtree = reporting_subtree_ids(org.manager)
        assert subtree == {org.report.id}  # only `report`, not `peer`


def test_leaf_employee_has_empty_subtree(org):
    with tenant_context(org.tenant):
        assert reporting_subtree_ids(org.report) == set()


def test_subtree_terminates_on_cycle(org, make_user):
    """A corrupt reporting loop must not spin forever; the cycle guard stops it."""
    with tenant_context(org.tenant):
        a = make_user(tenant=org.tenant, role="MANAGER", email="cyc-a@acme.test")
        b = make_user(tenant=org.tenant, role="MANAGER", email="cyc-b@acme.test", manager=a)
        # Close the loop: a now reports to b.
        a.manager = b
        a.save(update_fields=["manager"])
        subtree = reporting_subtree_ids(a)
        assert subtree == {b.id}  # b collected once; recursion back to `a` is skipped


# ── actor_can_access: OWN (Employee) ───────────────────────────────────
def test_employee_can_access_self(org):
    with tenant_context(org.tenant):
        assert actor_can_access(org.report, org.report) is True


def test_employee_cannot_access_peer(org):
    with tenant_context(org.tenant):
        assert actor_can_access(org.report, org.peer) is False


def test_employee_cannot_access_their_manager(org):
    with tenant_context(org.tenant):
        assert actor_can_access(org.report, org.manager) is False


# ── actor_can_access: TEAM (Manager) ───────────────────────────────────
def test_manager_can_access_self(org):
    with tenant_context(org.tenant):
        assert actor_can_access(org.manager, org.manager) is True


def test_manager_can_access_their_report(org):
    with tenant_context(org.tenant):
        assert actor_can_access(org.manager, org.report) is True


def test_manager_rejects_out_of_scope_peer(org):
    # `peer` reports to hrbp, not to manager — the canonical out-of-scope case.
    with tenant_context(org.tenant):
        assert actor_can_access(org.manager, org.peer) is False


def test_manager_cannot_access_upward(org):
    with tenant_context(org.tenant):
        assert actor_can_access(org.manager, org.hrbp) is False


# ── actor_can_access: TENANT (HRBP / Admin) ────────────────────────────
@pytest.mark.parametrize("actor_attr", ["hrbp", "admin"])
def test_tenant_scope_can_access_everyone_in_tenant(org, actor_attr):
    actor = getattr(org, actor_attr)
    with tenant_context(org.tenant):
        for subject in (org.admin, org.hrbp, org.manager, org.report, org.peer):
            assert actor_can_access(actor, subject) is True


# ── Cross-tenant defence in depth ──────────────────────────────────────
@pytest.mark.parametrize("actor_attr", ["admin", "hrbp"])
def test_cross_tenant_is_never_in_scope(org, other_tenant, make_user, actor_attr):
    actor = getattr(org, actor_attr)
    # An outsider in a different tenant — created under its own bound context.
    with tenant_context(other_tenant):
        outsider = make_user(tenant=other_tenant, role="EMPLOYEE", email="x@other.test")
    with tenant_context(org.tenant):
        assert actor_can_access(actor, outsider) is False


def test_none_actor_or_subject_fails_closed(org):
    with tenant_context(org.tenant):
        assert actor_can_access(None, org.report) is False
        assert actor_can_access(org.admin, None) is False
