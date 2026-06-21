"""
Live Org Chart API — the HTTP surface of Module 7.

Views stay THIN on purpose:
  * the reads (tree / person-card / search / export / vacancies) go through
    ``services``, which compute the live hierarchy from ``User.manager`` and
    apply the §2 scope rule (OWN line / TEAM subtree / TENANT all) IN MEMORY over
    a per-tenant cached tree — so an out-of-scope (or inactive / cross-tenant)
    target falls out as a 404 (never a 403 that would leak existence). The views
    only gate the capability and return the service payload verbatim;
  * the position writes (create / fill / close / link-jd / unlink-jd) go through
    ``positions``, which enforce legality (409 ``POSITION_ALREADY_FILLED`` /
    ``ILLEGAL_POSITION_TRANSITION``) and input validity (422 ``INVALID_ORG_INPUT``
    for an inactive / cross-tenant manager or a non-published / cross-tenant JD)
    internally and invalidate the tenant org cache so the next read reflects the
    change;
  * the reassignment goes through ``reassign``, which is cycle-checked (422
    ``REPORTING_CYCLE``) and likewise cache-invalidating.

Every referenced user / position / JD is loaded through its TENANT-SCOPED default
manager (the tenant is bound from the JWT by ``TenantMiddleware``), so a
cross-tenant id never resolves and we never filter by tenant by hand. The
services / writes do NOT re-check RBAC — these views are the SOLE RBAC gate, so
every endpoint declares its capability.

There is deliberately NO PATCH/PUT mutator: the position writes + the
reassignment are the only mutators.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.identity.models import User
from apps.jd.models import JobDescription
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import positions, reassign, services
from .models import Position
from .serializers import (
    PositionCreateSerializer,
    PositionFillSerializer,
    PositionLinkJDSerializer,
    PositionSerializer,
    ReassignSerializer,
)


# ── reads (VIEW_ORG_CHART — everyone, scope-filtered by the services) ─────────


class OrgTreeView(RBACMixin, APIView):
    """``GET /api/org/tree`` (VIEW_ORG_CHART) — the actor-scoped org tree
    (``{nodes, edges, roots}`` with headcount + vacancy rollups). The service
    applies the §2 scope tier, so an employee sees only their line.

    Optional lazy params (the default with neither is the full scoped tree):
      * ``?root=<id>`` → the subtree under a visible node (out-of-scope → 404);
      * ``?depth=<n>`` → only ``n`` levels below the root(s), for expand-on-demand.
    """

    required_capability = Capability.VIEW_ORG_CHART

    def get(self, request):
        root = request.query_params.get("root") or None
        depth = None
        depth_raw = request.query_params.get("depth")
        if depth_raw not in (None, ""):
            try:
                depth = max(0, int(depth_raw))
            except (TypeError, ValueError):
                depth = None  # a non-integer depth is ignored → behave as unbounded
        return Response(services.build_org_tree(request.user, root=root, depth=depth))


class PersonCardView(RBACMixin, APIView):
    """``GET /api/org/people/<pk>`` (VIEW_ORG_CHART) — scoped detail for one
    person (manager, direct-report count, filled positions). An out-of-scope /
    inactive / cross-tenant target is a 404 (the service hides it rather than
    leaking a 403 — do NOT catch)."""

    required_capability = Capability.VIEW_ORG_CHART

    def get(self, request, pk):
        return Response(services.person_card(request.user, pk))


class OrgSearchView(RBACMixin, APIView):
    """``GET /api/org/search?q=`` (VIEW_ORG_CHART) — people within the actor's
    scope whose email OR filled-position title matches ``q`` (case-insensitive;
    an empty ``q`` returns the whole visible scope)."""

    required_capability = Capability.VIEW_ORG_CHART

    def get(self, request):
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(
            services.search_people(request.user, request.query_params.get("q", "")),
            request,
            view=self,
        )
        return paginator.get_paginated_response(page)


class OrgExportView(RBACMixin, APIView):
    """``GET /api/org/export`` (VIEW_ORG_CHART) — the actor-scoped org structure
    as structured JSON + a flat node list (text/JSON only; no binary export)."""

    required_capability = Capability.VIEW_ORG_CHART

    def get(self, request):
        return Response(services.export_org(request.user))


class VacancyListView(RBACMixin, APIView):
    """``GET /api/org/vacancies`` (VIEW_ORG_CHART) — OPEN positions within the
    actor's scope. HRBP/Admin also see tenant-level vacancies (reports_to null);
    Manager/Employee see only vacancies reporting into their visible subtree."""

    required_capability = Capability.VIEW_ORG_CHART

    def get(self, request):
        return Response(services.list_vacancies(request.user))


# ── position writes (MANAGE_POSITIONS — HRBP/Admin) ───────────────────────────


class PositionListCreateView(RBACMixin, APIView):
    """``GET, POST /api/org/positions`` (MANAGE_POSITIONS).

    GET: every position in the tenant (the scoped manager auto-filters tenant).
    POST: create an OPEN position (a vacancy) — the ``reports_to`` manager and
    optional ``published_jd`` are resolved through the tenant-scoped managers
    (cross-tenant id → 404); the write 422s on an inactive / cross-tenant manager
    or a non-published / cross-tenant JD.
    """

    _caps = {"GET": Capability.MANAGE_POSITIONS, "POST": Capability.MANAGE_POSITIONS}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        # select_related the FKs the serializer resolves for filled_by_name /
        # reports_to_name / published_jd_title (else N+1 per position).
        positions_qs = Position.objects.select_related(
            "filled_by", "reports_to", "published_jd"
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(positions_qs, request, view=self)
        return paginator.get_paginated_response(
            PositionSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = PositionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reports_to = get_object_or_404(User.objects.all(), pk=data["reports_to"])
        published_jd = None
        if data.get("published_jd") is not None:
            published_jd = get_object_or_404(
                JobDescription.objects.all(), pk=data["published_jd"]
            )
        position = positions.create_position(
            request.user,
            title=data["title"],
            reports_to=reports_to,
            department=data.get("department"),
            published_jd=published_jd,
        )
        return Response(
            PositionSerializer(position).data, status=status.HTTP_201_CREATED
        )


class PositionDetailView(RBACMixin, APIView):
    """``GET /api/org/positions/<pk>`` (MANAGE_POSITIONS) — one position by id,
    loaded through the tenant-scoped manager (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_POSITIONS

    def get(self, request, pk):
        position = get_object_or_404(Position.objects.all(), pk=pk)
        return Response(PositionSerializer(position).data)


class PositionFillView(RBACMixin, APIView):
    """``POST /api/org/positions/<pk>/fill`` (MANAGE_POSITIONS) — fill an OPEN
    position with ``filled_by`` (→ FILLED). 409 if already FILLED / CLOSED; the
    employee is resolved through the tenant-scoped manager (cross-tenant → 404)
    and 422s if inactive / cross-tenant."""

    required_capability = Capability.MANAGE_POSITIONS

    def post(self, request, pk):
        position = get_object_or_404(Position.objects.all(), pk=pk)
        serializer = PositionFillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filled_by = get_object_or_404(
            User.objects.all(), pk=serializer.validated_data["filled_by"]
        )
        position = positions.fill_position(request.user, position, filled_by)
        return Response(PositionSerializer(position).data)


class PositionCloseView(RBACMixin, APIView):
    """``POST /api/org/positions/<pk>/close`` (MANAGE_POSITIONS) — close an
    OPEN/FILLED position (→ CLOSED), clearing the vacancy. 409 if already
    CLOSED."""

    required_capability = Capability.MANAGE_POSITIONS

    def post(self, request, pk):
        position = get_object_or_404(Position.objects.all(), pk=pk)
        position = positions.close_position(request.user, position)
        return Response(PositionSerializer(position).data)


class PositionLinkJDView(RBACMixin, APIView):
    """``POST /api/org/positions/<pk>/link-jd`` (MANAGE_POSITIONS) — link a
    PUBLISHED, in-tenant JD to the position. The JD is resolved through the
    tenant-scoped manager (cross-tenant id → 404); the write 422s if the JD is
    not PUBLISHED."""

    required_capability = Capability.MANAGE_POSITIONS

    def post(self, request, pk):
        position = get_object_or_404(Position.objects.all(), pk=pk)
        serializer = PositionLinkJDSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        jd = get_object_or_404(
            JobDescription.objects.all(), pk=serializer.validated_data["jd"]
        )
        position = positions.link_jd(request.user, position, jd)
        return Response(PositionSerializer(position).data)


class PositionUnlinkJDView(RBACMixin, APIView):
    """``POST /api/org/positions/<pk>/unlink-jd`` (MANAGE_POSITIONS) — clear the
    position's linked JD."""

    required_capability = Capability.MANAGE_POSITIONS

    def post(self, request, pk):
        position = get_object_or_404(Position.objects.all(), pk=pk)
        position = positions.unlink_jd(request.user, position)
        return Response(PositionSerializer(position).data)


# ── reassignment (REASSIGN_REPORTING_LINE — HRBP/Admin) ───────────────────────


class ReassignView(RBACMixin, APIView):
    """``POST /api/org/reassign`` (REASSIGN_REPORTING_LINE) — move a person to a
    new manager (cycle-checked). Both ``user`` and ``new_manager`` are resolved
    through the tenant-scoped manager (cross-tenant id → 404); the write 422s on
    a self / subtree cycle (``REPORTING_CYCLE``) or an inactive / cross-tenant
    manager (``INVALID_ORG_INPUT``). Cache-invalidating, so the next tree read
    reflects the move."""

    required_capability = Capability.REASSIGN_REPORTING_LINE

    def post(self, request):
        serializer = ReassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = get_object_or_404(User.objects.all(), pk=data["user"])
        new_manager = get_object_or_404(User.objects.all(), pk=data["new_manager"])
        user = reassign.reassign_reporting_line(request.user, user, new_manager)
        return Response({"id": str(user.id), "manager": str(user.manager_id)})
