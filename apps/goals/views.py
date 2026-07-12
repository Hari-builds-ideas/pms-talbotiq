"""
Goals & KPI API — the goal tree (goals, nested KPIs, actuals) and the KPI
template instantiation path.

RBAC is enforced two ways, mirroring the model:
  * a capability gate (``required_capability`` / per-method ``get_permissions``)
    decides the *verb*;
  * a data-scope gate decides the *rows* — object-level via
    ``scope_subject_attr="employee"`` + ``check_object_scope(obj)`` on
    detail/approve, and explicitly via ``actor_can_access`` on CREATE (no object
    exists yet to hang ``WithinScope`` on).

The tenant is bound from the JWT by ``TenantMiddleware``; the scoped managers
auto-filter, so a cross-tenant row never resolves (404) and we never filter by
tenant by hand. Views stay thin: weight rules live in the serializers/validators,
actuals go through ``record_actual``, templates through ``instantiate_role_templates``.
Every consequential action audits BEFORE the side effect.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.concurrency import check_version
from apps.core.pagination import StandardResultsSetPagination
from apps.core.throttling import AI_THROTTLES
from apps.cycles.models import PerformanceCycle
from apps.identity.models import User
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin
from apps.rbac.scope import (
    Scope,
    actor_can_access,
    reporting_subtree_ids,
    scope_for_role,
)

from .models import Goal, Kpi, KpiMeasurement, KpiTemplate
from .serializers import (
    GoalSerializer,
    GoalUpdateSerializer,
    KpiMeasurementSerializer,
    KpiSerializer,
    KpiTemplateSerializer,
)
from .services import add_goal_update, record_actual
from .templates import instantiate_role_templates
from .validators import assert_kpi_weights_complete


class GoalListCreateView(RBACMixin, APIView):
    """``GET, POST /api/goals/``.

    GET (VIEW_OWN_GOALS): goals filtered by the caller's data scope, with an
    optional ``?cycle=<id>`` filter. POST (MANAGE_REPORTS_GOALS): create a goal
    with nested KPIs in one transaction.
    """

    _caps = {"GET": Capability.VIEW_OWN_GOALS, "POST": Capability.MANAGE_REPORTS_GOALS}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        goals = Goal.objects.all()
        scope = scope_for_role(request.user.role)
        if scope is Scope.OWN:
            goals = goals.filter(employee_id=request.user.id)
        elif scope is Scope.TEAM:
            visible = reporting_subtree_ids(request.user) | {request.user.id}
            goals = goals.filter(employee_id__in=visible)
        # Scope.TENANT → all in tenant (scoped manager already isolates).
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            goals = goals.filter(cycle_id=cycle_id)
        # FKs for the *_name fields (one JOIN each) + prefetch kpis so
        # kpi_weight_total's sum doesn't fire a query per goal. Each KPI's
        # measurements are prefetched desc-ordered so the serializer's
        # `latest_actual` reads the current actual with NO per-KPI query (O(1)).
        goals = goals.select_related(
            "employee", "created_by", "approved_by"
        ).prefetch_related(
            Prefetch(
                "kpis",
                queryset=Kpi.objects.prefetch_related(
                    Prefetch(
                        "measurements",
                        queryset=KpiMeasurement.objects.order_by(
                            "-recorded_at", "-created_at"
                        ),
                    )
                ),
            )
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(goals, request, view=self)
        return paginator.get_paginated_response(GoalSerializer(page, many=True).data)

    def post(self, request):
        serializer = GoalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.validated_data["employee"]
        # Scope-on-CREATE: no object yet, so check the target employee explicitly.
        if not actor_can_access(request.user, employee):
            raise PermissionDenied("This record is outside your access scope.")
        # Audit BEFORE the create.
        record(
            action="goal.created",
            actor=request.user,
            target_type="goal",
            metadata={
                "employee_id": str(employee.id),
                "cycle_id": str(serializer.validated_data["cycle"].id),
                "title": serializer.validated_data.get("title"),
            },
        )
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GoalDetailView(RBACMixin, APIView):
    """``GET, PATCH, DELETE /api/goals/<pk>`` — retrieve / update / soft-delete a
    goal. GET=VIEW_OWN_GOALS, PATCH/DELETE=MANAGE_REPORTS_GOALS; object-level
    scope on all three (``scope_subject_attr="employee"``)."""

    scope_subject_attr = "employee"
    _caps = {
        "GET": Capability.VIEW_OWN_GOALS,
        "PATCH": Capability.MANAGE_REPORTS_GOALS,
        "DELETE": Capability.MANAGE_REPORTS_GOALS,
    }

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def _get_goal(self, pk):
        goal = get_object_or_404(Goal.objects.all(), pk=pk)
        self.check_object_scope(goal)
        return goal

    def get(self, request, pk):
        return Response(GoalSerializer(self._get_goal(pk)).data)

    def patch(self, request, pk):
        goal = self._get_goal(pk)
        # Optimistic lock: a stale `version` → 409 (no silent last-writer-wins).
        check_version(goal, request.data)
        # Only the goal's own fields are patchable here (title/description/
        # objective/weight/status); KPIs are edited via the KPI sub-resources.
        serializer = GoalSerializer(goal, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # Bump the version atomically with the field update (server-controlled).
        serializer.save(version=goal.version + 1)
        return Response(serializer.data)

    def delete(self, request, pk):
        goal = self._get_goal(pk)
        goal.delete()  # soft delete — stamps deleted_at
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoalApproveView(RBACMixin, APIView):
    """``POST /api/goals/<pk>/approve`` — manager approval transition
    (APPROVE_GOALS, object scope). Stamps ``approved_by`` + ``approved_at``."""

    required_capability = Capability.APPROVE_GOALS
    scope_subject_attr = "employee"

    def post(self, request, pk):
        goal = get_object_or_404(Goal.objects.all(), pk=pk)
        self.check_object_scope(goal)
        # Audit BEFORE the approval side effect.
        record(
            action="goal.approved",
            actor=request.user,
            target_type="goal",
            target_id=goal.id,
        )
        goal.approved_by = request.user
        goal.approved_at = timezone.now()
        goal.save()
        return Response(GoalSerializer(goal).data)


class GoalUpdateListCreateView(RBACMixin, APIView):
    """``GET, POST /api/goals/<goal_id>/updates`` — the goal's progress timeline
    (AGENT_UX_V3 Part 2.3). GET=VIEW_OWN_GOALS, POST=UPDATE_OWN_ACTUALS; object scope
    on the goal's employee (own goal for an employee, subtree for a manager)."""

    scope_subject_attr = "employee"
    _caps = {"GET": Capability.VIEW_OWN_GOALS, "POST": Capability.UPDATE_OWN_ACTUALS}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def _goal(self, goal_id):
        goal = get_object_or_404(Goal.objects.all(), pk=goal_id)
        self.check_object_scope(goal)
        return goal

    def get(self, request, goal_id):
        goal = self._goal(goal_id)
        updates = goal.updates.select_related("author").all()
        return Response(GoalUpdateSerializer(updates, many=True).data)

    def post(self, request, goal_id):
        goal = self._goal(goal_id)
        update = add_goal_update(request.user, goal, request.data.get("text", ""))
        return Response(GoalUpdateSerializer(update).data, status=status.HTTP_201_CREATED)


