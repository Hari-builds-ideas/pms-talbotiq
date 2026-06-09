"""
Capability decorator for view functions and view methods.

Kept at parity with :class:`~apps.rbac.permissions.HasCapability`: both consult
the same :func:`~apps.rbac.matrix.role_has_capability` and both deny by raising
DRF's ``PermissionDenied`` (HTTP 403) when the caller's role lacks the
capability — or ``NotAuthenticated`` (HTTP 401) when there is no authenticated
user. Prefer :class:`~apps.rbac.mixins.RBACMixin` on class-based views; reach for
this decorator on standalone ``@api_view`` functions or one-off method gates.

The decorated callable's first positional argument is expected to be either a
DRF ``Request`` (function-based ``@api_view``) or ``self`` followed by a
``Request`` (a view method). Both shapes are handled.
"""
from __future__ import annotations

import functools

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.request import Request

from .matrix import role_has_capability


def _extract_request(args) -> Request | None:
    """Find the DRF/HTTP request among the leading positional args, supporting
    both ``view_fn(request, ...)`` and ``method(self, request, ...)`` shapes."""
    for candidate in args[:2]:
        if hasattr(candidate, "user"):
            return candidate
    return None


def requires_capability(capability: str):
    """Decorator enforcing that the caller's role holds ``capability``.

    Raises ``NotAuthenticated`` (401) when unauthenticated, ``PermissionDenied``
    (403) when authenticated but unauthorized, and otherwise calls through::

        @api_view(["POST"])
        @requires_capability(Capability.APPROVE_REVIEW)
        def approve(request):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request = _extract_request(args)
            user = getattr(request, "user", None) if request is not None else None
            if user is None or not getattr(user, "is_authenticated", False):
                raise NotAuthenticated()
            if not role_has_capability(user.role, capability):
                raise PermissionDenied("Your role does not permit this action.")
            return func(*args, **kwargs)

        return wrapper

    return decorator
