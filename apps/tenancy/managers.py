"""
Tenant-scoping queryset + manager.

Every tenant-scoped model's default manager auto-filters by the current-tenant
contextvar AND hides soft-deleted rows. With no tenant bound the manager
**fails closed** — it returns an empty queryset, never the whole table.

``all_tenants()`` is the single escape hatch, reserved for system/migration
code and forbidden on any request path.
"""
from django.db import models
from django.utils import timezone

from .context import get_current_tenant_id, is_request_active


class TenantScopedQuerySet(models.QuerySet):
    def delete(self):
        """Soft delete: stamp ``deleted_at`` instead of removing rows."""
        return super().update(deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently remove rows. System use only."""
        return super().delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class TenantScopedManager(models.Manager):
    """Default manager for tenant-scoped models.

    ``include_deleted=True`` builds a variant (``all_objects``) that still scopes
    by tenant but does not hide soft-deleted rows.
    """

    def __init__(self, *args, include_deleted=False, **kwargs):
        self._include_deleted = include_deleted
        super().__init__(*args, **kwargs)

    def _base_qs(self):
        return TenantScopedQuerySet(self.model, using=self._db)

    def get_queryset(self):
        qs = self._base_qs()
        if not self._include_deleted:
            qs = qs.filter(deleted_at__isnull=True)
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            # Fail closed: no tenant bound -> no rows (never the whole table).
            return qs.none()
        return qs.filter(tenant_id=tenant_id)

    def with_deleted(self):
        """Current-tenant rows including soft-deleted ones. Fails closed."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return self._base_qs().none()
        return self._base_qs().filter(tenant_id=tenant_id)

    def all_tenants(self):
        """Cross-tenant, includes soft-deleted. SYSTEM/MIGRATION ONLY.

        Raises on any API/request path so it can never be used to bypass
        tenant isolation from a view.
        """
        if is_request_active():
            raise RuntimeError(
                "all_tenants() is not permitted on an API/request path; it is "
                "reserved for system and migration code."
            )
        return self._base_qs()
