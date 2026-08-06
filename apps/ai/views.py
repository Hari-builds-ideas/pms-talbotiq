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
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
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
        # AGENT_UX_V3 §A — ONE send path: reads answer; writes return an inert PLAN.
        # Session-backed so multi-turn memory + references work from the single field.
        from apps.ai import sessions
        from apps.ai.models import ChatTurn

        query = (request.data.get("query") or "").strip()
        if not query:
            return Response({"detail": "query is required."}, status=status.HTTP_400_BAD_REQUEST)
        session = sessions.get_session(request.user, request.data.get("session_id"))
        sessions.append_turn(session, ChatTurn.Role.USER, query)
        result = chat_answer(request.user, query, session=session)
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
        if result["status"] == "plan":
            # A write → an ordered, INERT plan the human approves step by step.
            from apps.ai.planner import refs_for_plan
            from apps.ai.serializers import ChatPlanSerializer

            plan = result["plan"]
            sessions.append_turn(
                session, ChatTurn.Role.ASSISTANT, plan.summary,
                refs=refs_for_plan(plan), plan=plan,
            )
            return Response({
                "type": "plan", "status": "plan", "intent": "write",
                "session_id": str(session.id), "answer": plan.summary,
                "plan": ChatPlanSerializer(plan).data,
            })
        # ok / blocked-write / legacy-proposal → 200 (record the assistant turn).
        # C2: read answers ground the person they answered about (`refs`) so later
        # turns can resolve "she"/"her" — access is re-checked on every use.
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, result.get("answer", ""),
            refs=result.pop("refs", None),
        )
        # The agent's raw tool RESULTS are for the eval harness, not for the wire — they
        # are the same scoped rows the answer already states, at ten times the size.
        result.pop("evidence", None)
        return Response({**result, "session_id": str(session.id)})


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


class ChatActionsSchemaView(RBACMixin, APIView):
    """``GET /api/ai/actions/schema`` — public metadata for every supported assistant
    action (name, label, one-line description, feel, capability, and whether the
    CALLER may perform it). Powers the "what can the assistant do" surface and gives a
    place to enumerate the agent's capabilities. SENSITIVE actions the caller can't
    perform are omitted (no existence leak); no internals. Same gating as chat."""

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append(requires_entitlement("chat")())
        return perms

    def get(self, request):
        from apps.ai.actions import describe_actions

        return Response({"actions": describe_actions(request.user)})


