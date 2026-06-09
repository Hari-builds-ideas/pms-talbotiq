"""
Data scope — *which records a role may see*, orthogonal to capabilities
(``matrix.py``). A capability gates the verb; a scope gates the rows.

Scope tiers:
  - ``OWN``    (Employee): only themselves / their own records.
  - ``TEAM``   (Manager): self + everyone in their reporting subtree (direct and
                transitive reports, walked via the ``User.manager`` self-FK).
  - ``TENANT`` (HRBP, Admin): everyone in the tenant.

MVP simplification — HRBP scope: the §2 spec describes HRBP as "business-unit
wide". There is no BusinessUnit model yet, so for the MVP an HRBP's data scope is
approximated as **tenant-wide**, identical to Admin's. HRBP and Admin therefore
share a data *scope* and differ only in *capabilities* (Admin alone holds
``manage_tenant``). When BusinessUnit lands, only ``scope_for_role`` and the
TENANT branch of ``actor_can_access`` need revisiting — callers are unaffected.

Tenant isolation is enforced upstream by ``TenantScopedManager`` (every query is
filtered by the bound tenant, failing closed when none is bound). The
``actor_can_access`` check here *also* requires a matching ``tenant_id`` as
defence in depth — an in-scope decision must never cross a tenant boundary even
if a caller hands us a subject loaded outside the scoped manager.

Reporting-tree queries (``reporting_subtree_ids``) use ``User.objects`` and so
MUST run inside a bound tenant context. On a request that is guaranteed by
``TenantMiddleware``; in unit tests wrap calls in ``tenant_context(...)``.
"""
from __future__ import annotations

import enum
from uuid import UUID

from .matrix import Role

# NOTE: ``apps.identity.models.User`` is imported lazily inside the functions
# that touch the ORM. Importing it at module top would run during Django's
# phase-1 app loading (this module is reachable from ``apps.rbac.__init__``),
# before the model registry is ready -> AppRegistryNotReady.


class Scope(enum.Enum):
    """A role's data-visibility tier. Ordering is not meaningful; membership is
    decided per-tier in ``actor_can_access``."""

    OWN = "OWN"
    TEAM = "TEAM"
    TENANT = "TENANT"


#: role string -> data scope. HRBP and Admin both map to TENANT (see the MVP
#: simplification in the module docstring).
_SCOPE_BY_ROLE: dict[str, Scope] = {
    Role.EMPLOYEE: Scope.OWN,
    Role.MANAGER: Scope.TEAM,
    Role.HRBP: Scope.TENANT,
    Role.ADMIN: Scope.TENANT,
}


def scope_for_role(role: str) -> Scope:
    """Return the :class:`Scope` for ``role``.

    Fails closed: an unknown/None role maps to the narrowest scope (``OWN``) so a
    misconfiguration can never widen visibility.
    """
    return _SCOPE_BY_ROLE.get(role, Scope.OWN)


def reporting_subtree_ids(manager_user: User) -> set[UUID]:
    """Return the ids of every transitive report under ``manager_user``.

    Walks the ``User.manager`` self-FK breadth-first over the tenant-scoped
    manager (so it never crosses a tenant), collecting direct reports, their
    reports, and so on. The manager's *own* id is NOT included — callers that
    need "self + team" add it themselves (``actor_can_access`` does).

    Must run inside a bound tenant context (always true on a request; use
    ``tenant_context`` in tests). Guards against cycles in the reporting graph by
    never revisiting an id already seen, so a corrupt loop terminates instead of
    spinning forever.
    """
    from apps.identity.models import User  # lazy: see module-top note

    subtree: set[UUID] = set()
    frontier: list[UUID] = [manager_user.id]
    while frontier:
        # One query per level: all users whose manager is anyone on the frontier.
        children = list(
            User.objects.filter(manager_id__in=frontier).values_list("id", flat=True)
        )
        next_frontier: list[UUID] = []
        for child_id in children:
            # Skip self-reference and anything already collected (cycle guard).
            if child_id == manager_user.id or child_id in subtree:
                continue
            subtree.add(child_id)
            next_frontier.append(child_id)
        frontier = next_frontier
    return subtree


def actor_can_access(actor: User, subject_user: User) -> bool:
    """Return True iff ``subject_user`` falls within ``actor``'s data scope.

    Decision per tier:
      - ``OWN``    -> subject is the actor.
      - ``TEAM``   -> subject is the actor, or in the actor's reporting subtree.
      - ``TENANT`` -> subject is in the same tenant as the actor.

    Cross-tenant defence in depth: regardless of tier, a differing ``tenant_id``
    is always denied first. A missing/None actor or subject denies (fails
    closed).
    """
    if actor is None or subject_user is None:
        return False
    # Defence in depth: never grant access across tenants, even though the
    # scoped manager already isolates rows per tenant.
    if subject_user.tenant_id != actor.tenant_id:
        return False

    scope = scope_for_role(actor.role)
    if scope is Scope.TENANT:
        # Same-tenant already verified above.
        return True
    if scope is Scope.OWN:
        return subject_user.id == actor.id
    # Scope.TEAM — self or anyone beneath the actor in the reporting tree.
    if subject_user.id == actor.id:
        return True
    return subject_user.id in reporting_subtree_ids(actor)
