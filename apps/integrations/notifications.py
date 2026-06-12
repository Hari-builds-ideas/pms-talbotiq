"""
Slack notifications — BEST-EFFORT delivery. A Slack failure must NEVER break the
action that triggered it (an approval still completes, a feedback request is still
created): every send is wrapped, logged, and swallowed. An unconfigured/disabled
tenant (or an unset webhook secret) is a clean, logged no-op.

These functions bind the tenant themselves, so they are safe to call from a signal
receiver / Celery task off the request path. Secrets are NEVER logged.
"""
from __future__ import annotations

import logging

from apps.tenancy.context import tenant_context

from .clients import get_slack_client
from .models import TenantIntegration

logger = logging.getLogger("pms.integrations.slack")


def _send(tenant_id, text) -> bool:
    """Send ``text`` to the tenant's Slack channel. Returns True iff a send was
    attempted-and-succeeded; False on any no-op/failure. NEVER raises."""
    try:
        with tenant_context(tenant_id):
            integration = TenantIntegration.objects.filter(
                kind=TenantIntegration.Kind.SLACK, enabled=True
            ).first()
            if integration is None:
                logger.info(
                    "Slack notify no-op for tenant=%s: no enabled Slack integration.",
                    tenant_id,
                )
                return False
            channel = (integration.config or {}).get("channel")
            client = get_slack_client(integration)
            client.post(channel, text)
            return True
    except Exception:  # noqa: BLE001 — best-effort: a Slack failure never breaks the action
        logger.warning(
            "Slack notify failed for tenant=%s (best-effort; the triggering action "
            "is unaffected).",
            tenant_id,
            exc_info=True,
        )
        return False


def notify_approval_assignment(tenant_id, *, route_id, order, artifact_type) -> bool:
    return _send(
        tenant_id,
        f"📋 Approval needed: step {order} of the {artifact_type} approval route "
        f"{route_id} is now assigned to you.",
    )


def notify_approval_escalation(tenant_id, *, route_id, order) -> bool:
    return _send(
        tenant_id,
        f"⏰ Approval escalated: step {order} of route {route_id} was overdue and "
        f"has been reassigned.",
    )


def notify_feedback_request(tenant_id, *, relationship) -> bool:
    return _send(
        tenant_id,
        f"📝 Feedback requested: you have been invited to give {relationship} "
        f"feedback. Please complete it before the cycle closes.",
    )


def notify_kpi_nudge(tenant_id, *, message) -> bool:
    """Deliver an Agent-2 KPI nudge to Slack (Module 10 composes the message and
    calls this; it is a clean no-op until then / when Slack is unconfigured)."""
    return _send(tenant_id, f"📈 {message}")