class ChatPlanCreateView(RBACMixin, APIView):
    """``POST /api/ai/chat/plan`` — body ``{"query": str, "session_id"?: str}``.

    The AGENT surface (OVERNIGHT_A): plan a (possibly multi-step) request into an
    INERT :class:`~apps.ai.models.ChatPlan` the human approves step by step. Nothing
    executes here — the plan is data. Resumes/creates the caller's session, records
    the user + assistant turns (short-term memory), and returns the plan + session id.
    Same gating as chat (USE_CHAT + the chat entitlement); AI-throttled (one LLM call).
    """

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append(requires_entitlement("chat")())
        return perms

    def post(self, request):
        from apps.ai import sessions
        from apps.ai.models import ChatTurn
        from apps.ai.planner import build_plan, refs_for_plan
        from apps.ai.serializers import ChatPlanSerializer

        query = (request.data.get("query") or "").strip()
        if not query:
            return Response({"detail": "query is required."}, status=status.HTTP_400_BAD_REQUEST)

        session = sessions.get_session(request.user, request.data.get("session_id"))
        sessions.append_turn(session, ChatTurn.Role.USER, query)

        out = build_plan(request.user, session, query)
        if out["status"] == "not_configured":
            return Response(
                {"detail": "The assistant is not configured (no LLM provider)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if out["status"] == "budget":
            return Response(
                {"detail": "Assistant budget exhausted for this window.", "errors": out.get("errors")},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if out["status"] == "error":
            return Response({"detail": f"assistant unavailable: {out.get('detail')}"},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        plan = out["plan"]
        sessions.append_turn(
            session, ChatTurn.Role.ASSISTANT, plan.summary,
            refs=refs_for_plan(plan), plan=plan,
        )
        return Response({"session_id": str(session.id), "plan": ChatPlanSerializer(plan).data})


class ChatSessionListView(RBACMixin, APIView):
    """``GET /api/ai/chat/sessions`` — the caller's recent, non-expired chat sessions
    (the recent-chats picker). Owner + tenant scoped; never another user's."""

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append(requires_entitlement("chat")())
        return perms

    def get(self, request):
        from apps.ai.models import CHAT_SESSION_TTL_HOURS, ChatSession
        from apps.ai.serializers import ChatSessionSerializer

        cutoff = timezone.now() - timedelta(hours=CHAT_SESSION_TTL_HOURS)
        qs = ChatSession.objects.filter(owner=request.user, last_activity__gte=cutoff).order_by("-last_activity")[:25]
        return Response(ChatSessionSerializer(qs, many=True).data)


class ChatSessionDetailView(RBACMixin, APIView):
    """``GET /api/ai/chat/sessions/<id>`` — one of the caller's own sessions with its
    recent turns (the resume payload). 404 for a missing / expired / other-user /
    cross-tenant id (no existence leak)."""

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append(requires_entitlement("chat")())
        return perms

    def get(self, request, session_id):
        from apps.ai import sessions
        from apps.ai.serializers import ChatSessionDetailSerializer

        session = sessions.fetch_session_or_none(request.user, session_id)
        if session is None:
            return Response({"detail": "No such session."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ChatSessionDetailSerializer(session).data)


class ChatPlanStepApproveView(RBACMixin, APIView):
    """``POST /api/ai/chat/plan/<plan_id>/step/<step_id>/approve`` — approve and run
    EXACTLY ONE step of a plan. The ONLY write path from a plan; reached only on an
    explicit human Approve. ``approve_step`` re-checks capability + scope on the real
    targets (403/404) and is concurrency-safe + idempotent. Same gating as chat."""

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append(requires_entitlement("chat")())
        return perms

    def post(self, request, plan_id, step_id):
        from apps.ai.planner import approve_step

        return Response(approve_step(request.user, plan_id, step_id))


class MeetingSummaryView(RBACMixin, APIView):
    """``POST /api/ai/meeting-summary`` — body ``{"notes": str}``. Stateless AI
    summary of 1-on-1 / meeting notes → ``{summary, action_items}``. DRAFT only,
    persists nothing (RW_BUILD_5). USE_CHAT + the chat entitlement, AI-throttled;
    maps the gateway result to HTTP (200 / 503 no-provider / 429 over-budget)."""

    required_capability = Capability.USE_CHAT
    throttle_classes = AI_THROTTLES

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append(requires_entitlement("chat")())
        return perms

    def post(self, request):
        notes = (request.data.get("notes") or "").strip()
        if not notes:
            return Response({"detail": "notes is required."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.ai.agents.meeting_summary import summarize_meeting

        out = summarize_meeting(request.user, notes)
        if out["status"] == "not_configured":
            return Response(
                {"detail": "The AI summary is not configured (no LLM provider)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if out["status"] == "budget":
            return Response(
                {"detail": "AI budget exhausted for this window.", "errors": out.get("errors")},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if out["status"] == "error":
            return Response(
                {"detail": f"AI summary unavailable: {out.get('detail')}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(out)


class ReviewQualityView(RBACMixin, APIView):
    """``POST /api/ai/review-quality`` — body ``{"text": str}``. ASSISTIVE quality/bias
    flags on a draft review's text → ``{flags: [{type, note}]}`` (empty = clean). Never
    blocks, persists nothing (RW_BUILD_5). Gated by MANAGE_REVIEWS (reviewers, Manager+),
    AI-throttled; maps the gateway result to HTTP (200 / 503 / 429)."""

    required_capability = Capability.MANAGE_REVIEWS
    throttle_classes = AI_THROTTLES

    def post(self, request):
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "text is required."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.ai.agents.review_quality import flag_review_quality

        out = flag_review_quality(request.user, text)
        if out["status"] == "not_configured":
            return Response(
                {"detail": "The AI review check is not configured (no LLM provider)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if out["status"] == "budget":
            return Response(
                {"detail": "AI budget exhausted for this window.", "errors": out.get("errors")},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if out["status"] == "error":
            return Response(
                {"detail": f"AI review check unavailable: {out.get('detail')}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(out)


class StaleGoalsView(RBACMixin, APIView):
    """``GET /api/ai/stale-goals`` (VIEW_TEAM_SCORES — Manager+) — READ-ONLY: the
    caller's reporting-subtree ACTIVE goals with no KPI progress in ~30 days, plus ONE
    AI-drafted follow-up suggestion (RW_BUILD_5). Advisory — suggests, never nudges
    anyone automatically; persists nothing. The deterministic list always returns; the
    suggestion is null with no AI provider. AI-throttled (the LLM is called at most once)."""

    required_capability = Capability.VIEW_TEAM_SCORES
    throttle_classes = AI_THROTTLES

    def get(self, request):
        from apps.ai.agents.stale_goals import stale_goals_for, suggest_followup

        stale = stale_goals_for(request.user)
        suggestion = suggest_followup(request.user, stale)
        return Response({"stale": stale, "suggestion": suggestion})


class NLSearchView(RBACMixin, APIView):
    """``POST /api/ai/search`` (VIEW_TEAM_SCORES — Manager+) — body ``{"query": str}``.
    Natural-language search: the LLM classifies the question into a fixed SUPPORTED
    search, then a DETERMINISTIC, scope-bound query runs (returns only people the
    caller can see). Read-only; persists nothing (RW_BUILD_5). Maps the gateway result
    to HTTP (200 / 503 / 429); AI-throttled."""

    required_capability = Capability.VIEW_TEAM_SCORES
    throttle_classes = AI_THROTTLES

    def post(self, request):
        query = (request.data.get("query") or "").strip()
        if not query:
            return Response({"detail": "query is required."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.ai.agents.nl_search import nl_search

        out = nl_search(request.user, query)
        if out["status"] == "not_configured":
            return Response(
                {"detail": "AI search is not configured (no LLM provider)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if out["status"] == "budget":
            return Response(
                {"detail": "AI budget exhausted for this window.", "errors": out.get("errors")},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if out["status"] == "error":
            return Response(
                {"detail": f"AI search unavailable: {out.get('detail')}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"search": out["search"], "results": out["results"]})


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
