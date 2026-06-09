"""
Performance cycles.

A ``PerformanceCycle`` is the (tenant-scoped) time window every goal and score is
attached to. Scoring is always scoped to (tenant, cycle). Deliberately minimal —
Module 4 (Reviews & Appraisal Cycles) extends this with the review state machine.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.tenancy.models import TenantScopedModel


class PerformanceCycle(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"

    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        db_table = "cycles_performancecycle"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} [{self.status}]"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "end_date must be on or after start_date."})

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    def elapsed_fraction(self, as_of=None) -> Decimal:
        """Fraction of [start_date, end_date] elapsed at ``as_of`` (default today),
        clamped to [0, 1]. Used by the scoring engine's pace-behind check.
        Returns a 4-dp Decimal — never a float."""
        as_of = as_of or timezone.now().date()
        if as_of <= self.start_date:
            return Decimal("0")
        if as_of >= self.end_date:
            return Decimal("1")
        total_days = (self.end_date - self.start_date).days
        if total_days <= 0:
            return Decimal("1")
        elapsed_days = (as_of - self.start_date).days
        return (Decimal(elapsed_days) / Decimal(total_days)).quantize(Decimal("0.0001"))
