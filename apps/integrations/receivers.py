"""
Signal receivers — the ONE-WAY bridge from the core apps' notification signals
(Module 4 feedback, Module 5 approvals) to the best-effort Slack notifier. The
core apps never import integrations; integrations subscribes here (the same
decoupling Module 2 used for the Agent-2 nudge seam).

Every notify_* call is already best-effort (it swallows failures), and the signals
are emitted with ``send_robust``, so a Slack problem can never break the action.
"""
from __future__ import annotations

from .notifications import (
    notify_approval_assignment,
    notify_approval_escalation,
    notify_feedback_request,
)


def on_feedback_request_sent(sender, **kwargs):
    notify_feedback_request(
        kwargs.get("tenant_id"), relationship=kwargs.get("relationship")
    )


def on_approval_step_assigned(sender, **kwargs):
    notify_approval_assignment(
        kwargs.get("tenant_id"),
        route_id=kwargs.get("route_id"),
        order=kwargs.get("order"),
        artifact_type=kwargs.get("artifact_type"),
    )


def on_approval_step_escalated(sender, **kwargs):
    notify_approval_escalation(
        kwargs.get("tenant_id"),
        route_id=kwargs.get("route_id"),
        order=kwargs.get("order"),
    )
