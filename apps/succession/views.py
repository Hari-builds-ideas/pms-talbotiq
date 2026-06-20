"""
Succession & Talent API — the HTTP surface of Module 8, the MOST SENSITIVE data
in the system.

THE HEADLINE RULE — SENSITIVITY: succession is MANAGEMENT-ONLY. There is NO
employee access to ANY endpoint here — not even to their own 9-box or readiness.
Every view subclasses :class:`~apps.succession.permissions.SuccessionMixin`, whose
``get_permissions`` orders ``[IsAuthenticated, SuccessionParticipant,
HasCapability]`` — so an employee (or any non-management role) 404s at the
participant gate BEFORE the capability check could 403 them: the module must not
leak its own existence.

Views stay THIN on purpose:
  * the reads/writes go through ``services`` (critical-role registry, bench,
    9-box) and ``plans`` (the HITL plan state machine + dashboard), which are the
    SOLE scope authority — a Manager is confined to their reporting subtree and an
    out-of-tier / cross-tenant target falls out as a 404 (never a 403 that would
    leak existence). The views only gate the capability, resolve referenced rows
    through their tenant-scoped managers (cross-tenant id → 404), call the
    service / plan, and serialize;
  * the plan HITL (``generate`` → PENDING_HUMAN_REVIEW → ``action-item`` →
    ``publish``) enforces legality internally (409 ``ILLEGAL_PLAN_TRANSITION``);
  * the Agent-4 enrichment comes from ``enrich_succession_with_agent4``, called
    SYNCHRONOUSLY. Until Module 10 ships a provider it returns ``no_provider`` and
    the view surfaces a loud 503 — the DETERMINISTIC plan is left COMPLETELY
    INTACT and no fake analysis is ever written.

The tenant is bound from the JWT by ``TenantMiddleware``; the scoped managers
auto-filter, so a cross-tenant row never resolves and we never filter by tenant by
hand. The services / plans / tasks are the ONLY mutators and the sole scope
authority — these views are the SOLE RBAC gate, so every endpoint declares its
capability.

There is deliberately NO PATCH/PUT mutator.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.serializers import AIJobSerializer
from apps.ai.services import enqueue_agent_job
from apps.core.pagination import StandardResultsSetPagination
from apps.cycles.models import PerformanceCycle
from apps.identity.models import User
from apps.org.models import Position
from apps.rbac.matrix import Capability

from . import plans, services
from .models import BenchCandidate, CriticalRole, SuccessionPlan
from .permissions import SuccessionMixin
from .serializers import (
    ActionItemSerializer,
    BenchAddSerializer,
    BenchCandidateSerializer,
    CriticalRoleCreateSerializer,
    CriticalRoleSerializer,
    KnowledgeRiskSerializer,
    NineBoxAssessSerializer,
    NineBoxSerializer,
    ReadinessSerializer,
    SuccessionPlanSerializer,
)


# ── dashboard ─────────────────────────────────────────────────────────────────


class DashboardView(SuccessionMixin, APIView):
    """``GET /api/succession/dashboard`` (VIEW_SUCCESSION) — the scoped succession
    dashboard: HRBP/Admin see the tenant, a Manager sees only critical roles
    touching their reporting tier, each carrying its latest PUBLISHED plan's
    coverage. An employee 404s at the participant gate."""

    required_capability = Capability.VIEW_SUCCESSION

    def get(self, request):
        return Response(plans.dashboard(request.user))


# ── critical-role registry ────────────────────────────────────────────────────


class CriticalRoleListCreateView(SuccessionMixin, APIView):
    """``GET, POST /api/succession/critical-roles``.

    GET (VIEW_SUCCESSION): the actor-scoped critical roles. POST
    (MANAGE_CRITICAL_ROLES — HRBP+): register a critical role; the optional
    ``position`` (org Position) and ``incumbent`` (User) are resolved through the
    tenant-scoped managers (cross-tenant id → 404). An employee 404s at the
    participant gate; a Manager (a participant lacking the HRBP-only capability)
    403s on POST.
    """

    _caps = {
        "GET": Capability.VIEW_SUCCESSION,
        "POST": Capability.MANAGE_CRITICAL_ROLES,
    }

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        roles = services.list_critical_roles(request.user)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(roles, request, view=self)
        return paginator.get_paginated_response(
            CriticalRoleSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = CriticalRoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        position = None
        if data.get("position") is not None:
            position = get_object_or_404(Position.objects.all(), pk=data["position"])
        incumbent = None
        if data.get("incumbent") is not None:
            incumbent = get_object_or_404(User.objects.all(), pk=data["incumbent"])
        role = services.mark_critical_role(
            request.user,
            name=data["name"],
            position=position,
            incumbent=incumbent,
            criticality=data.get("criticality"),
            knowledge_risk=data.get("knowledge_risk"),
            risk_notes=data.get("risk_notes") or "",
        )
        return Response(
            CriticalRoleSerializer(role).data, status=status.HTTP_201_CREATED
        )


class CriticalRoleDetailView(SuccessionMixin, APIView):
    """``GET /api/succession/critical-roles/<pk>`` (VIEW_SUCCESSION) — one critical
    role, loaded through ``services.get_critical_role_in_scope`` so an out-of-tier
    / cross-tenant id is a 404 (the scope rule hides it rather than leaking a
    403)."""

    required_capability = Capability.VIEW_SUCCESSION

    def get(self, request, pk):
        role = services.get_critical_role_in_scope(request.user, pk)
        return Response(CriticalRoleSerializer(role).data)


class KnowledgeRiskView(SuccessionMixin, APIView):
    """``POST /api/succession/critical-roles/<pk>/knowledge-risk``
    (MANAGE_CRITICAL_ROLES — HRBP+) — update a role's knowledge-risk flag (and
    optionally its notes). The role is loaded through the tenant-scoped manager
    (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_CRITICAL_ROLES

    def post(self, request, pk):
        role = get_object_or_404(CriticalRole.objects.all(), pk=pk)
        serializer = KnowledgeRiskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = services.update_knowledge_risk(
            request.user,
            role,
            knowledge_risk=serializer.validated_data["knowledge_risk"],
            risk_notes=serializer.validated_data.get("risk_notes"),
        )
        return Response(CriticalRoleSerializer(role).data)


class CriticalRoleArchiveView(SuccessionMixin, APIView):
    """``POST /api/succession/critical-roles/<pk>/archive``
    (MANAGE_CRITICAL_ROLES — HRBP+) — archive a critical role (→ ARCHIVED). The
    role is loaded through the tenant-scoped manager (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_CRITICAL_ROLES

    def post(self, request, pk):
        role = get_object_or_404(CriticalRole.objects.all(), pk=pk)
        role = services.archive_critical_role(request.user, role)
        return Response(CriticalRoleSerializer(role).data)


# ── bench ─────────────────────────────────────────────────────────────────────


class BenchListCreateView(SuccessionMixin, APIView):
    """``GET, POST /api/succession/critical-roles/<pk>/bench``.

    The role is loaded through ``services.get_critical_role_in_scope`` (out-of-tier
    / cross-tenant → 404). GET (VIEW_SUCCESSION): the role's bench, scoped (a
    Manager sees only candidates within their reporting subtree). POST
    (MANAGE_BENCH — Manager+): add a candidate (resolved through the tenant-scoped
    manager; an out-of-tier candidate 404s in the service), seeding the
    deterministic readiness.
    """

    _caps = {"GET": Capability.VIEW_SUCCESSION, "POST": Capability.MANAGE_BENCH}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request, pk):
        role = services.get_critical_role_in_scope(request.user, pk)
        bench = services.list_bench(request.user, role)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(bench, request, view=self)
        return paginator.get_paginated_response(
            BenchCandidateSerializer(page, many=True).data
        )

    def post(self, request, pk):
        role = services.get_critical_role_in_scope(request.user, pk)
        serializer = BenchAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        candidate = get_object_or_404(User.objects.all(), pk=data["candidate"])
        bench_candidate = services.add_bench_candidate(
            request.user, role, candidate, notes=data.get("notes") or ""
        )
        return Response(
            BenchCandidateSerializer(bench_candidate).data,
            status=status.HTTP_201_CREATED,
        )


class BenchReadinessView(SuccessionMixin, APIView):
    """``POST /api/succession/bench/<pk>/readiness`` (MANAGE_BENCH — Manager+) — set
    a candidate's readiness (an override that STICKS). The bench entry is loaded
    through the tenant-scoped manager (cross-tenant id → 404); an out-of-tier
    candidate 404s in the service."""

    required_capability = Capability.MANAGE_BENCH

    def post(self, request, pk):
        bench_candidate = get_object_or_404(BenchCandidate.objects.all(), pk=pk)
        serializer = ReadinessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bench_candidate = services.set_readiness(
            request.user, bench_candidate, serializer.validated_data["readiness"]
        )
        return Response(BenchCandidateSerializer(bench_candidate).data)


# ── 9-box ─────────────────────────────────────────────────────────────────────


class NineBoxListCreateView(SuccessionMixin, APIView):
    """``GET, POST /api/succession/nine-box``.

    GET (VIEW_SUCCESSION): the actor-scoped 9-box placements, optionally filtered
    by ``?cycle=`` (resolved through the tenant-scoped manager → 404). POST
    (ASSESS_NINE_BOX — Manager+): place an employee on the 9-box for a cycle (both
    resolved through the tenant-scoped managers → 404; an out-of-tier employee
    404s in the service). The performance band + box are DERIVED from the Module-2
    CycleScore; only the potential band is human-assigned. Upserts per
    employee+cycle.
    """

    _caps = {"GET": Capability.VIEW_SUCCESSION, "POST": Capability.ASSESS_NINE_BOX}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        cycle = None
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            cycle = get_object_or_404(PerformanceCycle.objects.all(), pk=cycle_id)
        placements = services.list_nine_box(request.user, cycle=cycle)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(placements, request, view=self)
        return paginator.get_paginated_response(
            NineBoxSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = NineBoxAssessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        employee = get_object_or_404(User.objects.all(), pk=data["employee"])
        cycle = get_object_or_404(PerformanceCycle.objects.all(), pk=data["cycle"])
        placement = services.assess_nine_box(
            request.user,
            employee,
            cycle,
            potential_band=data["potential_band"],
        )
        return Response(
            NineBoxSerializer(placement).data, status=status.HTTP_201_CREATED
        )


# ── plan HITL ─────────────────────────────────────────────────────────────────


class GenerateAnalysisView(SuccessionMixin, APIView):
    """``POST /api/succession/critical-roles/<pk>/generate``
    (GENERATE_SUCCESSION_ANALYSIS — HRBP+) — run the deterministic analysis and
    lock a NEW plan PENDING_HUMAN_REVIEW. The role is loaded through the
    tenant-scoped manager (cross-tenant id → 404); a Manager 403s (participant
    without the HRBP-only capability)."""

    required_capability = Capability.GENERATE_SUCCESSION_ANALYSIS

    def post(self, request, pk):
        role = get_object_or_404(CriticalRole.objects.all(), pk=pk)
        plan = plans.generate_plan(request.user, role)
        return Response(
            SuccessionPlanSerializer(plan).data, status=status.HTTP_201_CREATED
        )


class PlanDetailView(SuccessionMixin, APIView):
    """``GET /api/succession/plans/<pk>`` (VIEW_SUCCESSION) — one plan, loaded
    through ``plans.get_plan_in_scope`` so an out-of-tier / cross-tenant id is a
    404 (the scope rule hides it rather than leaking a 403)."""

    required_capability = Capability.VIEW_SUCCESSION

    def get(self, request, pk):
        plan = plans.get_plan_in_scope(request.user, pk)
        return Response(SuccessionPlanSerializer(plan).data)


class PlanActionItemView(SuccessionMixin, APIView):
    """``POST /api/succession/plans/<pk>/action-item``
    (PUBLISH_SUCCESSION_PLAN — HRBP+) — append an HRBP action item during review.
    The plan is loaded through the tenant-scoped manager (cross-tenant id → 404);
    409 ``ILLEGAL_PLAN_TRANSITION`` if the plan is not PENDING_HUMAN_REVIEW."""

    required_capability = Capability.PUBLISH_SUCCESSION_PLAN

    def post(self, request, pk):
        plan = get_object_or_404(SuccessionPlan.objects.all(), pk=pk)
        serializer = ActionItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = plans.add_action_item(
            request.user, plan, serializer.validated_data["item"]
        )
        return Response(SuccessionPlanSerializer(plan).data)


class PlanPublishView(SuccessionMixin, APIView):
    """``POST /api/succession/plans/<pk>/publish`` (PUBLISH_SUCCESSION_PLAN — HRBP+)
    — PENDING_HUMAN_REVIEW → PUBLISHED (to the dashboard). The plan is loaded
    through the tenant-scoped manager (cross-tenant id → 404); 409
    ``ILLEGAL_PLAN_TRANSITION`` if it has not been through review."""

    required_capability = Capability.PUBLISH_SUCCESSION_PLAN

    def post(self, request, pk):
        plan = get_object_or_404(SuccessionPlan.objects.all(), pk=pk)
        plan = plans.publish_plan(request.user, plan)
        return Response(SuccessionPlanSerializer(plan).data)


class PlanEnrichView(SuccessionMixin, APIView):
    """``POST /api/succession/plans/<pk>/enrich``
    (GENERATE_SUCCESSION_ANALYSIS — HRBP+) — the Agent-4 (Successor Planning) seam.
    ENQUEUES the enrichment and returns ``202`` + an AI job id; the client polls
    ``GET /api/ai/jobs/<id>``.

    Async by design (BUILD_2). The DETERMINISTIC plan stays COMPLETELY INTACT
    while the job runs; on success the worker locks a NEW AI plan
    PENDING_HUMAN_REVIEW (name-free evidence, unchanged). No provider lands the
    job DEGRADED — no fake analysis is ever written. The plan is loaded
    tenant-scoped here (cross-tenant / out-of-tier → 404 before enqueue).
    """

    required_capability = Capability.GENERATE_SUCCESSION_ANALYSIS

    def post(self, request, pk):
        plan = plans.get_plan_in_scope(request.user, pk)
        job = enqueue_agent_job(
            actor=request.user,
            agent_code="agent4",
            target_type="succession_plan",
            target_id=plan.id,
        )
        return Response(AIJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)
