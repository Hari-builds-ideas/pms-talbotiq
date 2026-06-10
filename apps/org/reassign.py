"""
The ONLY place Module 7 mutates the reporting tree: an explicit, cycle-checked
reassignment of ``User.manager``. Positions are untouched here (decision 4).

Cycle detection: the new manager must not be the user themselves, nor anyone in
the user's own subtree (else a loop — 422 REPORTING_CYCLE). The transitive case
is covered because ``reporting_subtree_ids`` walks the whole subtree (e.g. moving
a grandparent under a grandchild is rejected). The new manager must be active +
in-tenant. Audits BEFORE the change and invalidates the org cache (the tenant's
RBAC scope is computed live from ``User.manager``, so clearing the org namespace
is sufficient — there is no separate scope cache to clear).
"""
from __future__ import annotations

from apps.audit.services import record
from apps.rbac.scope import reporting_subtree_ids
from apps.tenancy.context import tenant_context

from .exceptions import InvalidOrgInput, ReportingCycle
from .services import invalidate_org_cache


def reassign_reporting_line(actor, user, new_manager):
    """Move ``user`` to report to ``new_manager`` (cycle-checked, audited)."""
    if new_manager is None:
        raise InvalidOrgInput("new_manager_missing", "The new manager could not be found.")
    if str(new_manager.tenant_id) != str(actor.tenant_id):
        raise InvalidOrgInput("new_manager_cross_tenant", "The new manager is in another tenant.")
    if not new_manager.is_active:
        raise InvalidOrgInput("new_manager_inactive", "The new manager is not active.")

    if str(new_manager.id) == str(user.id):
        raise ReportingCycle(user.id, new_manager.id)

    tid = user.tenant_id
    with tenant_context(tid):
        # Transitive cycle guard: the proposed manager must not sit within the
        # user's own subtree (direct or indirect report).
        if new_manager.id in reporting_subtree_ids(user):
            raise ReportingCycle(user.id, new_manager.id)

        record(
            action="reporting_line.reassigned",
            actor=actor,
            target_type="user",
            target_id=user.id,
            metadata={
                "previous_manager": str(user.manager_id) if user.manager_id else None,
                "new_manager": str(new_manager.id),
            },
            tenant=tid,
        )
        user.manager = new_manager
        user.save(update_fields=["manager", "updated_at"])
    invalidate_org_cache(tid)
    return user
