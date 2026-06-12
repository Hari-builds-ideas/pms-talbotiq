"""
AI surfaces. Currently the Chat Assistant — the only USER-facing AI endpoint
(the other agents fill existing module seams). READ-ONLY + RBAC-bound: it returns
only what the caller could already see (the routing uses the caller's identity +
scoped services), and write/approval intents are blocked. Gated by ``USE_CHAT``
(everyone) + ``requires_entitlement("chat")`` (STARTER); the per-tenant chat budget
is enforced by the gateway (over budget → 429).
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.agents.chat import chat_answer
from apps.billing.gate import requires_entitlement
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin


class ChatView(RBACMixin, APIView):
    """``POST /api/ai/chat`` — body ``{"query": str}``. Maps the read-only,
    RBAC-bound answer to HTTP: 200 (ok / blocked-write), 503 (no LLM provider),
    429 (chat budget exhausted)."""

    required_capability = Capability.USE_CHAT

    def get_permissions(self):
        perms = super().get_permissions()  # IsAuthenticated + HasCapability(USE_CHAT)
        perms.append(requires_entitlement("chat")())  # tenant must hold the chat feature
        return perms

    def post(self, request):
        query = (request.data.get("query") or "").strip()
        if not query:
            return Response({"detail": "query is required."}, status=status.HTTP_400_BAD_REQUEST)
        result = chat_answer(request.user, query)
        if result["status"] == "not_configured":
            return Response(
                {"detail": "The Chat Assistant is not configured (LLM provider unset; "
                           "lands with the Module-10 provider activation)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if result["status"] == "budget":
            return Response(
                {"detail": "Chat budget exhausted for this window.", "errors": result.get("errors")},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if result["status"] == "error":
            return Response({"detail": f"chat unavailable: {result.get('detail')}"},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        # ok / blocked-write → 200 (a blocked write is a valid, informative answer).
        return Response(result)