class GoalKpiListCreateView(RBACMixin, APIView):
    """``GET, POST /api/goals/<goal_id>/kpis`` — list / create KPIs under a goal
    (MANAGE_REPORTS_GOALS). Object scope via the parent goal's employee.

    On create: ``target_value`` must be > 0, and after adding the KPI the goal's
    KPI weights must sum to 100.00 — done in a transaction so a non-100 total
    rolls back and returns 400.
    """

    required_capability = Capability.MANAGE_REPORTS_GOALS
    # check_object_scope(goal) resolves the subject via this attr: goal.employee
    # is the User whose scope the caller must satisfy.
    scope_subject_attr = "employee"

    def _get_goal(self, goal_id):
        goal = get_object_or_404(Goal.objects.all(), pk=goal_id)
        self.check_object_scope(goal)
        return goal

    def get(self, request, goal_id):
        goal = self._get_goal(goal_id)
        return Response(KpiSerializer(goal.kpis.all(), many=True).data)

    def post(self, request, goal_id):
        goal = self._get_goal(goal_id)
        serializer = KpiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            _lock_goal(goal)  # serialise concurrent weight changes on this goal
            serializer.save(goal=goal)
            # The goal's KPIs must now sum to exactly 100.00; a non-100 total
            # raises a DRF ValidationError (400) and rolls the insert back.
            _assert_goal_weight_complete(goal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class KpiDetailView(RBACMixin, APIView):
    """``GET, PATCH, DELETE /api/goals/kpis/<pk>`` — KPI detail
    (MANAGE_REPORTS_GOALS). Object scope via ``kpi.employee``.

    A weight PATCH or a DELETE re-validates the parent goal's KPI sum to 100.00
    in a transaction (rolls back → 400 if it would break the rule)."""

    required_capability = Capability.MANAGE_REPORTS_GOALS
    scope_subject_attr = "employee"

    def _get_kpi(self, pk):
        kpi = get_object_or_404(Kpi.objects.all(), pk=pk)
        self.check_object_scope(kpi)
        return kpi

    def get(self, request, pk):
        return Response(KpiSerializer(self._get_kpi(pk)).data)

    def patch(self, request, pk):
        kpi = self._get_kpi(pk)
        serializer = KpiSerializer(kpi, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            _lock_goal(kpi.goal)  # serialise concurrent weight changes on this goal
            serializer.save()
            # If the weight moved, the parent goal must still sum to 100.00.
            if "weight" in serializer.validated_data:
                _assert_goal_weight_complete(kpi.goal)
        return Response(serializer.data)

    def delete(self, request, pk):
        kpi = self._get_kpi(pk)
        goal = kpi.goal
        with transaction.atomic():
            _lock_goal(goal)  # serialise concurrent weight changes on this goal
            kpi.delete()  # soft delete
            # After removal the remaining KPIs must still sum to 100.00.
            _assert_goal_weight_complete(goal)
        return Response(status=status.HTTP_204_NO_CONTENT)


class KpiActualsView(RBACMixin, APIView):
    """``POST /api/goals/kpis/<kpi_id>/actuals`` — record an actual for the
    caller's OWN KPI (the lightweight mobile path; UPDATE_OWN_ACTUALS).

    OWN is enforced EXPLICITLY: the KPI's ``goal.employee_id`` must equal the
    caller — this is NOT role-based scope, so a manager cannot use THIS endpoint
    for a report (they manage report actuals via the goal/KPI endpoints).
    """

    required_capability = Capability.UPDATE_OWN_ACTUALS

    def post(self, request, kpi_id):
        kpi = get_object_or_404(Kpi.objects.all(), pk=kpi_id)
        # Explicit OWN check — not actor_can_access (a manager must NOT pass here).
        if kpi.goal.employee_id != request.user.id:
            raise PermissionDenied("You can only record actuals on your own KPIs.")
        value = request.data.get("value")
        if value is None:
            raise ValidationError({"value": "This field is required."})
        # Audit BEFORE the write.
        record(
            action="actual.recorded",
            actor=request.user,
            target_type="kpi",
            target_id=kpi.id,
            metadata={"value": str(value)},
        )
        measurement = record_actual(
            kpi,
            value,
            source=KpiMeasurement.Source.MANUAL,
            recorded_by=request.user,
        )
        return Response(
            KpiMeasurementSerializer(measurement).data, status=status.HTTP_201_CREATED
        )


class KpiTemplateListView(RBACMixin, APIView):
    """``GET /api/goals/templates/`` — the tenant's KPI template catalogue
    (MANAGE_KPI_TEMPLATES, HRBP/Admin)."""

    required_capability = Capability.MANAGE_KPI_TEMPLATES

    def get(self, request):
        templates = KpiTemplate.objects.all()
        return Response(KpiTemplateSerializer(templates, many=True).data)


class KpiTemplateInstantiateView(RBACMixin, APIView):
    """``POST /api/goals/templates/instantiate`` — instantiate a role's templates
    into a new (weight-complete) goal (MANAGE_KPI_TEMPLATES).

    Body: ``{employee, cycle, role?(default employee.role), goal_title?}``. The
    target employee is scope-checked explicitly (no object yet).
    """

    required_capability = Capability.MANAGE_KPI_TEMPLATES

    def post(self, request):
        employee = get_object_or_404(User.objects.all(), pk=request.data.get("employee"))
        cycle = get_object_or_404(
            PerformanceCycle.objects.all(), pk=request.data.get("cycle")
        )
        # Scope-check the target employee (no object exists yet).
        if not actor_can_access(request.user, employee):
            raise PermissionDenied("This record is outside your access scope.")
        role = request.data.get("role") or employee.role
        # Audit BEFORE the create.
        record(
            action="goal.created",
            actor=request.user,
            target_type="goal",
            metadata={
                "employee_id": str(employee.id),
                "cycle_id": str(cycle.id),
                "role": str(role),
                "source": "template_instantiate",
            },
        )
        goal = instantiate_role_templates(
            employee=employee, cycle=cycle, created_by=request.user, role=role
        )
        return Response(GoalSerializer(goal).data, status=status.HTTP_201_CREATED)


class GoalAIDraftView(RBACMixin, APIView):
    """``POST /api/goals/ai-draft`` (MANAGE_REPORTS_GOALS) — draft a SMART goal from a
    one-line intent via the AI Goal-writer (RW_BUILD_5). Returns an editable DRAFT
    (title, objective, KPIs); **nothing is persisted** — the human edits it and creates
    the goal through the normal (scope-gated, audited) create endpoint. The draft flows
    through the LLMGateway (budget/scrub/validate/meter); maps the result to HTTP: 503
    (no provider), 429 (over budget). AI-throttled."""

    required_capability = Capability.MANAGE_REPORTS_GOALS
    throttle_classes = AI_THROTTLES

    def post(self, request):
        intent = (request.data.get("prompt") or "").strip()
        if not intent:
            return Response({"detail": "prompt is required."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.ai.agents.goal_writer import draft_goal

        out = draft_goal(request.user, intent)
        if out["status"] == "not_configured":
            return Response(
                {"detail": "The AI goal-writer is not configured (no LLM provider)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if out["status"] == "budget":
            return Response(
                {"detail": "AI budget exhausted for this window.", "errors": out.get("errors")},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if out["status"] == "error":
            return Response(
                {"detail": f"AI draft unavailable: {out.get('detail')}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(out)


def _lock_goal(goal):
    """Take a row lock on the goal (BUILD_4) for a KPI weight critical section.

    The KPI weight-sum invariant (= 100.00) is read-modify-write across a goal's
    KPIs: two concurrent KPI adds/edits could each read a valid sum and both
    commit, corrupting the total. ``select_for_update`` serialises them — the
    second waits, then re-validates against the first's committed change. Hits
    the PRIMARY DB (the router routes a write/locked read to default)."""
    Goal.objects.select_for_update().filter(pk=goal.pk).first()


def _assert_goal_weight_complete(goal):
    """Re-validate a goal's KPI weight sum (= 100.00), re-raising the validator's
    django error as a DRF 400 so the transaction rolls back with a clear message.

    ``assert_kpi_weights_complete`` reads ``goal.kpis.all()`` fresh from the DB,
    so a just-added / just-removed / re-weighted KPI is reflected.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    try:
        assert_kpi_weights_complete(goal)
    except DjangoValidationError as exc:
        raise ValidationError({"kpis": exc.messages})
