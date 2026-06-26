"""
Weekly Check-ins (RW_BUILD_3) — the lightweight engagement loop: an employee writes
a short weekly check-in (mood, wins, blockers, learning, a few priorities), and their
manager reads + responds. It is NOT anonymous and NOT a review — it FEEDS review
evidence but never duplicates review/goal state (goal progress is PULLED read-only
from the goals engine; see services).

Scope: an employee writes/reads their OWN check-ins; their manager reads + responds
within their reporting subtree (cross-manager → 404). Tenant isolation rides on the
``TenantScopedManager``.
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.tenancy.models import TenantScopedModel


class CheckIn(TenantScopedModel):
    """One employee's weekly check-in. One per (author, week_of)."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checkins"
    )
    #: The Monday (week start) the check-in covers — the natural cadence key.
    week_of = models.DateField()
    #: 1 (struggling) … 5 (great). The one structured signal.
    mood = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    wins = models.TextField(blank=True, default="")
    blockers = models.TextField(blank=True, default="")
    learning = models.TextField(blank=True, default="")

    class Meta:
        db_table = "checkin"
        ordering = ["-week_of"]
        constraints = [
            models.UniqueConstraint(fields=["author", "week_of"], name="uniq_checkin_author_week")
        ]
        indexes = [
            models.Index(fields=["tenant", "author", "-week_of"], name="ix_checkin_author_recent"),
        ]

    def __str__(self):
        return f"CheckIn({self.author_id}, {self.week_of})"


class CheckInPriority(TenantScopedModel):
    """A priority on a check-in. Carry-forward is a status, not a copy — the UI can
    pull last week's CARRY_FORWARD/ACTIVE items when starting a new check-in."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DONE = "DONE", "Done"
        CARRY_FORWARD = "CARRY_FORWARD", "Carry forward"

    check_in = models.ForeignKey(CheckIn, on_delete=models.CASCADE, related_name="priorities")
    text = models.CharField(max_length=280)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "checkin_priority"
        ordering = ["order", "created_at"]
        indexes = [models.Index(fields=["tenant", "check_in"], name="ix_checkinprio_card")]

    def __str__(self):
        return f"CheckInPriority({self.text[:20]!r}, {self.status})"


class ManagerResponse(TenantScopedModel):
    """A manager's response to a report's check-in (one per check-in)."""

    check_in = models.OneToOneField(
        CheckIn, on_delete=models.CASCADE, related_name="response"
    )
    responder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checkin_responses"
    )
    comment = models.TextField(blank=True, default="")
    reaction = models.CharField(max_length=8, blank=True, default="")
    follow_up = models.BooleanField(default=False)
    add_to_one_on_one = models.BooleanField(default=False)

    class Meta:
        db_table = "checkin_manager_response"
        indexes = [models.Index(fields=["tenant", "check_in"], name="ix_checkinresp_card")]

    def __str__(self):
        return f"ManagerResponse({self.check_in_id}, by {self.responder_id})"
