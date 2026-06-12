"""
Integration-config services — Admin-only, audited. These manage the NON-secret
config + the ``secret_ref`` (an env-var NAME); the actual token is NEVER accepted,
stored, or returned here (see ``secrets.py`` + ``NEEDS_HARI_secrets.md``).
"""
from __future__ import annotations

from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.tenancy.context import tenant_context

from .models import TenantIntegration


def list_integrations(actor) -> list[TenantIntegration]:
    with tenant_context(actor.tenant_id):
        return list(TenantIntegration.objects.all())


def get_integration(actor, kind) -> TenantIntegration | None:
    with tenant_context(actor.tenant_id):
        return TenantIntegration.objects.filter(kind=kind).first()


def upsert_integration(actor, kind, *, enabled, config, secret_ref="") -> TenantIntegration:
    """Create/update the tenant's ``kind`` integration (Admin-only at the view).
    Audited before the write. Rejects an unknown kind / non-object config (422)."""
    if kind not in TenantIntegration.Kind.values:
        raise ValidationError({"kind": f"Unknown integration kind '{kind}'."})
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValidationError({"config": "config must be a JSON object."})
    tid = actor.tenant_id
    with tenant_context(tid):
        record(
            action="integration.configured",
            actor=actor,
            target_type="tenant_integration",
            target_id="",
            metadata={"kind": kind, "enabled": bool(enabled), "config_keys": sorted(config.keys())},
            tenant=tid,
        )
        integration, _created = TenantIntegration.objects.update_or_create(
            tenant_id=tid,
            kind=kind,
            defaults={"enabled": bool(enabled), "config": config, "secret_ref": secret_ref or ""},
        )
        return integration
