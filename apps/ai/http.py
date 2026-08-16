"""
Honest HTTP responses for an unavailable AI feature (B3).

The gateway already distinguishes why a call did not happen — switched off, no
provider, over budget, provider failed — and then every view flattened that back
into "AI unavailable". A person who sees that has no idea whether to call their
admin, wait until next month, or try again in a minute.

These helpers keep the distinction all the way to the client, as a machine-
readable ``code`` plus a sentence written for the person reading it.

The codes are the contract the SPA renders from:

    ai_disabled          your admin switched AI off for this organisation
    ai_not_configured    no provider key is set for this deployment/tenant
    ai_budget_exhausted  the AI budget for this period is used up
    ai_provider_error    the provider rejected the request or is unreachable
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response

AI_DISABLED = "ai_disabled"
AI_NOT_CONFIGURED = "ai_not_configured"
AI_BUDGET_EXHAUSTED = "ai_budget_exhausted"
AI_PROVIDER_ERROR = "ai_provider_error"

_DETAIL = {
    AI_DISABLED: (
        "AI features are switched off for this organisation. An administrator can "
        "turn them back on in Administration → AI."
    ),
    AI_NOT_CONFIGURED: (
        "AI features are not set up yet. An administrator needs to add a model "
        "provider key in Administration → AI."
    ),
    AI_BUDGET_EXHAUSTED: (
        "The AI budget for this period is used up. It resets automatically, or an "
        "administrator can raise the limit."
    ),
    AI_PROVIDER_ERROR: (
        "The AI provider could not be reached just now. Nothing was changed — try "
        "again in a moment."
    ),
}

#: 503 for "cannot serve", 429 for "served too much". A budget exhaustion is not a
#: fault, and returning 503 for it would tell a monitoring system the service is
#: broken when it is behaving exactly as configured.
_STATUS = {
    AI_DISABLED: status.HTTP_503_SERVICE_UNAVAILABLE,
    AI_NOT_CONFIGURED: status.HTTP_503_SERVICE_UNAVAILABLE,
    AI_BUDGET_EXHAUSTED: status.HTTP_429_TOO_MANY_REQUESTS,
    AI_PROVIDER_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def unavailable_code(tenant, *, gateway_status: str = "NOT_CONFIGURED") -> str:
    """Which of the four states applies.

    ``NOT_CONFIGURED`` covers two very different situations — the tenant switched
    AI off, or nobody ever set a key. The gateway carries the difference in its
    ``errors`` list, but that gets flattened as results pass through the agents.
    Rather than thread it through every call site, ask the switch: it is one cheap
    read and it is the authority on the question.
    """
    if gateway_status == "BUDGET_EXCEEDED":
        return AI_BUDGET_EXHAUSTED
    if gateway_status in ("PROVIDER_ERROR", "SCHEMA_INVALID"):
        return AI_PROVIDER_ERROR

    from .tenant_switch import ai_enabled_for

    return AI_NOT_CONFIGURED if ai_enabled_for(tenant) else AI_DISABLED


def unavailable_response(tenant, *, gateway_status="NOT_CONFIGURED", errors=None):
    """The response body every AI surface should return when it cannot serve."""
    code = unavailable_code(tenant, gateway_status=gateway_status)
    body = {"detail": _DETAIL[code], "code": code}
    if errors:
        # The gateway's own words (e.g. which budget was hit), kept alongside the
        # human sentence rather than replacing it.
        body["errors"] = list(errors)
    return Response(body, status=_STATUS[code])
