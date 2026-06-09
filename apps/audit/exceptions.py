"""Audit-app exceptions."""


class AuditLogImmutableError(Exception):
    """Raised on any attempt to mutate or delete an existing audit row.

    The audit log is append-only. App-level guards (model ``save()`` and the
    queryset's ``update()``/``delete()``) raise this; the database enforces the
    same rule independently via BEFORE UPDATE / BEFORE DELETE triggers.
    """
