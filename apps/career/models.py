"""
Career Development (Roadmap LITE) — advisory-only, NEVER auto-promotion.

Three models, all :class:`~apps.tenancy.models.TenantScopedModel`:
  * ``TargetRoleSelection`` — an employee's chosen target role (a PUBLISHED
    ``jd.JobDescription`` OR an ``org.Position`` profile; exactly one). Who
    selected it + when are server-set.
  * ``DevelopmentRoadmap`` — a deterministic (or, in Module 10, AI-enriched)
    tiered development path toward the target. ``advisory`` is ALWAYS True and is
    enforced at the DB with a CHECK constraint — a structural guarantee that this
    feature can never become an auto-promotion mechanism.
  * ``RoadmapProgress`` — per-tier progress (the employee/manager marks tiers
    NOT_STARTED → IN_PROGRESS → DONE).

THE DATA BOUNDARY: the roadmap stores ONLY the employee's own performance-derived
gap (performance band, weak goal categories) + advisory tiers. It never stores or
exposes the sensitive succession surface (bench / 9-box potential / coverage /
other employees) — see ``engine.py`` and ``constants.py``.

A target is modelled as a nullable FK PAIR (``target_jd`` / ``target_position``),
exactly one set (validated in the service). "One ACTIVE roadmap per (tenant,
employee, target)" is a code-enforced invariant (the services upsert the ACTIVE
row), not a DB unique constraint — MySQL's NULL-distinct semantics make a unique
key over a nullable FK pair unable to express it, the same pattern documented for
Modules 5/7.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class TargetRoleSelection(TenantScopedModel):
    """An employee's selected target role — a PUBLISHED JD or an org Position
    (exactly one). The employee may select their own; a manager/HRBP may select
    for someone in scope. ``selected_by`` + ``selected_at`` are server-set."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="career_target_selections",
    )
    #: The target role profile — EXACTLY ONE of these is set (service-validated).
    target_jd = models.ForeignKey(
        "jd.JobDescription", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    target_position = models.ForeignKey(
        "org.Position", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="career_targets_selected",
    )
    selected_at = models.DateTimeField()

    class Meta:
        db_table = "career_target_selection"
        ordering = ["-selected_at"]
        indexes = [
            models.Index(fields=["tenant", "employee"], name="ix_career_target_emp"),
        ]

    def __str__(self):
        target = self.target_jd_id or self.target_position_id
        return f"target(emp={self.employee_id})={target}"


class DevelopmentRoadmap(TenantScopedModel):
    """A deterministic, advisory tiered development path toward a target role.

    ``advisory`` is ALWAYS True (DB CHECK enforced) — this is a coaching aid, never
    an auto-promotion. The DETERMINISTIC roadmap is the always-available baseline;
    Agent (Module 10) only enriches into a NEW ``source=AI`` roadmap.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    class Source(models.TextChoices):
        DETERMINISTIC = "DETERMINISTIC", "Deterministic engine"
        AI = "AI", "Career Roadmap agent (Module 10)"

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="development_roadmaps",
    )
    target_jd = models.ForeignKey(
        "jd.JobDescription", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    target_position = models.ForeignKey(
        "org.Position", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The selection that spawned this roadmap (provenance; nullable on SET_NULL).
    selection = models.ForeignKey(
        "career.TargetRoleSelection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roadmaps",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    #: Ordered development tiers: [{"index", "title", "detail", "basis"}].
    tiers = models.JSONField(default=list)
    #: The employee's own performance-derived gap snapshot at generation time
    #: (performance band, required band, band gap, weak goal categories). NEVER
    #: contains succession potential/readiness/bench data — see engine.py.
    skill_gap = models.JSONField(default=dict)
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.DETERMINISTIC
    )
    #: ALWAYS True — advisory only, never auto-promotion (DB CHECK enforced).
    advisory = models.BooleanField(default=True)
    #: Agent (Module 10) only; null for the deterministic baseline.
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    generated_at = models.DateTimeField()
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roadmaps_generated",
    )

    class Meta:
        db_table = "career_development_roadmap"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["tenant", "employee", "status"], name="ix_roadmap_emp_status"),
        ]
        constraints = [
            # Structural guarantee that a development roadmap is ALWAYS advisory —
            # the feature can never silently become an auto-promotion mechanism.
            models.CheckConstraint(
                check=models.Q(advisory=True), name="ck_roadmap_advisory_always_true"
            ),
        ]

    def __str__(self):
        target = self.target_jd_id or self.target_position_id
        return f"roadmap(emp={self.employee_id} -> {target}) [{self.status}/{self.source}]"


class RoadmapProgress(TenantScopedModel):
    """Per-tier progress on a development roadmap (unique per roadmap+tier)."""

    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        DONE = "DONE", "Done"

    roadmap = models.ForeignKey(
        "career.DevelopmentRoadmap", on_delete=models.CASCADE, related_name="progress"
    )
    tier_index = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.NOT_STARTED
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roadmap_progress_updates",
    )

    class Meta:
        db_table = "career_roadmap_progress"
        ordering = ["tier_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "roadmap", "tier_index"], name="uq_progress_roadmap_tier"
            )
        ]

    def __str__(self):
        return f"progress(roadmap={self.roadmap_id}, tier={self.tier_index})={self.status}"
