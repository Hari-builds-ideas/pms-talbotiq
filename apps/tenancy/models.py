"""
Tenancy core models.

* ``Tenant`` — the tenant row itself (NOT tenant-scoped; it IS the scope).
* ``TenantScopedModel`` — abstract base every domain model inherits: UUID pk,
  tenant FK, created/updated timestamps, soft delete, and a default manager
  that enforces tenant isolation. ``save()`` enforces write-side isolation:
  you can only write into the tenant that is currently bound.
"""
import uuid

from django.db import models
from django.utils import timezone

from .context import get_current_tenant_id
from .managers import TenantScopedManager


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Tenant is the scope boundary itself, so it uses a plain manager.
    objects = models.Manager()

    class Meta:
        db_table = "tenant"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @property
    def is_active_tenant(self):
        return self.status == self.Status.ACTIVE


class TenantScopedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    # Default manager: tenant-scoped, hides soft-deleted rows, fails closed.
    objects = TenantScopedManager()
    # Tenant-scoped but includes soft-deleted rows (still never cross-tenant).
    all_objects = TenantScopedManager(include_deleted=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        current = get_current_tenant_id()
        if current is not None:
            if self.tenant_id is None:
                # Stamp the bound tenant automatically.
                self.tenant_id = current
            elif str(self.tenant_id) != str(current):
                # Cross-tenant write attempt — block it.
                raise PermissionError(
                    "Cross-tenant write blocked: object tenant "
                    f"{self.tenant_id} does not match the active tenant {current}."
                )
        else:
            if self.tenant_id is None:
                # Fail closed on writes too: no context and no explicit tenant.
                raise ValueError(
                    "Cannot save a tenant-scoped object without a tenant: no "
                    "active tenant context and tenant is unset."
                )
            # No context but an explicit tenant -> system/provisioning path.
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False, hard=False):
        """Soft delete by default (stamp ``deleted_at``); ``hard=True`` removes
        the row and is reserved for system use."""
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.deleted_at = timezone.now()
        super().save(update_fields=["deleted_at", "updated_at"])
        return (1, {self._meta.label: 1})
