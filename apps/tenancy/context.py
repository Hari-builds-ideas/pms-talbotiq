"""
Current-tenant context.

The active tenant for a unit of work is held in a contextvar (thread- and
async-safe). It is set ONLY from cryptographically verified JWT claims by
``TenantMiddleware`` on the request path, or explicitly via ``tenant_context``
in system/test code. The ``TenantScopedManager`` reads it to scope every query.

``_request_active`` records whether we are currently inside an API/request
cycle. The ``all_tenants()`` escape hatch consults it and refuses to run on a
request path — that escape is for system and migration code only.
"""
import contextvars
from contextlib import contextmanager

_current_tenant_id: contextvars.ContextVar = contextvars.ContextVar(
    "pms_current_tenant_id", default=None
)
_request_active: contextvars.ContextVar = contextvars.ContextVar(
    "pms_request_active", default=False
)


def _normalize(tenant_id):
    if tenant_id is None:
        return None
    return str(tenant_id)


def get_current_tenant_id():
    """Return the active tenant id (str) or None when no tenant is bound."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id):
    """Bind the current tenant id; returns a token for ``reset_current_tenant_id``."""
    return _current_tenant_id.set(_normalize(tenant_id))


def reset_current_tenant_id(token):
    _current_tenant_id.reset(token)


@contextmanager
def tenant_context(tenant):
    """Bind ``tenant`` (a Tenant instance or an id) for the duration of the block.

    Used by system code, the authentication bootstrap, and tests to scope ORM
    access without an HTTP request.
    """
    tenant_id = getattr(tenant, "id", tenant)
    token = set_current_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant_id(token)


def mark_request_active():
    """Mark the start of an API/request cycle; returns a token to reset with."""
    return _request_active.set(True)


def reset_request_active(token):
    _request_active.reset(token)


def is_request_active():
    return _request_active.get()
