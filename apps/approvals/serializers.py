"""
Approval-workflow serializers — SHAPE only; routing/auth/legality live in the
engine (``engine.py``) and the RBAC layer, never here.

Two halves:
  * the TEMPLATE (read+write): ``WorkflowSerializer`` / ``StepSerializer`` for
    reads, ``WorkflowCreateSerializer`` for the nested-write create path. Step
    edits via PATCH are deliberately OUT OF SCOPE (see views) — PATCH touches
    only the workflow's top-level fields.
  * the RUNNING INSTANCE (read-only): ``RouteSerializer`` /
    ``StepInstanceSerializer`` for the tracker, ``InboxItemSerializer`` for an
    approver's actionable queue.

No serializer ever accepts a server-owned field (``initiated_by``,
``decided_by``, ``started_at``, route/instance status): the engine stamps those.
``tenant`` is never accepted or echoed — it is bound from the request.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.core.display import person_label

from .models import (
    ApprovalRoute,
    ApprovalStep,
    ApprovalStepInstance,
    ApprovalWorkflow,
)


class StepSerializer(serializers.ModelSerializer):
    """A template step. Used for nested reads on a workflow and (with the same
    field set) for the nested write inside ``WorkflowCreateSerializer``.

    ``approver_user`` / ``escalation_user`` are plain UUIDs on the wire — the
    view resolves them through the TENANT-SCOPED ``User`` manager so a
    cross-tenant id 404s (it never leaks existence as a 400 on the FK)."""

    approver_user = serializers.UUIDField(required=False, allow_null=True)
    escalation_user = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = ApprovalStep
        fields = [
            "id",
            "order",
            "approver_kind",
            "approver_role",
            "approver_user",
            "required",
            "timeout_hours",
            "escalation_role",
            "escalation_user",
        ]
        read_only_fields = ["id"]


class WorkflowSerializer(serializers.ModelSerializer):
    """Read shape for a :class:`ApprovalWorkflow`, with its ordered steps nested.

    ``active`` is read-only here: it is flipped exclusively via the
    activate/deactivate endpoints (which audit + enforce at-most-one-active),
    never by a blind PATCH of this serializer."""

    steps = StepSerializer(many=True, read_only=True)

    class Meta:
        model = ApprovalWorkflow
        fields = ["id", "name", "artifact_type", "mode", "active", "steps", "created_at"]
        read_only_fields = ["id", "active", "steps", "created_at"]


class WorkflowUpdateSerializer(serializers.ModelSerializer):
    """PATCH shape — top-level workflow fields ONLY (``name`` / ``mode``).

    ``artifact_type`` is immutable after creation (a route snapshots its type;
    re-typing a workflow would orphan its semantics). ``active`` and step edits
    are out of scope here — see the activate/deactivate endpoints and the
    create-replace path."""

    class Meta:
        model = ApprovalWorkflow
        fields = ["name", "mode"]
        extra_kwargs = {"name": {"required": False}, "mode": {"required": False}}


class WorkflowCreateSerializer(serializers.ModelSerializer):
    """POST shape: a workflow WITH its steps in one body. ``active`` is an
    optional input flag — when true the view calls ``engine.activate_workflow``
    AFTER creation so the workflow becomes the sole active one for its type.

    At least one step is required (a step-less workflow is unroutable — the
    engine raises 422 at start; we reject it up front instead)."""

    steps = StepSerializer(many=True)
    active = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = ApprovalWorkflow
        fields = ["name", "artifact_type", "mode", "active", "steps"]

    def validate_steps(self, steps):
        if not steps:
            raise serializers.ValidationError("A workflow must define at least one step.")
        return steps


class StepInstanceSerializer(serializers.ModelSerializer):
    """Read-only running decision slot for the route tracker / inbox.
    ``approver``/``decided_by`` carry resolved ``*_name`` labels (a role-slot step
    may have no named approver — then ``approver_name`` is null and the UI shows
    the role)."""

    approver_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalStepInstance
        fields = [
            "id",
            "order",
            "approver",
            "approver_name",
            "approver_role",
            "required",
            "status",
            "due_at",
            "decided_by",
            "decided_by_name",
            "decided_at",
            "comment",
            "escalated",
        ]
        read_only_fields = fields

    def get_approver_name(self, obj) -> str | None:
        return person_label(obj.approver) if obj.approver_id else None

    def get_decided_by_name(self, obj) -> str | None:
        return person_label(obj.decided_by) if obj.decided_by_id else None


class RouteSerializer(serializers.ModelSerializer):
    """Read-only route tracker: the route header + its ordered step instances."""

    step_instances = StepInstanceSerializer(many=True, read_only=True)
    initiated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRoute
        fields = [
            "id",
            "workflow",
            "artifact_type",
            "artifact_id",
            "mode",
            "status",
            "initiated_by",
            "initiated_by_name",
            "started_at",
            "completed_at",
            "step_instances",
        ]
        read_only_fields = fields

    def get_initiated_by_name(self, obj) -> str | None:
        return person_label(obj.initiated_by) if obj.initiated_by_id else None


class InboxItemSerializer(serializers.ModelSerializer):
    """One actionable item in an approver's inbox: the pending step instance plus
    enough of its route to act on it (artifact type/id + the route id)."""

    route = serializers.UUIDField(source="route_id", read_only=True)
    artifact_type = serializers.CharField(source="route.artifact_type", read_only=True)
    artifact_id = serializers.UUIDField(source="route.artifact_id", read_only=True)
    approver_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalStepInstance
        fields = [
            "id",
            "route",
            "artifact_type",
            "artifact_id",
            "order",
            "approver",
            "approver_name",
            "approver_role",
            "required",
            "status",
            "due_at",
        ]
        read_only_fields = fields

    def get_approver_name(self, obj) -> str | None:
        return person_label(obj.approver) if obj.approver_id else None
