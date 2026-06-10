"""
Configurable approval workflows — DELIBERATELY AI-FREE (the spec requires
approvals to be deterministic and auditable). No LLM, no agent seam.

Two layers:

* TEMPLATE — ``ApprovalWorkflow`` + ``ApprovalStep``: the configurable matrix an
  Admin/HRBP designs. At most ONE active workflow per (tenant, artifact_type).
* RUNNING INSTANCE — ``ApprovalRoute`` + ``ApprovalStepInstance``: a live routing
  of one artifact, snapshotted from the template at start (the instance is
  self-contained, so editing the template later never mutates an in-flight route).

Routing is OPT-IN and ADDITIVE: an artifact type (e.g. "review") routes only when
its tenant has an active workflow; otherwise the artifact's own module behaves
exactly as before (Module 3's single-step finalize). The engine
(``engine.py``) and the escalation beat task bind the tenant themselves.

At-most-one-active and one-active-route-per-artifact are enforced in the engine /
activate service (MySQL has no partial unique indexes), not by DB constraints.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class ApprovalWorkflow(TenantScopedModel):
    """The configurable matrix / template for one artifact type."""

    class Mode(models.TextChoices):
        SEQUENTIAL = "SEQUENTIAL", "Sequential"
        PARALLEL = "PARALLEL", "Parallel"

    name = models.CharField(max_length=255)
    #: e.g. "review", "jd", "record_amendment".
    artifact_type = models.CharField(max_length=64)
    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.SEQUENTIAL)
    active = models.BooleanField(default=False)

    class Meta:
        db_table = "approvals_workflow"
        ordering = ["artifact_type", "name"]
        indexes = [
            models.Index(fields=["tenant", "artifact_type", "active"], name="ix_wf_active"),
        ]

    def __str__(self):
        return f"{self.name} [{self.artifact_type}/{self.mode}{' ACTIVE' if self.active else ''}]"


class ApprovalStep(TenantScopedModel):
    """A template step: who approves, in what order, with what timeout/escalation."""

    class ApproverKind(models.TextChoices):
        ROLE = "ROLE", "Role"
        NAMED = "NAMED", "Named user"

    workflow = models.ForeignKey(
        "approvals.ApprovalWorkflow", on_delete=models.CASCADE, related_name="steps"
    )
    #: Sequence position for SEQUENTIAL; display order for PARALLEL.
    order = models.PositiveIntegerField()
    approver_kind = models.CharField(max_length=8, choices=ApproverKind.choices)
    #: For ROLE kind: MANAGER (→ subject's manager) / HRBP / ADMIN (role-slots).
    approver_role = models.CharField(max_length=16, null=True, blank=True)
    #: For NAMED kind: the specific approver.
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approval_steps_named",
    )
    #: PARALLEL quorum: a non-required step is advisory and does not block.
    required = models.BooleanField(default=True)
    timeout_hours = models.PositiveIntegerField(null=True, blank=True)
    escalation_role = models.CharField(max_length=16, null=True, blank=True)
    escalation_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approval_steps_escalation",
    )

    class Meta:
        db_table = "approvals_step"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workflow", "order"], name="uq_step_workflow_order"
            ),
        ]

    def __str__(self):
        target = self.approver_role if self.approver_kind == self.ApproverKind.ROLE else self.approver_user_id
        return f"step {self.order}: {self.approver_kind}={target}"


class ApprovalRoute(TenantScopedModel):
    """A running routing of ONE artifact through a workflow."""

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        ESCALATED = "ESCALATED", "Escalated"  # reserved: route stuck w/ no escalation target

    workflow = models.ForeignKey(
        "approvals.ApprovalWorkflow", on_delete=models.PROTECT, related_name="routes"
    )
    artifact_type = models.CharField(max_length=64)
    artifact_id = models.UUIDField()
    mode = models.CharField(max_length=12)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.IN_PROGRESS
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_routes_initiated",
    )
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "approvals_route"
        ordering = ["-started_at"]
        indexes = [
            models.Index(
                fields=["tenant", "artifact_type", "artifact_id", "status"],
                name="ix_route_artifact",
            ),
        ]

    def __str__(self):
        return f"route({self.artifact_type}:{self.artifact_id}) [{self.status}]"


class ApprovalStepInstance(TenantScopedModel):
    """A running decision slot. The decision lives here — one row per step.

    ``approver`` is the resolved user for NAMED/MANAGER steps; it is NULL for a
    role-slot (HRBP/ADMIN), where any in-scope holder of ``approver_role`` may
    act and the first to decide owns the slot. Escalation config + ``escalated``
    are snapshotted/flagged here so a running route is self-contained.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        ESCALATED = "ESCALATED", "Escalated"  # slot stuck w/ no escalation target
        SKIPPED = "SKIPPED", "Skipped"

    route = models.ForeignKey(
        "approvals.ApprovalRoute", on_delete=models.CASCADE, related_name="step_instances"
    )
    order = models.PositiveIntegerField()
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approval_step_instances",
    )
    approver_role = models.CharField(max_length=16, null=True, blank=True)
    required = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    due_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    # Escalation snapshot (from the template step) + whether this slot was
    # reassigned by the timeout escalation.
    timeout_hours = models.PositiveIntegerField(null=True, blank=True)
    escalation_role = models.CharField(max_length=16, null=True, blank=True)
    escalation_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approval_step_escalation_targets",
    )
    escalated = models.BooleanField(default=False)

    class Meta:
        db_table = "approvals_stepinstance"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "due_at"], name="ix_stepinst_due"),
            models.Index(fields=["tenant", "approver", "status"], name="ix_stepinst_inbox"),
        ]

    def __str__(self):
        return f"slot {self.order} of {self.route_id} [{self.status}]"
