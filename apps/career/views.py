"""
Career Development (Roadmap LITE) API — the HTTP surface of Module 9.

Career is EMPLOYEE-VISIBLE (unlike succession): every role holds the three career
capabilities, so the views never 403 a role out — instead SCOPE confines what each
caller may touch and an out-of-scope / cross-tenant employee or roadmap is a 404
(never a 403 that would leak existence).

Views stay THIN and are the SOLE RBAC gate: each declares its
``required_capability`` (multi-method views use a ``_caps`` dict + a
``get_permissions`` override so GET and POST can gate different capabilities). The
SERVICES are the SOLE mutators AND the SOLE scope authority — a Manager is confined
to their reporting subtree and an out-of-tier / cross-tenant target falls out of
the service as a 404. The views only gate the capability, resolve referenced rows
through their TENANT-SCOPED managers (cross-tenant id → 404 via
``get_object_or_404``), call the service, and serialize. There is deliberately NO
PATCH/PUT mutator.

THE DATA BOUNDARY: a career response carries ONLY the employee's own
performance-derived gap (performance band, weak goal categories) + advisory tiers —
never the succession surface (readiness / potential / bench / coverage / 9-box) nor
any other employee's data. The engine + serializers guarantee this; the views add
nothing back.

The Career Roadmap agent (Module 10) enrich seam is called SYNCHRONOUSLY; until a
provider ships it returns ``no_provider`` and the view surfaces a loud 503 with the
DETERMINISTIC roadmap left COMPLETELY INTACT — no fake roadmap is ever written.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.identity.models import User
from apps.jd.models import JobDescription
from apps.org.models import Position
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import services
from .serializers import (
    DevelopmentRoadmapSerializer,
    ProgressSerializer,
    RoadmapProgressSerializer,
    TargetRoleSelectionSerializer,
    TargetSelectSerializer,
)
from .tasks import generate_roadmap


# ── target selection + deterministic generation ───────────────────────────────


class TargetSelectView(RBACMixin, APIView):
    """``POST /api/career/target`` (SELECT_TARGET_ROLE) — select a target role and
    get the deterministic roadmap. ``employee`` defaults to the caller; the
    ``employee`` / ``target_jd`` / ``target_position`` UUIDs are resolved through the
    tenant-scoped managers (cross-tenant id → 404). The service validates exactly
    one target (422), a PUBLISHED target JD (422) and the employee's scope (404),
    then creates the deterministic roadmap."""

    required_capability = Capability.SELECT_TARGET_ROLE

    def post(self, request):
        serializer = TargetSelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("employee") is not None:
            employee = get_object_or_404(User.objects.all(), pk=data["employee"])
        else:
            employee = request.user

        target_jd = None
        if data.get("target_jd") is not None:
            target_jd = get_object_or_404(
                JobDescription.objects.all(), pk=data["target_jd"]
            )
        target_position = None
        if data.get("target_position") is not None:
            target_position = get_object_or_404(
                Position.objects.all(), pk=data["target_position"]
            )

        selection, roadmap = services.select_target_role(
            request.user,
            employee,
            target_jd=target_jd,
            target_position=target_position,
        )
        return Response(
            {
                "selection": TargetRoleSelectionSerializer(selection).data,
                "roadmap": DevelopmentRoadmapSerializer(roadmap).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ── reads ──────────────────────────────────────────────────────────────────────


class MyRoadmapsView(RBACMixin, APIView):
    """``GET /api/career/roadmap`` (VIEW_CAREER_ROADMAP) — the CALLER'S OWN
    roadmaps."""

    required_capability = Capability.VIEW_CAREER_ROADMAP

    def get(self, request):
        roadmaps = services.list_roadmaps(request.user, employee=request.user)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(roadmaps, request, view=self)
        return paginator.get_paginated_response(
            DevelopmentRoadmapSerializer(page, many=True).data
        )


class RoadmapListView(RBACMixin, APIView):
    """``GET /api/career/roadmaps`` (VIEW_CAREER_ROADMAP) — the actor-scoped
    roadmaps, optionally filtered by ``?employee=<uuid>`` (resolved through the
    tenant-scoped manager → 404; an out-of-scope employee 404s in the service)."""

    required_capability = Capability.VIEW_CAREER_ROADMAP

    def get(self, request):
        employee = None
        employee_id = request.query_params.get("employee")
        if employee_id:
            employee = get_object_or_404(User.objects.all(), pk=employee_id)
        roadmaps = services.list_roadmaps(request.user, employee=employee)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(roadmaps, request, view=self)
        return paginator.get_paginated_response(
            DevelopmentRoadmapSerializer(page, many=True).data
        )


class RoadmapDetailView(RBACMixin, APIView):
    """``GET /api/career/roadmaps/<pk>`` (VIEW_CAREER_ROADMAP) — one roadmap, loaded
    through ``services.get_roadmap_in_scope`` so an out-of-scope / cross-tenant id is
    a 404 (the scope rule hides it rather than leaking a 403)."""

    required_capability = Capability.VIEW_CAREER_ROADMAP

    def get(self, request, pk):
        roadmap = services.get_roadmap_in_scope(request.user, pk)
        return Response(DevelopmentRoadmapSerializer(roadmap).data)


class RoadmapSkillGapView(RBACMixin, APIView):
    """``GET /api/career/roadmaps/<pk>/skill-gap`` (VIEW_CAREER_ROADMAP) — the live
    deterministic skill gap for the roadmap's employee. Contains ONLY the employee's
    own performance-derived gap — never succession data."""

    required_capability = Capability.VIEW_CAREER_ROADMAP

    def get(self, request, pk):
        roadmap = services.get_roadmap_in_scope(request.user, pk)
        gap = services.skill_gap_for(request.user, services._employee_of(roadmap))
        return Response(gap)


# ── regenerate (deterministic refresh) ─────────────────────────────────────────


class RoadmapRegenerateView(RBACMixin, APIView):
    """``POST /api/career/roadmaps/<pk>/regenerate`` (MANAGE_CAREER_ROADMAP) —
    refresh the deterministic roadmap's gap + tiers from the employee's current
    performance data. The roadmap is loaded through ``services.get_roadmap_in_scope``
    (out-of-scope / cross-tenant → 404)."""

    required_capability = Capability.MANAGE_CAREER_ROADMAP

    def post(self, request, pk):
        roadmap = services.get_roadmap_in_scope(request.user, pk)
        roadmap = services.regenerate_roadmap(request.user, roadmap)
        return Response(DevelopmentRoadmapSerializer(roadmap).data)


# ── the Career Roadmap agent (Module 10) enrich seam ───────────────────────────


class RoadmapEnrichView(RBACMixin, APIView):
    """``POST /api/career/roadmaps/<pk>/enrich`` (MANAGE_CAREER_ROADMAP) — the Career
    Roadmap agent (Module 10) seam. Calls the enrichment task SYNCHRONOUSLY.

    The LOUD seam: until Module 10 ships a provider this returns 503 with
    ``reason: no_provider`` and the DETERMINISTIC roadmap stays COMPLETELY INTACT —
    no fake roadmap is ever written. A successful enrichment locks a NEW AI roadmap
    (DRAFT, advisory) and returns 200 with the result; any other skip reason is a
    409. The roadmap is loaded through ``services.get_roadmap_in_scope``
    (out-of-scope / cross-tenant → 404)."""

    required_capability = Capability.MANAGE_CAREER_ROADMAP

    def post(self, request, pk):
        roadmap = services.get_roadmap_in_scope(request.user, pk)
        target_ref = (
            {"jd": str(roadmap.target_jd_id)}
            if roadmap.target_jd_id
            else {"position": str(roadmap.target_position_id)}
        )
        # Synchronous call by design for the MVP (production may .delay() later).
        result = generate_roadmap(
            str(request.user.tenant_id),
            str(roadmap.employee_id),
            target_ref,
            actor_id=str(request.user.id),
        )
        if result.get("generated"):
            return Response(result)
        if result.get("reason") == "no_provider":
            body = dict(result)
            body["detail"] = (
                "The Career Roadmap agent is not configured; it lands in Module 10. "
                "The deterministic roadmap is left intact."
            )
            return Response(body, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result, status=status.HTTP_409_CONFLICT)


# ── per-tier progress ───────────────────────────────────────────────────────────


class RoadmapProgressView(RBACMixin, APIView):
    """``GET, POST /api/career/roadmaps/<pk>/progress``.

    The roadmap is loaded through ``services.get_roadmap_in_scope`` (out-of-scope /
    cross-tenant → 404). GET (VIEW_CAREER_ROADMAP): the roadmap's per-tier progress.
    POST (MANAGE_CAREER_ROADMAP): mark a tier's progress (upsert per roadmap+tier);
    an out-of-range ``tier_index`` is a 422 in the service."""

    _caps = {
        "GET": Capability.VIEW_CAREER_ROADMAP,
        "POST": Capability.MANAGE_CAREER_ROADMAP,
    }

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request, pk):
        roadmap = services.get_roadmap_in_scope(request.user, pk)
        progress = services.list_progress(request.user, roadmap)
        return Response(RoadmapProgressSerializer(progress, many=True).data)

    def post(self, request, pk):
        roadmap = services.get_roadmap_in_scope(request.user, pk)
        serializer = ProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        progress = services.set_progress(
            request.user,
            roadmap,
            tier_index=serializer.validated_data["tier_index"],
            status=serializer.validated_data["status"],
        )
        return Response(RoadmapProgressSerializer(progress).data)
