"""
Succession & Talent — the MOST SENSITIVE data in the system (readiness, 9-box,
flight-risk). Management-only by construction (see ``permissions.py``); there is
NO employee access to any of it.

Four models, all :class:`~apps.tenancy.models.TenantScopedModel`:
  * ``CriticalRole`` — a registered critical role + its knowledge-risk flag.
  * ``BenchCandidate`` — a successor candidate for a critical role + readiness.
  * ``NineBoxPlacement`` — an employee's 9-box cell for a cycle (performance band
    DERIVED from the Module-2 CycleScore; potential band HUMAN-assigned).
  * ``SuccessionPlan`` — the HITL-gated, published analysis for a critical role.

Performance is read from Module-2 ``CycleScore`` (the T-score); readiness/ranking/
coverage are DETERMINISTIC (``engine.py``) and always available. Agent 4
(Module 10) only ENRICHES — the deterministic baseline is core, never faked.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class CriticalRole(TenantScopedModel):
    """A role flagged as critical, with a knowledge-risk assessment."""

    class Criticality(models.TextChoices):
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class KnowledgeRisk(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=255)
    #: Optional link to the Module-7 Position this role corresponds to.
    position = models.ForeignKey(
        "org.Position", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The current holder of the role (nullable — the role may be vacant).
    incumbent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="critical_roles_held",
    )
    criticality = models.CharField(
        max_length=8, choices=Criticality.choices, default=Criticality.HIGH
    )
    knowledge_risk = models.CharField(
        max_length=8, choices=KnowledgeRisk.choices, default=KnowledgeRisk.LOW
    )
    risk_notes = models.TextField(blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="critical_roles_marked",
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "succession_critical_role"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="ix_critrole_status"),
        ]

    def __str__(self):
        return f"{self.name} [{self.criticality}/{self.status}]"


class BenchCandidate(TenantScopedModel):
    """A successor candidate on a critical role's bench, with readiness."""

    class Readiness(models.TextChoices):
        READY_NOW = "READY_NOW", "Ready now"
        READY_SOON = "READY_SOON", "Ready soon"
        DEVELOPING = "DEVELOPING", "Developing"
        NOT_READY = "NOT_READY", "Not ready"

    critical_role = models.ForeignKey(
        "succession.CriticalRole", on_delete=models.CASCADE, related_name="bench"
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bench_entries"
    )
    readiness = models.CharField(
        max_length=12, choices=Readiness.choices, default=Readiness.NOT_READY
    )
    #: An HRBP override STICKS — a re-generate never recomputes it away.
    readiness_overridden = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bench_candidates_added",
    )

    class Meta:
        db_table = "succession_bench_candidate"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "critical_role", "candidate"],
                name="uq_bench_role_candidate",
            )
        ]

    def __str__(self):
        return f"bench(role={self.critical_role_id}, cand={self.candidate_id})={self.readiness}"


class NineBoxPlacement(TenantScopedModel):
    """An employee's 9-box cell for one cycle. Performance band is DERIVED from
    the Module-2 CycleScore; potential band is HUMAN-assigned by HRBP/Manager."""

    class Band(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ninebox_placements"
    )
    cycle = models.ForeignKey(
        "cycles.PerformanceCycle", on_delete=models.CASCADE, related_name="ninebox_placements"
    )
    performance_band = models.CharField(max_length=8, choices=Band.choices)
    potential_band = models.CharField(max_length=8, choices=Band.choices)
    #: 1–9, derived from (performance_band, potential_band) — see engine.compute_box.
    box = models.PositiveSmallIntegerField()
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ninebox_assessments",
    )
    assessed_at = models.DateTimeField()

    class Meta:
        db_table = "succession_ninebox"
        ordering = ["-assessed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee", "cycle"], name="uq_ninebox_emp_cycle"
            )
        ]

    def __str__(self):
        return f"9box(emp={self.employee_id}, cycle={self.cycle_id})=box{self.box}"


class SuccessionPlan(TenantScopedModel):
    """The HITL-gated analysis for a critical role: generated PENDING_HUMAN_REVIEW,
    reviewed by an HRBP, then published to the dashboard."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW", "Pending human review"
        PUBLISHED = "PUBLISHED", "Published"

    class Coverage(models.TextChoices):
        RED = "RED", "Red (inadequate)"
        AMBER = "AMBER", "Amber"
        GREEN = "GREEN", "Green"

    class Source(models.TextChoices):
        DETERMINISTIC = "DETERMINISTIC", "Deterministic engine"
        AI = "AI", "Agent 4 (Module 10)"

    critical_role = models.ForeignKey(
        "succession.CriticalRole", on_delete=models.CASCADE, related_name="plans"
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING_HUMAN_REVIEW
    )
    #: Ordered snapshot of candidates + readiness at generation time.
    ranked_bench = models.JSONField(default=list)
    coverage_status = models.CharField(max_length=8, choices=Coverage.choices)
    red_flags = models.JSONField(default=list)
    #: HRBP-added action items during review.
    action_items = models.JSONField(default=list)
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.DETERMINISTIC
    )
    #: Agent-4 only (Module 10); null for the deterministic baseline.
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    generated_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="succession_plans_reviewed",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "succession_plan"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="ix_succplan_status"),
        ]

    def __str__(self):
        return f"plan(role={self.critical_role_id})=[{self.status}/{self.coverage_status}]"
