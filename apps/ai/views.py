"""
AI surfaces. Currently the Chat Assistant — the only USER-facing AI endpoint
(the other agents fill existing module seams). READ-ONLY + RBAC-bound: it returns
only what the caller could already see (the routing uses the caller's identity +
scoped services), and write/approval intents are blocked. Gated by ``USE_CHAT``
(everyone) + ``requires_entitlement("chat")`` (STARTER); the per-tenant chat budget
is enforced by the gateway (over budget → 429).
"""
from __future__ import annotations

import uuid

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.actions import execute_action
from apps.ai.agents.chat import chat_answer
from apps.ai.agents.kpi import team_nudges
from apps.ai.models import AIJob
from apps.ai.serializers import AIJobSerializer
from apps.billing.gate import requires_entitlement
from apps.core.throttling import AI_THROTTLES
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin


class ChatView(RBACMixin, APIView):
    """``POST /api/ai/chat`` — body ``{"query": str}``. Maps the read-only,
    RBAC-bound answer to HTTP: 200 (ok / blocked-write), 503 (no LLM provider),
    429 (chat budget exhausted)."""

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES  # the one synchronous LLM route — AI-throttled

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


class ChatActionExecuteView(RBACMixin, APIView):
    """``POST /api/ai/actions/execute`` — run a previously PROPOSED assistant action
    on an explicit human Approve. Body ``{"action": str, "params": {...}}``.

    Capability + data scope are RE-CHECKED inside ``execute_action`` on the real
    targets (the assistant can only ever do what the caller could do via the normal
    endpoint), and each effect is audited there. Gated by USE_CHAT + the chat
    entitlement, exactly like the chat surface; AI-throttled.
    """

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()  # IsAuthenticated + HasCapability(USE_CHAT)
        perms.append(requires_entitlement("chat")())
        return perms

    def post(self, request):
        action = (request.data.get("action") or "").strip()
        if not action:
            return Response({"detail": "action is required."}, status=status.HTTP_400_BAD_REQUEST)
        result = execute_action(request.user, action, request.data.get("params") or {})
        return Response(result)


class NudgesView(RBACMixin, APIView):
    """``GET /api/ai/nudges`` (VIEW_TEAM_SCORES — Manager+) — Agent 2's current KPI
    nudges for the caller's tier: a Manager sees their reporting subtree, HRBP/Admin
    the whole tenant. READ-ONLY (reuses ``team_nudges`` — no recompute). An Employee
    lacks VIEW_TEAM_SCORES → 403 (consistent with the team-scores surface).

    Returns a list of ``{employee, level, message}`` (level ∈ CRITICAL / STANDARD /
    SUPPRESSED); empty when no one is at risk.
    """

    required_capability = Capability.VIEW_TEAM_SCORES
    throttle_classes = AI_THROTTLES

    def get(self, request):
        return Response(team_nudges(request.user))


# ── async AI job status (BUILD_2) — the poll surface ──────────────────────────


class AIJobDetailView(APIView):
    """``GET /api/ai/jobs/<id>`` — the requester polls THEIR OWN AI job.

    Own- and tenant-scoped: ``AIJob.objects`` auto-filters the tenant (a
    cross-tenant id is invisible → 404) and we further scope to
    ``requested_by=request.user`` (another user's job → 404). No new capability —
    a user may only ever read a job they themselves enqueued. Authentication is
    the default ``IsAuthenticated``."""

    def get(self, request, pk):
        job = get_object_or_404(AIJob.objects.filter(requested_by=request.user), pk=pk)
        return Response(AIJobSerializer(job).data)


class AIJobListView(APIView):
    """``GET /api/ai/jobs?target=<id>`` — the caller's own recent AI jobs, newest
    first, optionally filtered to one artifact. Lets a screen find the live job
    for an artifact on load (so a refresh re-attaches to an in-flight run)."""

    def get(self, request):
        jobs = AIJob.objects.filter(requested_by=request.user)
        target = request.query_params.get("target")
        if target:
            # target_id is a UUIDField — a malformed (non-uuid) value would make
            # the ORM raise django ValidationError (a 500). It can't match any
            # artifact, so return an empty list instead of crashing.
            try:
                uuid.UUID(str(target))
            except (ValueError, TypeError, AttributeError):
                return Response([])
            jobs = jobs.filter(target_id=target)
        jobs = jobs.order_by("-created_at")[:20]
        return Response(AIJobSerializer(jobs, many=True).data)
