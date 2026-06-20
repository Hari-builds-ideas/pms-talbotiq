"""
Goals, KPIs, measurements and cycle scores.

Every model is a :class:`~apps.tenancy.models.TenantScopedModel` (UUID pk, tenant
FK, soft delete, scoped manager + write isolation). Every numeric weight / ratio /
value is ``Decimal`` — NEVER float — so scoring is exactly reproducible.

Scope note: ``Kpi``, ``KpiMeasurement`` and ``CycleScore`` expose an ``employee``
attribute (a User) so the RBAC ``WithinScope`` check (scope_subject_attr="employee")
resolves the subject uniformly across all goal-tree records.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.tenancy.models import TenantScopedModel

# Weight precision: 0.00–100.00, two decimal places, exact-Decimal "= 100.00" rule.
# Decimal limits (not int) so DRF's serializer DecimalField doesn't warn.
_WEIGHT_VALIDATORS = [MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
_POSITIVE_DECIMAL = [MinValueValidator(Decimal("0"))]


class Goal(TenantScopedModel):
    """An employee's goal/OKR within a cycle. ``weight`` is this goal's share of
    the employee's cycle score; an employee's ACTIVE goals must sum to 100.00."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ACHIEVED = "ACHIEVED", "Achieved"
        MISSED = "MISSED", "Missed"
        ARCHIVED = "ARCHIVED", "Archived"

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="goals"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_goals",
    )
    cycle = models.ForeignKey(
        "cycles.PerformanceCycle", on_delete=models.PROTECT, related_name="goals"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    objective = models.TextField(blank=True)  # the "O" in OKR
    weight = models.DecimalField(max_digits=6, decimal_places=2, validators=_WEIGHT_VALIDATORS)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_goals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    #: Optimistic-lock version (BUILD_4) — bumped on every plain-field PATCH; a
    #: stale version on update → 409. Goals are edited by managers/HRBP and are a
    #: classic last-writer-wins risk.
    version = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "goals_goal"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "cycle", "employee"], name="ix_goal_cohort"),
            # Serves the hottest Goal read — an employee's own goals and a
            # manager's team goals: WHERE tenant=? AND employee[_id in ...] ORDER
            # BY -created_at. The cycle-leading ix_goal_cohort can't serve an
            # employee filter, so this is the only employee-leading index.
            models.Index(fields=["tenant", "employee", "-created_at"], name="ix_goal_emp_recent"),
        ]

    def __str__(self):
        return f"{self.title} ({self.employee_id})"


class Kpi(TenantScopedModel):
    """A measurable KPI under a goal. A goal's KPIs' weights must sum to 100.00.
    ``target_value`` must be > 0 (validated)."""

    class Direction(models.TextChoices):
        INCREASING = "INCREASING", "Higher is better"
        DECREASING = "DECREASING", "Lower is better"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual entry"
        JIRA = "JIRA", "Jira"

    goal = models.ForeignKey("goals.Goal", on_delete=models.CASCADE, related_name="kpis")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, validators=_WEIGHT_VALIDATORS)
    # >0 enforced by validator + serializer; stored to 4 dp.
    target_value = models.DecimalField(
        max_digits=18, decimal_places=4, validators=_POSITIVE_DECIMAL
    )
    direction = models.CharField(
        max_length=16, choices=Direction.choices, default=Direction.INCREASING
    )
    unit = models.CharField(max_length=32, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    # Jira issue key / JQL when source=JIRA; null for manual.
    external_ref = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "goals_kpi"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.name} (goal={self.goal_id})"

    @property
    def employee(self):
        # Lets RBAC WithinScope resolve the subject uniformly (scope_subject_attr).
        return self.goal.employee


class KpiMeasurement(TenantScopedModel):
    """Append-style actual-value history for a KPI. The latest measurement (by
    ``recorded_at``) is the current actual the scoring engine reads."""

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual entry"
        JIRA = "JIRA", "Jira"
        SYSTEM = "SYSTEM", "System"

    kpi = models.ForeignKey("goals.Kpi", on_delete=models.CASCADE, related_name="measurements")
    value = models.DecimalField(max_digits=18, decimal_places=4)
    recorded_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kpi_measurements",
    )
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        db_table = "goals_kpimeasurement"
        ordering = ["-recorded_at", "-created_at"]
        indexes = [models.Index(fields=["tenant", "kpi", "-recorded_at"], name="ix_meas_latest")]

    def __str__(self):
        return f"{self.kpi_id}={self.value} @ {self.recorded_at:%Y-%m-%d}"

    @property
    def employee(self):
        return self.kpi.goal.employee


class CycleScore(TenantScopedModel):
    """The computed performance score for one employee in one cycle. Recomputed
    idempotently by the scoring engine (unique per tenant+employee+cycle)."""

    class Risk(models.TextChoices):
        ON_TRACK = "ON_TRACK", "On track"
        AT_RISK = "AT_RISK", "At risk"
        CRITICAL = "CRITICAL", "Critical"

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cycle_scores"
    )
    cycle = models.ForeignKey(
        "cycles.PerformanceCycle", on_delete=models.CASCADE, related_name="scores"
    )
    raw_score = models.DecimalField(max_digits=10, decimal_places=4)
    z_score = models.DecimalField(max_digits=10, decimal_places=4)
    t_score = models.DecimalField(max_digits=10, decimal_places=4)
    cohort_size = models.PositiveIntegerField()
    # Defaults to "tenant"; role-based cohorts can populate this later without a
    # migration (the engine groups by cohort_key within tenant+cycle).
    cohort_key = models.CharField(max_length=64, default="tenant")
    insufficient_cohort = models.BooleanField(default=False)
    risk_status = models.CharField(max_length=16, choices=Risk.choices, default=Risk.ON_TRACK)
    pace_behind = models.BooleanField(default=False)
    computed_at = models.DateTimeField()

    class Meta:
        db_table = "goals_cyclescore"
        ordering = ["-computed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee", "cycle"], name="uq_cyclescore_tenant_emp_cycle"
            )
        ]

    def __str__(self):
        return f"score(emp={self.employee_id}, cycle={self.cycle_id})={self.t_score} [{self.risk_status}]"


class KpiTemplate(TenantScopedModel):
    """Role-targeted reusable KPI definition. Seeded per tenant and instantiated
    into real Goal/KPI rows. Deterministic only (AI suggestion is Phase 2)."""

    class Direction(models.TextChoices):
        INCREASING = "INCREASING", "Higher is better"
        DECREASING = "DECREASING", "Lower is better"

    # Role this template targets (mirrors identity.User.Role string values).
    role = models.CharField(max_length=16)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_value = models.DecimalField(
        max_digits=18, decimal_places=4, validators=_POSITIVE_DECIMAL
    )
    direction = models.CharField(
        max_length=16, choices=Direction.choices, default=Direction.INCREASING
    )
    unit = models.CharField(max_length=32, blank=True)
    default_weight = models.DecimalField(
        max_digits=6, decimal_places=2, validators=_WEIGHT_VALIDATORS
    )

    class Meta:
        db_table = "goals_kpitemplate"
        ordering = ["role", "name"]

    def __str__(self):
        return f"{self.role}:{self.name}"
