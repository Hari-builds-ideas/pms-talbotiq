"""
Ergonomic RBAC wiring for DRF views.

A view declares *what it gates* and gets enforcement for free::

    class ApproveReviewView(RBACMixin, APIView):
        required_capability = Capability.APPROVE_REVIEW          # role gate
        scope_subject_attr = "employee"                          # row gate (optional)

        def post(self, request, *args, **kwargs):
            review = self.get_review(...)
            self.check_object_scope(review)   # 403 if out of scope
            ...

:class:`RBACMixin` assembles ``permission_classes`` so the framework enforces
``IsAuthenticated`` + :class:`~apps.rbac.permissions.HasCapability`, and adds
:class:`~apps.rbac.permissions.WithinScope` whenever the view opts into
object-level scoping (by setting ``scope_subject_attr`` or
``enforce_object_scope = True``). For views that do not go through DRF's
``get_object``/``check_object_permissions`` flow, :meth:`check_object_scope`
runs the same scope check imperatively and raises ``PermissionDenied`` (403).
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from .permissions import HasCapability, WithinScope, _resolve_subject
from .scope import actor_can_access


class RBACMixin:
    """Mixin for DRF ``APIView`` / ``GenericAPIView`` subclasses.

    Configuration attributes the subclass sets:
      - ``required_capability`` (str): the capability the endpoint gates. Wired
        into :class:`HasCapability`.
      - ``scope_subject_attr`` (str, optional): names the attribute on the
        handled object that identifies the subject user (a ``User`` or something
        with a ``.user`` FK). Presence opts the view into object-level scoping.
      - ``enforce_object_scope`` (bool, optional): force object-level scoping on
        even when the subject IS the object itself (no ``scope_subject_attr``).
    """

    required_capability: str | None = None
    scope_subject_attr: str | None = None
    enforce_object_scope: bool = False

    def get_permissions(self):
        """Build the permission stack from the view's RBAC declaration.

        Always: ``IsAuthenticated`` + ``HasCapability``. Plus ``WithinScope``
        when the view opts into object scoping. Overriding ``get_permissions``
        (rather than the class-level ``permission_classes``) keeps the decision
        per-instance and lets it read the subclass's attributes.
        """
        classes = [IsAuthenticated, HasCapability]
        if self.scope_subject_attr is not None or self.enforce_object_scope:
            classes.append(WithinScope)
        return [cls() for cls in classes]

    def check_object_scope(self, obj) -> None:
        """Enforce data-scope on ``obj`` imperatively, raising
        ``PermissionDenied`` (HTTP 403) when the resolved subject is out of
        scope.

        Use this in views that don't flow through DRF's
        ``get_object``/``check_object_permissions`` machinery (e.g. an action
        view that loads its own target). The subject is resolved exactly as the
        :class:`WithinScope` permission resolves it.
        """
        user = getattr(self.request, "user", None)
        subject = _resolve_subject(self, obj)
        if user is None or not user.is_authenticated or subject is None:
            raise PermissionDenied(WithinScope.message)
        if not actor_can_access(user, subject):
            raise PermissionDenied(WithinScope.message)
