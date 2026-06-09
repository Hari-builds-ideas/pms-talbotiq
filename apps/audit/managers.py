"""
Append-only, tenant-scoped manager for ``AuditLog``.

Reads are scoped to the current-tenant contextvar and **fail closed** — with no
tenant bound the manager returns an empty queryset, never the whole table. Bulk
mutation (``update``) and bulk removal (``delete``) are forbidden at the
queryset level; only INSERTs are allowed (via ``create()``/``save()``, which
stamp the tenant). ``all_tenants()`` is the single cross-tenant escape, reserved
for system/migration code and forbidden on any request path.
"""
from django.db import models

from apps.tenancy.context import get_current_tenant_id, is_request_active

from .exceptions import AuditLogImmutableError


class AuditLogQuerySet(models.QuerySet):
    def update(self, *args, **kwargs):
        raise AuditLogImmutableError("audit_log is append-only: update() is forbidden.")

    def delete(self):
        raise AuditLogImmutableError("audit_log is append-only: delete() is forbidden.")


class AuditLogManager(models.Manager):
    def _base_qs(self):
        return AuditLogQuerySet(self.model, using=self._db)

    def get_queryset(self):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            # Fail closed: no tenant bound -> no rows (never the whole table).
            return self._base_qs().none()
        return self._base_qs().filter(tenant_id=tenant_id)

    def all_tenants(self):
        """Cross-tenant read. SYSTEM/MIGRATION ONLY.

        Raises on any API/request path so it can never be used to bypass tenant
        isolation from a view.
        """
        if is_request_active():
            raise RuntimeError(
                "all_tenants() is not permitted on an API/request path; it is "
                "reserved for system and migration code."
            )
        return self._base_qs()
