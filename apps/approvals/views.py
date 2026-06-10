"""
Approval-workflows API — the HTTP surface of the Module-5 deterministic engine.

Views stay THIN on purpose (the house style from reviews/feedback):
  * routing, ordering, advancement and the auth-of-ASSIGNMENT (is this actor the
    assigned approver / an in-scope role-slot holder?) all live in
    ``engine.py``; the decision views only fast-fail the COARSE capability via
    ``RBACMixin`` and then hand the step to ``engine.record_decision`` — which
    raises 403 (not assigned / self-approval / cross-tenant) and 409
    (out-of-order / already decided / route done), mapped by DRF;
  * activation / at-most-one-active is the engine's (``activate_workflow``);
  * rows load through the TENANT-SCOPED managers, so a cross-tenant id simply
    404s — we never filter by tenant by hand;
  * serializers carry SHAPE only; no server-owned field is ever client-supplied.

Visibility on the read surfaces follows the spec: config holders (Admin/HRBP)
design and see everything tenant-wide; a route tracker is visible to its
initiator, any approver on it, or a config holder; the inbox is strictly the
caller's own actionable steps.
"""
from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.identity.models import User
from apps.rbac.matrix import Capability, role_has_capability
from apps.rbac.mixins import RBACMixin

from . import engine
from .models import (
    ApprovalRoute,
    ApprovalStep,
    ApprovalStepInstance,
    ApprovalWorkflow,
)
from .serializers import (
    InboxItemSerializer,
    RouteSerializer,
    StepInstanceSerializer,
    WorkflowCreateSerializer,
    WorkflowSerializer,
    WorkflowUpdateSerializer,
)

_NOT_VISIBLE = "This approval route is outside your access scope."


# ── workflow configuration (Admin / HRBP) ────────────────────────────────────


