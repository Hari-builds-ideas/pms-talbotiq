"""
Canonical audit writer.

``record()`` is the one way the rest of the system writes audit rows. The
``audit_action()`` context manager writes the immutable record *before* the
side effect runs, so the evidence of intent exists even if the action then
fails — every consequential action audits before it takes effect.
"""
from contextlib import contextmanager

from apps.tenancy.context import get_current_tenant_id

from .models import AuditLog


def _resolve_tenant_id(tenant):
    """Resolve a tenant id (str) from an explicit arg or the current context.

    ``tenant`` may be a ``Tenant`` instance, an id, or None (fall back to the
    bound context). Raises ``ValueError`` when no tenant can be determined.
    """
    if tenant is not None:
        return str(getattr(tenant, "id", tenant))
    current = get_current_tenant_id()
    if current is None:
        raise ValueError(
            "Cannot record an audit event without a tenant: pass tenant= or bind "
            "a tenant context."
        )
    return current


def record(
    *,
    action,
    actor=None,
    target_type="",
    target_id="",
    justification="",
    metadata=None,
    tenant=None,
):
    """Append a single audit row and return it.

    The tenant is taken from ``tenant`` (a ``Tenant`` instance or id) or, failing
    that, the current-tenant context. ``target_id`` is coerced to ``str``.
    """
    tenant_id = _resolve_tenant_id(tenant)
    return AuditLog.objects.create(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id="" if target_id is None else str(target_id),
        justification=justification,
        metadata=metadata if metadata is not None else {},
    )


@contextmanager
def audit_action(**kwargs):
    """Write the audit record first, then yield to run the action.

    Usage::

        with audit_action(action="review.approved", actor=user, target_id=r.id):
            approve(r)

    The returned ``AuditLog`` is yielded so callers can reference it. Because the
    record is committed before the body runs, the immutable evidence exists prior
    to any side effect taking effect.
    """
    entry = record(**kwargs)
    yield entry
