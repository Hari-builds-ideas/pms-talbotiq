"""
Admin Hub — AI provider configuration (B2).

Mounted under ``/api/ai/admin/``. Every endpoint is gated on
``MANAGE_TENANT_CONFIG`` (Admin only), the same capability that already guards
tenant settings, so this introduces no new authority.

What these endpoints will never do: return the stored API key. Reads answer
"is one installed, and which one" via a last-4 hint. There is no endpoint that
reveals a key, because there is no use for one that outweighs the risk of having
written it.

Every key set, rotation and clear is written to the audit log — the ACTION and
the ACTOR, never the value.
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from .crypto import EncryptionUnavailable
from .tenant_config import (
    PROVIDER_PATHS,
    clear_api_key,
    get_config,
    public_state,
    resolve_provider,
    set_api_key,
)
from .tenant_switch import set_ai_enabled

logger = logging.getLogger("pms.ai.admin")


class AIConfigView(RBACMixin, APIView):
    """``GET, PATCH /api/ai/admin/config`` — the tenant's AI configuration.

    GET returns the safe view (see ``public_state``): whether AI is on, which
    provider, whether a key is installed and its last four characters, and
    whether this deployment can store a key at all.

    PATCH accepts any of ``enabled``, ``provider``, ``model_overrides``,
    ``api_key`` (set/rotate) and ``clear_api_key``. It is a PATCH rather than a
    PUT precisely so that toggling AI off cannot silently drop the stored key.
    """

    required_capability = Capability.MANAGE_TENANT_CONFIG

    def get(self, request):
        return Response(public_state(request.user.tenant))

    def patch(self, request):
        tenant = request.user.tenant
        data = request.data or {}
        changed: list[str] = []

        # ── the on/off switch ──
        if "enabled" in data:
            enabled = bool(data["enabled"])
            set_ai_enabled(tenant, enabled)
            changed.append("enabled")
            audit.record(
                action="ai.config.switch",
                actor=request.user,
                target_type="TenantAIConfig",
                target_id=str(tenant.id),
                metadata={"enabled": enabled},
            )

        # ── provider choice ──
        if "provider" in data:
            provider = (data.get("provider") or "").strip().lower()
            if provider and provider not in PROVIDER_PATHS:
                return Response(
                    {
                        "detail": "Unknown provider.",
                        "code": "unknown_provider",
                        "allowed": sorted(PROVIDER_PATHS),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cfg = get_config(tenant)
            cfg.provider = provider
            cfg.save(update_fields=["provider", "updated_at"])
            changed.append("provider")
            audit.record(
                action="ai.config.provider",
                actor=request.user,
                target_type="TenantAIConfig",
                target_id=str(tenant.id),
                metadata={"provider": provider or "inherit"},
            )

        # ── model overrides ──
        if "model_overrides" in data:
            overrides = data.get("model_overrides") or {}
            if not isinstance(overrides, dict):
                return Response(
                    {"detail": "model_overrides must be an object.",
                     "code": "invalid_model_overrides"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cfg = get_config(tenant)
            cfg.model_overrides = overrides
            cfg.save(update_fields=["model_overrides", "updated_at"])
            changed.append("model_overrides")
            audit.record(
                action="ai.config.models",
                actor=request.user,
                target_type="TenantAIConfig",
                target_id=str(tenant.id),
                metadata={"keys": sorted(overrides)},
            )

        # ── the key: set/rotate, or clear ──
        if data.get("clear_api_key"):
            clear_api_key(tenant, actor=request.user)
            changed.append("api_key")
            audit.record(
                action="ai.key.cleared",
                actor=request.user,
                target_type="TenantAIConfig",
                target_id=str(tenant.id),
            )
        elif data.get("api_key"):
            raw = str(data["api_key"]).strip()
            had_key = bool(getattr(get_config(tenant), "api_key_encrypted", ""))
            try:
                cfg = set_api_key(tenant, raw_key=raw, actor=request.user)
            except EncryptionUnavailable as exc:
                # 409, not 500: the deployment is missing a variable, and the
                # admin can be told exactly which one. Nothing was stored.
                return Response(
                    {"detail": str(exc), "code": "encryption_unavailable"},
                    status=status.HTTP_409_CONFLICT,
                )
            except ValueError as exc:
                return Response(
                    {"detail": str(exc), "code": "invalid_api_key"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            changed.append("api_key")
            # The ACTION and the ACTOR — never the value. The last-4 is recorded
            # so an auditor can correlate "which key was installed on the 3rd?"
            # without the key itself ever being written anywhere.
            audit.record(
                action="ai.key.rotated" if had_key else "ai.key.set",
                actor=request.user,
                target_type="TenantAIConfig",
                target_id=str(tenant.id),
                metadata={"key_last4": cfg.key_last4},
            )

        body = public_state(tenant)
        body["changed"] = changed
        return Response(body)


class AITestConnectionView(RBACMixin, APIView):
    """``POST /api/ai/admin/test-connection`` — one minimal call, honest result.

    Reports what actually happened rather than a boolean: not configured, the
    tenant's AI switch is off, the provider rejected the credentials, or it
    worked. The point of this button is to turn "the AI isn't working" into a
    specific sentence an admin can act on.

    Exactly ONE provider call, with a tiny prompt. It goes through the normal
    gateway so the tenant's budget, the deployment ceiling and the PII scrubber
    all apply — a test that bypasses those would be testing a path that does not
    exist in production.
    """

    required_capability = Capability.MANAGE_TENANT_CONFIG

    def post(self, request):
        tenant = request.user.tenant
        dotted, _key, source = resolve_provider(tenant)

        if source == "unconfigured":
            return Response(
                {
                    "ok": False,
                    "state": "not_configured",
                    "detail": (
                        "No AI provider is configured. Add an API key here, or set "
                        "one for the whole deployment."
                    ),
                }
            )

        from .gateway import AI_DISABLED_DETAIL, gateway

        result = gateway.run(
            tenant=tenant,
            agent_code="connection_test",
            prompt='Reply with {"ok": true} and nothing else.',
            model="default",
        )

        audit.record(
            action="ai.connection.tested",
            actor=request.user,
            target_type="TenantAIConfig",
            target_id=str(tenant.id),
            metadata={"status": result.status, "key_source": source},
        )

        if result.ok:
            return Response({
                "ok": True,
                "state": "ok",
                "provider": dotted.rsplit(".", 1)[-1],
                "model": result.model,
                "key_source": source,
                "detail": "The provider answered.",
            })

        # Map the gateway's own statuses to something a person can act on, rather
        # than collapsing every failure into "error" (B3's principle, applied
        # here first because this endpoint exists to explain failures).
        state_detail = {
            "NOT_CONFIGURED": (
                "ai_disabled"
                if AI_DISABLED_DETAIL in (result.errors or [])
                else "not_configured",
                AI_DISABLED_DETAIL
                if AI_DISABLED_DETAIL in (result.errors or [])
                else "No AI provider is configured.",
            ),
            "BUDGET_EXCEEDED": (
                "budget_exceeded",
                "The AI budget for this period is used up. "
                + " ".join(result.errors or []),
            ),
            "SCHEMA_INVALID": (
                "provider_error",
                "The provider answered, but not in the expected shape.",
            ),
            "PROVIDER_ERROR": (
                "provider_error",
                "The provider rejected the request or could not be reached. "
                "Check the key is valid and has quota.",
            ),
        }
        state, detail = state_detail.get(
            result.status, ("provider_error", "The provider call did not succeed.")
        )
        return Response({
            "ok": False,
            "state": state,
            "key_source": source,
            "detail": detail.strip(),
        })