class WorkflowListCreateView(RBACMixin, APIView):
    """``GET, POST /api/approvals/workflows`` — CONFIGURE_APPROVAL_WORKFLOW.

    GET: every workflow in the tenant (the scoped manager isolates the tenant),
    each with its ordered steps. POST: create a workflow WITH nested steps in
    one transaction; ``active=true`` then makes it the sole active workflow for
    its artifact type (via ``engine.activate_workflow``).
    """

    required_capability = Capability.CONFIGURE_APPROVAL_WORKFLOW

    def get(self, request):
        workflows = ApprovalWorkflow.objects.all()
        return Response(WorkflowSerializer(workflows, many=True).data)

    def post(self, request):
        serializer = WorkflowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        steps = data["steps"]
        make_active = data.get("active", False)
        tenant_id = request.user.tenant_id

        with transaction.atomic():
            workflow = ApprovalWorkflow.objects.create(
                tenant_id=tenant_id,
                name=data["name"],
                artifact_type=data["artifact_type"],
                mode=data["mode"],
                active=False,  # activation is a separate, audited effect below
            )
            for step in steps:
                # Resolve named users through the TENANT-SCOPED manager: a
                # cross-tenant id 404s (never silently binds a foreign user).
                approver_user = self._resolve_user(step.get("approver_user"))
                escalation_user = self._resolve_user(step.get("escalation_user"))
                ApprovalStep.objects.create(
                    tenant_id=tenant_id,
                    workflow=workflow,
                    order=step["order"],
                    approver_kind=step["approver_kind"],
                    approver_role=step.get("approver_role"),
                    approver_user=approver_user,
                    required=step.get("required", True),
                    timeout_hours=step.get("timeout_hours"),
                    escalation_role=step.get("escalation_role"),
                    escalation_user=escalation_user,
                )

        if make_active:
            # Audit BEFORE the effect (CLAUDE.md rule), then flip via the engine
            # so at-most-one-active is enforced and the prior active deactivates.
            record(
                action="workflow.activated",
                actor=request.user,
                target_type="approval_workflow",
                target_id=workflow.id,
                metadata={"artifact_type": workflow.artifact_type},
                tenant=tenant_id,
            )
            engine.activate_workflow(workflow)
            workflow.refresh_from_db()

        return Response(
            WorkflowSerializer(workflow).data, status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _resolve_user(user_id):
        if user_id is None:
            return None
        return get_object_or_404(User.objects.all(), pk=user_id)


class WorkflowDetailView(RBACMixin, APIView):
    """``GET, PATCH, DELETE /api/approvals/workflows/<pk>`` —
    CONFIGURE_APPROVAL_WORKFLOW.

    GET retrieves the workflow with its steps. PATCH updates only top-level
    fields (``name`` / ``mode``) — step edits via PATCH are out of scope (replace
    by POSTing a fresh workflow). DELETE soft-deletes (the scoped manager hides
    soft-deleted rows). Cross-tenant id → 404.
    """

    required_capability = Capability.CONFIGURE_APPROVAL_WORKFLOW

    def get(self, request, pk):
        workflow = get_object_or_404(ApprovalWorkflow.objects.all(), pk=pk)
        return Response(WorkflowSerializer(workflow).data)

    def patch(self, request, pk):
        workflow = get_object_or_404(ApprovalWorkflow.objects.all(), pk=pk)
        serializer = WorkflowUpdateSerializer(workflow, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(WorkflowSerializer(workflow).data)

    def delete(self, request, pk):
        workflow = get_object_or_404(ApprovalWorkflow.objects.all(), pk=pk)
        record(
            action="workflow.deleted",
            actor=request.user,
            target_type="approval_workflow",
            target_id=workflow.id,
            metadata={"artifact_type": workflow.artifact_type},
            tenant=request.user.tenant_id,
        )
        workflow.delete()  # TenantScopedModel soft-deletes by default
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowActivateView(RBACMixin, APIView):
    """``POST /api/approvals/workflows/<pk>/activate`` —
    CONFIGURE_APPROVAL_WORKFLOW. Makes the workflow the sole active one for its
    type (``engine.activate_workflow`` deactivates the prior active). Audits
    ``workflow.activated`` BEFORE the effect."""

    required_capability = Capability.CONFIGURE_APPROVAL_WORKFLOW

    def post(self, request, pk):
        workflow = get_object_or_404(ApprovalWorkflow.objects.all(), pk=pk)
        record(
            action="workflow.activated",
            actor=request.user,
            target_type="approval_workflow",
            target_id=workflow.id,
            metadata={"artifact_type": workflow.artifact_type},
            tenant=request.user.tenant_id,
        )
        engine.activate_workflow(workflow)
        workflow.refresh_from_db()
        return Response(WorkflowSerializer(workflow).data)


class WorkflowDeactivateView(RBACMixin, APIView):
    """``POST /api/approvals/workflows/<pk>/deactivate`` —
    CONFIGURE_APPROVAL_WORKFLOW. Sets ``active=False`` (the artifact type then
    falls back to its non-routed path). Audits ``workflow.deactivated`` BEFORE
    the effect."""

    required_capability = Capability.CONFIGURE_APPROVAL_WORKFLOW

    def post(self, request, pk):
        workflow = get_object_or_404(ApprovalWorkflow.objects.all(), pk=pk)
        record(
            action="workflow.deactivated",
            actor=request.user,
            target_type="approval_workflow",
            target_id=workflow.id,
            metadata={"artifact_type": workflow.artifact_type},
            tenant=request.user.tenant_id,
        )
        workflow.active = False
        workflow.save(update_fields=["active", "updated_at"])
        return Response(WorkflowSerializer(workflow).data)


# ── the approver's inbox ──────────────────────────────────────────────────────


class InboxView(RBACMixin, APIView):
    """``GET /api/approvals/inbox`` — VIEW_APPROVAL_STATUS. The PENDING step
    instances awaiting the CURRENT user, across the tenant's IN_PROGRESS routes.

    Awaiting THIS user means: ``approver == request.user`` (NAMED / resolved
    MANAGER), OR a role-slot (``approver`` null) whose ``approver_role`` equals
    the user's role (HRBP/ADMIN tenant-wide). For a SEQUENTIAL route only the
    currently-active step (the lowest-order PENDING one) is surfaced — a waiting
    step-2 is not actionable yet, so it is filtered out in Python.
    """

    required_capability = Capability.VIEW_APPROVAL_STATUS

    def get(self, request):
        user = request.user
        pending = list(
            ApprovalStepInstance.objects.filter(
                status=ApprovalStepInstance.Status.PENDING,
                route__status=ApprovalRoute.Status.IN_PROGRESS,
            ).select_related("route")
        )
        # Awaiting THIS user: their named assignment OR their role-slot.
        mine = [
            step
            for step in pending
            if step.approver_id == user.id
            or (step.approver_id is None and step.approver_role == user.role)
        ]
        # SEQUENTIAL routes: keep only the active (lowest-order PENDING) step per
        # route, so a waiting later step is never surfaced as actionable.
        active_seq_step: dict = {}
        for step in pending:
            route = step.route
            if route.mode != ApprovalWorkflow.Mode.SEQUENTIAL:
                continue
            cur = active_seq_step.get(route.id)
            if cur is None or step.order < cur.order:
                active_seq_step[route.id] = step

        actionable = []
        for step in mine:
            route = step.route
            if route.mode == ApprovalWorkflow.Mode.SEQUENTIAL:
                active = active_seq_step.get(route.id)
                if active is None or active.id != step.id:
                    continue
            actionable.append(step)

        actionable.sort(key=lambda s: (s.route.started_at, s.order))
        return Response(InboxItemSerializer(actionable, many=True).data)


# ── the route tracker ─────────────────────────────────────────────────────────


def _can_view_route(user, route) -> bool:
    """Route visibility: the initiator, any approver on a step, or a config
    holder (Admin/HRBP) in the tenant. (The route is already tenant-scoped — a
    cross-tenant id never resolves.)"""
    if route.initiated_by_id == user.id:
        return True
    if role_has_capability(user.role, Capability.CONFIGURE_APPROVAL_WORKFLOW):
        return True
    return route.step_instances.filter(approver_id=user.id).exists()


class RouteListView(RBACMixin, APIView):
    """``GET /api/approvals/routes?artifact_type=&artifact_id=`` —
    VIEW_APPROVAL_STATUS. The route(s) for one artifact (both params REQUIRED),
    filtered to the routes the caller may view (same visibility as the tracker).
    """

    required_capability = Capability.VIEW_APPROVAL_STATUS

    def get(self, request):
        artifact_type = request.query_params.get("artifact_type")
        artifact_id = request.query_params.get("artifact_id")
        if not artifact_type or not artifact_id:
            raise ValidationError(
                {"detail": "artifact_type and artifact_id query params are required."}
            )
        routes = ApprovalRoute.objects.filter(
            artifact_type=artifact_type, artifact_id=artifact_id
        )
        visible = [r for r in routes if _can_view_route(request.user, r)]
        return Response(RouteSerializer(visible, many=True).data)


class RouteDetailView(RBACMixin, APIView):
    """``GET /api/approvals/routes/<pk>`` — VIEW_APPROVAL_STATUS. The route
    tracker: the route header + its ordered step instances. Visible to the
    initiator, any approver on it, or a config holder; anyone else → 403.
    Cross-tenant id → 404."""

    required_capability = Capability.VIEW_APPROVAL_STATUS

    def get(self, request, pk):
        route = get_object_or_404(ApprovalRoute.objects.all(), pk=pk)
        if not _can_view_route(request.user, route):
            raise PermissionDenied(_NOT_VISIBLE)
        return Response(RouteSerializer(route).data)


# ── deciding a step ───────────────────────────────────────────────────────────


class _StepDecisionView(RBACMixin, APIView):
    """Base for approve/reject: load the step through the scoped manager
    (cross-tenant → 404), then let the ENGINE decide.

    ``required_capability`` is only a cheap FAST-FAIL — ``record_decision``
    re-checks capability AND the auth-of-assignment, raising 403 (not the
    assigned approver / self-approval / cross-tenant) and 409 (out-of-order /
    already decided / route done), which DRF maps to the response.
    """

    required_capability = Capability.ACT_ON_APPROVAL_STEP
    decision: str = ""  # "APPROVE" / "REJECT"

    def post(self, request, pk):
        step = get_object_or_404(ApprovalStepInstance.objects.all(), pk=pk)
        step = engine.record_decision(
            step,
            request.user,
            self.decision,
            comment=request.data.get("comment", ""),
        )
        return Response(StepInstanceSerializer(step).data)


class StepApproveView(_StepDecisionView):
    """``POST /api/approvals/steps/<pk>/approve`` — ACT_ON_APPROVAL_STEP."""

    decision = "APPROVE"


class StepRejectView(_StepDecisionView):
    """``POST /api/approvals/steps/<pk>/reject`` — ACT_ON_APPROVAL_STEP."""

    decision = "REJECT"
