"""
Billing exceptions.

``BudgetExceeded`` is raised by ``check_and_reserve_budget`` when a tenant has
spent its per-window agent-call budget. It is a 429 (the same status family as the
rate-limit throttle) and carries an ``upgrade_hint`` so the surface can prompt the
tenant to upgrade rather than just failing opaquely.
"""
from __future__ import annotations

from rest_framework.exceptions import APIException


class BudgetExceeded(APIException):
    """429: the tenant's agent-call budget for this window is exhausted."""

    status_code = 429
    default_code = "budget_exceeded"

    def __init__(self, *, agent_code, window, limit, upgrade_hint=True):
        detail = {
            "detail": (
                f"Agent-call budget exhausted for '{agent_code}' "
                f"({window.lower()} limit {limit})."
            ),
            "code": "BUDGET_EXCEEDED",
            "agent_code": agent_code,
            "window": window,
            "limit": limit,
        }
        if upgrade_hint:
            detail["upgrade_hint"] = (
                "Upgrade to FULL_AI for higher agent-call budgets, or raise this "
                "tenant's AgentBudget."
            )
        super().__init__(detail)
