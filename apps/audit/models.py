"""
Append-only audit log.

``AuditLog`` records every consequential action in the system. It is
deliberately NOT a :class:`~apps.tenancy.models.TenantScopedModel`: there is no
``updated_at`` and no soft delete, because an audit row may never change once
written. Immutability is enforced at three layers:

* ``save()`` refuses to rewrite an existing row (append-only).
* :class:`~apps.audit.managers.AuditLogQuerySet` forbids ``update()``/``delete()``.
* MySQL ``BEFORE UPDATE``/``BEFORE DELETE`` triggers (migration ``0002``) reject
  mutation even against raw SQL.

Writes fail closed: a row is never persisted without a tenant. The tenant is
either passed explicitly (system path) or stamped from the current-tenant
context.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.tenancy.context import get_current_tenant_id

from .exceptions import AuditLogImmutableError
from .managers import AuditLogManager


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.PROTECT,
        related_name="+",
    )
    # ``actor`` is null for system-initiated actions (no human behind them).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=128)  # e.g. "review.approved"
    target_type = models.CharField(max_length=128, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    justification = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta:
        # NOTE: the trigger SQL in migration 0002 references this exact name.
        db_table = "audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="audit_tenant_created_idx"),
        ]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    def save(self, *args, **kwargs):
        """Append-only insert. Existing rows can never be rewritten."""
        if not self._state.adding:
            raise AuditLogImmutableError(
                "audit_log is append-only: an existing AuditLog row cannot be "
                "modified."
            )
        if self.tenant_id is None:
            # Stamp the bound tenant if one is available...
            self.tenant_id = get_current_tenant_id()
        if self.tenant_id is None:
            # ...otherwise fail closed: never write an unscoped audit row.
            raise ValueError(
                "Cannot write an AuditLog without a tenant: no active tenant "
                "context and tenant is unset."
            )
        super().save(*args, **kwargs)
