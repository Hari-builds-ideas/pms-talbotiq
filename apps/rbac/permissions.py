"""
DRF permission classes that enforce the RBAC matrix server-side.

Two orthogonal checks, mirroring the two halves of the model:
  - :class:`HasCapability` — request-level. Does the caller's *role* hold the
    capability the view requires? (the verb gate; see ``matrix.py``)
  - :class:`WithinScope` — object-level. Is the target record within the
    caller's *data scope*? (the row gate; see ``scope.py``)

Both fail closed: an unauthenticated request, a view that forgot to declare its
``required_capability``, or an unresolvable subject all deny. DRF turns a False
``has_permission`` into 403 (401 if unauthenticated) and a False
``has_object_permission`` into 403.

These compose with the project default ``IsAuthenticated`` and rely on
``TenantMiddleware`` having bound the tenant from the verified JWT before the
view runs, so any scope query inside ``WithinScope`` is correctly tenant-scoped.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from .matrix import role_has_capability
from .scope import actor_can_access


def _resolve_subject(view, obj):
    """Resolve the :class:`~apps.identity.models.User` a scope check applies to.

    The view names the attribute holding the subject via ``scope_subject_attr``;
    that attribute may itself be a ``User`` or an object carrying a ``.user``
    FK. When ``scope_subject_attr`` is unset (or names a missing attribute) and
    ``obj`` looks like a user (has ``id`` + ``tenant_id`` + ``role``), ``obj`` is
    treated as the subject directly. Returns ``None`` when no subject can be
    resolved — the caller then denies (fails closed).
    """
    attr = getattr(view, "scope_subject_attr", None)
    candidate = getattr(obj, attr, None) if attr else obj
    if candidate is None:
        return None
    # Unwrap a record that points at a user via a ``.user`` FK.
    if not _looks_like_user(candidate) and hasattr(candidate, "user"):
        candidate = candidate.user
    return candidate if _looks_like_user(candidate) else None


def _looks_like_user(obj) -> bool:
    """Duck-type a User without importing-coupling every caller: the attributes
    the scope check needs are ``id``, ``tenant_id`` and ``role``."""
    return all(hasattr(obj, name) for name in ("id", "tenant_id", "role"))


class HasCapability(BasePermission):
    """Allow the request iff the caller's role holds the view's
    ``required_capability``.

    The view declares the capability it gates::

        class ApproveReviewView(APIView):
            required_capability = Capability.APPROVE_REVIEW

    A view with no ``required_capability`` denies (a capability-gated endpoint
    must say what it gates; silence is not consent).
    """

    message = "Your role does not permit this action."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        capability = getattr(view, "required_capability", None)
        if not capability:
            return False
        return role_has_capability(user.role, capability)


class WithinScope(BasePermission):
    """Object-level: allow iff the resolved subject is within the caller's data
    scope (see :func:`_resolve_subject` for how the subject is found).

    DRF only invokes ``has_object_permission`` when the view calls
    ``check_object_permissions`` (e.g. via ``get_object``); for non-object views
    use ``RBACMixin.check_object_scope`` to run the same check explicitly.
    ``has_permission`` returns True here so this class never blocks at the
    request level — capability gating is :class:`HasCapability`'s job.
    """

    message = "This record is outside your access scope."

    def has_permission(self, request, view) -> bool:
        # Object-level only; request-level admission is decided elsewhere.
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        subject = _resolve_subject(view, obj)
        if subject is None:
            return False
        return actor_can_access(user, subject)


def require_capability(capability: str) -> type[BasePermission]:
    """Build a :class:`HasCapability` subclass pinned to ``capability``.

    Useful when listing permission classes directly on a view instead of via
    :class:`~apps.rbac.mixins.RBACMixin`::

        permission_classes = [IsAuthenticated, require_capability(Capability.APPROVE_REVIEW)]

    The returned class ignores the view's ``required_capability`` attribute and
    always checks the bound ``capability``.
    """

    class _PinnedCapability(HasCapability):
        _capability = capability

        def has_permission(self, request, view) -> bool:
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return False
            return role_has_capability(user.role, self._capability)

    _PinnedCapability.__name__ = f"HasCapability[{capability}]"
    _PinnedCapability.__qualname__ = _PinnedCapability.__name__
    return _PinnedCapability
