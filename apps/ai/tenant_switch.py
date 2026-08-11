"""The tenant's own AI on/off switch.

Separate from the entitlement, which answers a different question. The plan says
what a tenant MAY use; this says what they WANT enabled. An organisation with a
policy against sending employee data to a model provider needs to turn AI off
without downgrading their plan, and a customer asking "can we switch the AI off?"
during procurement needs the answer to be yes.

Stored in ``TenantConfig.settings`` — the existing schemaless, Admin-managed,
audited, optimistically-locked bag — so this needs no migration and inherits the
audit trail the admin endpoint already writes.

**Default ON.** An absent key means enabled: every existing tenant keeps working,
and a tenant is never silently deprived of a feature they are paying for by a
config row that has not been written yet.
"""
from __future__ import annotations

#: The key inside ``TenantConfig.settings``.
AI_ENABLED_KEY = "ai_enabled"


def ai_enabled_for(tenant) -> bool:
    """Is AI switched on for ``tenant``?

    Fails OPEN (returns True) when the config cannot be read. The switch is a
    customer preference, not a security control — the security controls are the
    entitlement gate, RBAC and tenant scoping, all of which are enforced elsewhere
    and independently. Failing closed here would turn a transient database hiccup
    into "the AI stopped working" across every tenant at once, which is a worse
    outcome than a preference briefly not applying.
    """
    if tenant is None:
        return True
    tenant_id = getattr(tenant, "id", tenant)
    try:
        from apps.administration.models import TenantConfig
        from apps.tenancy.context import tenant_context

        with tenant_context(tenant_id):
            config = TenantConfig.objects.filter(tenant_id=tenant_id).first()
    except Exception:  # noqa: BLE001 — see the fail-open note above
        return True
    if config is None:
        return True
    return bool((config.settings or {}).get(AI_ENABLED_KEY, True))
