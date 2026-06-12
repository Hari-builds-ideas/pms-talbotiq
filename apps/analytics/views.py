"""
Analytics & Reporting API — the HTTP surface of Module A (deterministic reporting
over already-built data: Module-2 ``CycleScore`` and the Module-8 9-box).

Views are THIN and the SOLE RBAC gate. Each endpoint subclasses
:class:`~apps.rbac.mixins.RBACMixin` and declares a single ``required_capability``;
``IsAuthenticated`` + ``HasCapability`` are then wired for free. Everything else —
data SCOPE (an Employee sees only their own; a Manager their reporting line;
HRBP/Admin the tenant) and the headline MIN-COHORT SUPPRESSION (a cohort < 5 is
returned aggregate-only) — lives ENTIRELY in ``services``; the views never
re-implement it. An out-of-scope subject raises ``NotFound`` (404) inside the
service and is allowed to propagate.

Referenced rows (employee, head, cycle) are resolved through their tenant-scoped
managers via ``get_object_or_404(Model.objects.all(), pk=...)`` — the tenant is
bound from the JWT by ``TenantMiddleware``, so a cross-tenant id never resolves
and falls out as a 404 (never a tenant-leaking 403). The capabilities map
``VIEW_INDIVIDUAL_ANALYTICS`` (all roles, OWN for an employee),
``VIEW_DEPARTMENT_ANALYTICS`` (Manager+; NEVER an employee) and
``VIEW_CALIBRATION_GRID`` (HRBP/Admin).

The services are read-only, so there is no audit write and no mutator here.
"""
from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cycles.models import PerformanceCycle
from apps.identity.models import User
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import services


class _ExportContentNegotiation(DefaultContentNegotiation):
    """Content negotiation that IGNORES the ``?format=`` query param.

    DRF's default negotiation treats ``?format=`` as a renderer override
    (``URL_FORMAT_OVERRIDE='format'``): with no matching renderer it raises during
    negotiation BEFORE the view runs (a 404/406), so ``?format=text`` would never
    reach ``get()``. The export endpoint owns ``?format`` as its OWN parameter
    (json|text) and returns a raw ``HttpResponse``, so we always pick the first
    (JSON) renderer and let the view interpret ``?format`` itself."""

    def select_renderer(self, request, renderers, format_suffix=None):
        # Bypass the query-param override entirely: the view, not DRF, owns
        # ``?format``. Return the first configured renderer (its media type is
        # irrelevant — the view replaces the response with an HttpResponse).
        return (renderers[0], renderers[0].media_type)


def _resolve_employee(request, *, param="employee"):
    """Resolve a ``?<param>=<uuid>`` to a User in the caller's tenant, defaulting
    to the caller. A cross-tenant / unknown id → 404 (tenant-scoped manager)."""
    value = request.query_params.get(param)
    if not value:
        return request.user
    return get_object_or_404(User.objects.all(), pk=value)


def _require_cycle(request, *, param="cycle"):
    """Resolve the REQUIRED ``?cycle=<uuid>``. Missing → 400; cross-tenant /
    unknown id → 404. Returns the cycle, or a ``Response`` to short-circuit."""
    value = request.query_params.get(param)
    if not value:
        return Response({"detail": "cycle is required."}, status=400)
    return get_object_or_404(PerformanceCycle.objects.all(), pk=value)


# ── individual analytics ──────────────────────────────────────────────────────


class IndividualAnalyticsView(RBACMixin, APIView):
    """``GET /api/analytics/individual`` (VIEW_INDIVIDUAL_ANALYTICS — all roles).

    Optional ``?employee=<uuid>`` (default = the caller). The service scopes the
    subject — an Employee may see only themselves, a Manager their reports,
    HRBP/Admin the tenant — and 404s an out-of-scope subject."""

    required_capability = Capability.VIEW_INDIVIDUAL_ANALYTICS

    def get(self, request):
        employee = _resolve_employee(request)
        return Response(services.individual_trend(request.user, employee))


# ── department analytics ──────────────────────────────────────────────────────


class DepartmentAnalyticsView(RBACMixin, APIView):
    """``GET /api/analytics/department`` (VIEW_DEPARTMENT_ANALYTICS — Manager+;
    NEVER an employee).

    Optional ``?head=<uuid>`` (default = the caller) + REQUIRED ``?cycle=<uuid>``.
    The service confines ``head`` to the actor's scope (404 otherwise) and applies
    MIN-COHORT suppression (a cohort < 5 → aggregate-only)."""

    required_capability = Capability.VIEW_DEPARTMENT_ANALYTICS

    def get(self, request):
        head = _resolve_employee(request, param="head")
        cycle = _require_cycle(request)
        if isinstance(cycle, Response):
            return cycle
        return Response(services.department_analytics(request.user, head, cycle))


# ── calibration grid ──────────────────────────────────────────────────────────


class CalibrationGridView(RBACMixin, APIView):
    """``GET /api/analytics/calibration`` (VIEW_CALIBRATION_GRID — HRBP/Admin).

    REQUIRED ``?cycle=<uuid>``. Returns the 9-box calibration grid for the cycle,
    tenant-scoped via the reused Module-8 ``NineBoxPlacement``."""

    required_capability = Capability.VIEW_CALIBRATION_GRID

    def get(self, request):
        cycle = _require_cycle(request)
        if isinstance(cycle, Response):
            return cycle
        return Response(services.calibration_grid(request.user, cycle))


# ── export (text / JSON only — no binary) ─────────────────────────────────────


class DepartmentExportView(RBACMixin, APIView):
    """``GET /api/analytics/export`` (VIEW_DEPARTMENT_ANALYTICS — Manager+).

    Optional ``?head=<uuid>`` (default = the caller) + REQUIRED ``?cycle=<uuid>``
    + ``?format=json|text`` (default json). Exports the department rollup, honouring
    the same scope + min-cohort suppression as the department view (the service
    calls ``department_analytics``). Text/JSON only — never binary."""

    required_capability = Capability.VIEW_DEPARTMENT_ANALYTICS
    content_negotiation_class = _ExportContentNegotiation

    def get(self, request):
        head = _resolve_employee(request, param="head")
        cycle = _require_cycle(request)
        if isinstance(cycle, Response):
            return cycle
        fmt = request.query_params.get("format", "json")
        content, content_type = services.export_department(
            request.user, head, cycle, fmt=fmt
        )
        return HttpResponse(content, content_type=content_type)
