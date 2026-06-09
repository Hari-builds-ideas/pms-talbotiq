"""
RBAC engine (Agent D).

Server-side enforcement of the §2 Roles & Permissions matrix, split into two
orthogonal concerns:
  - **Capabilities** (``matrix.py``): what a role may *do* (the verb gate).
  - **Scopes** (``scope.py``): what data a role may *see* (the row gate).

Public surface (re-exported here for ergonomic imports)::

    from apps.rbac import (
        Capability, Role, CAPABILITIES, role_has_capability,
        Scope, scope_for_role, actor_can_access,
        HasCapability, WithinScope, require_capability,
        RBACMixin, requires_capability,
    )

The submodules avoid importing Django at module top level except where the ORM
is genuinely needed (``scope.py``, ``permissions.py``, ``mixins.py``); the
matrix is pure data.
"""
from .decorators import requires_capability
from .matrix import (
    CAPABILITIES,
    Capability,
    Role,
    role_has_capability,
)
from .mixins import RBACMixin
from .permissions import HasCapability, WithinScope, require_capability
from .scope import Scope, actor_can_access, reporting_subtree_ids, scope_for_role

__all__ = [
    # matrix
    "CAPABILITIES",
    "Capability",
    "Role",
    "role_has_capability",
    # scope
    "Scope",
    "scope_for_role",
    "reporting_subtree_ids",
    "actor_can_access",
    # permissions
    "HasCapability",
    "WithinScope",
    "require_capability",
    # mixins / decorators
    "RBACMixin",
    "requires_capability",
]
