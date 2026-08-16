"""The tenant's own AI on/off switch.

Separate from the entitlement, which answers a different question. The plan says
what a tenant MAY use; this says what they WANT enabled. An organisation with a
policy against sending employee data to a model provider needs to turn AI off
without downgrading their plan, and a customer asking "can we switch the AI off?"
during procurement needs the answer to be yes.

Stored on ``ai.TenantAIConfig.enabled`` (B1), with a fallback read of the legacy
``TenantConfig.settings["ai_enabled"]`` so tenants that set it before B1 keep the
answer they chose without a data migration.

**Default ON.** An absent setting means enabled: every existing tenant keeps
working, and a tenant is never silently deprived of a feature they are paying for
by a config row that has not been written yet.

**Fails CLOSED (B4).** If the switch cannot be read, AI is treated as OFF.

That inverts the original behaviour, and the reasoning that produced the original
was wrong. It argued this is a preference rather than a security control, so a
database hiccup should not stop AI working. But we tell customers this switch is
how they stop employee performance data leaving for a model provider. Once that
is the promise, "we could not read your preference, so we sent the data anyway"
is the one outcome that is never acceptable — a transient failure that silently
re-enables the thing a customer switched off is worse than a transient failure
that makes AI unavailable and says so. The caller renders "AI is switched off for
this organisation", which is honest and recoverable; the alternative is not.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("pms.ai.switch")

#: The key inside the legacy ``TenantConfig.settings`` bag (pre-B1).
AI_ENABLED_KEY = "ai_enabled"


def ai_enabled_for(tenant) -> bool:
    """Is AI switched on for ``tenant``?

    Returns False when the setting cannot be read — see the module docstring for
    why this fails closed rather than open.
    """
    if tenant is None:
        # No tenant to consult. Every real call path binds one; a None here means
        # a system/system-test path, and refusing is the safe reading.
        return False

    tenant_id = getattr(tenant, "id", tenant)
    try:
        from apps.tenancy.context import tenant_context

        from .models import TenantAIConfig

        with tenant_context(tenant_id):
            cfg = TenantAIConfig.objects.filter(tenant_id=tenant_id).first()
            if cfg is not None:
                return bool(cfg.enabled)

            # No B1 row yet: honour a pre-B1 choice if one was recorded.
            from apps.administration.models import TenantConfig

            legacy = TenantConfig.objects.filter(tenant_id=tenant_id).first()
            if legacy is not None:
                return bool((legacy.settings or {}).get(AI_ENABLED_KEY, True))

        # Neither row exists — a tenant that has never touched the setting. On by
        # default, per the docstring: absent is not the same as switched off.
        return True
    except Exception:  # noqa: BLE001 — see the fail-closed note above
        logger.exception(
            "Could not read the AI switch for tenant=%s; treating AI as OFF.",
            tenant_id,
        )
        return False


def set_ai_enabled(tenant, enabled: bool):
    """Flip the switch. Returns the config row."""
    from .tenant_config import get_config

    cfg = get_config(tenant)
    if cfg is None:
        return None
    cfg.enabled = bool(enabled)
    cfg.save(update_fields=["enabled", "updated_at"])
    return cfg
