"""
Administration (Admin Hub) — Admin-only tenant configuration.

The Admin Hub backend operates mostly on EXISTING models (``identity.User`` for
user/role management, ``tenancy.Tenant`` for the tenant itself, and the Module-7
``org.reassign`` for the reporting line — reused, never duplicated). The single new
model here is per-tenant configuration.
"""
from django.db import models

from apps.tenancy.models import TenantScopedModel


class TenantConfig(TenantScopedModel):
    """Per-tenant configuration / settings, Admin-managed (one row per tenant).

    ``settings`` is a free-form JSON bag for tenant-level preferences (display name
    overrides, locale, feature toggles that are NOT entitlements, etc.). Kept
    deliberately schemaless for the MVP; structured fields can graduate out of it
    later without a data migration of the values themselves."""

    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "administration_tenant_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uq_tenantconfig_tenant"),
        ]

    def __str__(self):
        return f"TenantConfig(tenant={self.tenant_id})"
