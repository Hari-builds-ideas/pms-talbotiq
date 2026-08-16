"""
Per-tenant AI configuration: read, write, and resolution (B1).

The one place that knows how a tenant's provider choice and API key are stored,
decrypted and turned into an answer for the gateway. Everything else — the admin
endpoints, the gateway, the switch — goes through here, so the rules about what
may leave this module (never the key) live in one file.

Resolution order, per B1: **tenant key → environment key → not configured.**
"""
from __future__ import annotations

import logging

from django.conf import settings as dj_settings
from django.utils import timezone

from .crypto import EncryptionUnavailable, decrypt, encrypt, last4

logger = logging.getLogger("pms.ai.config")

#: Provider slug → the dotted path the gateway imports. An admin chooses a SLUG,
#: never a dotted path, so a stored value cannot name an arbitrary importable
#: class (which would be a remote-code-execution shaped hole in a settings form).
PROVIDER_PATHS: dict[str, str] = {
    "gemini": "apps.ai.gemini_provider.GeminiProvider",
    "openai": "apps.ai.openai_provider.OpenAIProvider",
    "groq": "apps.ai.groq.GroqProvider",
}


def get_config(tenant):
    """The tenant's AI config row, created empty on first access.

    Returns None if it cannot be read at all (no tenant bound, table missing
    mid-migration). Callers treat None as "no tenant-level configuration", never
    as an error.
    """
    from .models import TenantAIConfig

    tenant_id = getattr(tenant, "id", tenant)
    if tenant_id is None:
        return None
    try:
        obj, _ = TenantAIConfig.objects.get_or_create(tenant_id=tenant_id)
        return obj
    except Exception:  # noqa: BLE001 — see docstring; never break an AI request
        logger.exception("Could not load TenantAIConfig for tenant=%s", tenant_id)
        return None


def set_api_key(tenant, *, raw_key: str, actor=None) -> "object":
    """Store (or rotate) the tenant's provider key, encrypted.

    Raises :class:`EncryptionUnavailable` when ``FIELD_ENCRYPTION_KEY`` is unset —
    the caller turns that into an explicit 409 telling the admin what to set.
    Nothing is written in that case; a plaintext fallback is not on the table.
    """
    raw_key = (raw_key or "").strip()
    if not raw_key:
        raise ValueError("An API key is required.")
    cfg = get_config(tenant)
    if cfg is None:
        raise ValueError("No tenant configuration available.")
    # encrypt() raises EncryptionUnavailable before anything is persisted.
    cfg.api_key_encrypted = encrypt(raw_key)
    cfg.key_last4 = last4(raw_key)
    cfg.key_set_at = timezone.now()
    cfg.key_set_by = actor
    cfg.save(update_fields=[
        "api_key_encrypted", "key_last4", "key_set_at", "key_set_by", "updated_at",
    ])
    return cfg


def clear_api_key(tenant, *, actor=None):
    """Remove the tenant's key so it falls back to the environment key."""
    cfg = get_config(tenant)
    if cfg is None:
        return None
    cfg.api_key_encrypted = ""
    cfg.key_last4 = ""
    cfg.key_set_at = None
    cfg.key_set_by = actor
    cfg.save(update_fields=[
        "api_key_encrypted", "key_last4", "key_set_at", "key_set_by", "updated_at",
    ])
    return cfg


def resolve_provider(tenant) -> tuple[str, str | None, str]:
    """Decide which provider serves ``tenant``, and with which key.

    Returns ``(dotted_path, api_key_or_None, source)`` where source is one of
    ``"tenant"``, ``"environment"`` or ``"unconfigured"``.

    A tenant row that names a provider but whose key cannot be decrypted (rotated
    away, tampered with) is treated as having NO key and falls through to the
    environment — degrading to the deployment default beats failing every request.
    """
    cfg = get_config(tenant)
    if cfg is not None and cfg.api_key_encrypted:
        key = decrypt(cfg.api_key_encrypted)
        if key:
            dotted = PROVIDER_PATHS.get(cfg.provider or "")
            if dotted:
                return dotted, key, "tenant"
            # Key set but no provider chosen: use the deployment's provider class
            # with the tenant's key, which is the sane reading of "our own key".
            return getattr(dj_settings, "LLM_PROVIDER", ""), key, "tenant"

    env_dotted = getattr(dj_settings, "LLM_PROVIDER", "") or ""
    if env_dotted and not env_dotted.endswith("NotConfiguredProvider"):
        return env_dotted, None, "environment"
    return "apps.ai.providers.NotConfiguredProvider", None, "unconfigured"


def public_state(tenant) -> dict:
    """What the admin API is allowed to say about a tenant's AI configuration.

    Note what is NOT here: the key. Only whether one is installed, its last four
    characters, and who set it when. The decrypted value never leaves this module.
    """
    from .crypto import encryption_available

    cfg = get_config(tenant)
    dotted, key, source = resolve_provider(tenant)
    return {
        "enabled": bool(getattr(cfg, "enabled", True)),
        "provider": getattr(cfg, "provider", "") or "",
        "model_overrides": getattr(cfg, "model_overrides", {}) or {},
        # `configured` answers the only question a UI actually needs: will an AI
        # request work right now, from any source?
        "configured": source != "unconfigured",
        "key_source": source,
        "tenant_key_set": bool(getattr(cfg, "api_key_encrypted", "")),
        "key_hint": f"••••{cfg.key_last4}" if getattr(cfg, "key_last4", "") else "",
        "key_set_at": getattr(cfg, "key_set_at", None),
        # So the UI can explain "you must set FIELD_ENCRYPTION_KEY before you can
        # store a key here" instead of showing a form that will always fail.
        "encryption_available": encryption_available(),
        "available_providers": sorted(PROVIDER_PATHS),
    }


__all__ = [
    "PROVIDER_PATHS",
    "EncryptionUnavailable",
    "clear_api_key",
    "get_config",
    "public_state",
    "resolve_provider",
    "set_api_key",
]
