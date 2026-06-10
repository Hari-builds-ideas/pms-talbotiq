"""
Live Org Chart — the reporting hierarchy is READ from ``User.manager`` (the
self-FK that has powered RBAC scope and approver resolution since Module 1); this
module does NOT duplicate it. Module 7 adds exactly one new model — ``Position``
— and an explicit, cycle-checked reassignment of ``User.manager`` (in
``reassign.py``); the tree itself is computed from the live identity graph.

``Position`` models the APPROVED headcount plan / vacancies, NOT the whole
roster: you do not create a Position for every employee. An OPEN position is a
vacancy reporting to its ``reports_to`` manager; filling it links the employee
and flips it to FILLED; closing it clears the vacancy.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class Position(TenantScopedModel):
    """An approved headcount slot — a vacancy (OPEN), a filled seat (FILLED), or
    a retired slot (CLOSED). Distinct from the live reporting tree, which is read
    from ``User.manager``."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open (vacancy)"
        FILLED = "FILLED", "Filled"
        CLOSED = "CLOSED", "Closed"

    title = models.CharField(max_length=255)
    #: The manager this role reports to (must be active + in-tenant when set).
    #: SET_NULL so soft-deleting a manager never blocks; a null reports_to is a
    #: tenant-level vacancy visible only to HRBP/Admin.
    reports_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incoming_positions",
    )
    department = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    #: Set when the position is filled — the employee who now holds the seat.
    filled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="filled_positions",
    )
    #: An optional link to a PUBLISHED JD (Module 6) describing the role.
    published_jd = models.ForeignKey(
        "jd.JobDescription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    opened_at = models.DateTimeField()
    filled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="positions_created",
    )

    class Meta:
        db_table = "org_position"
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="ix_position_status"),
            models.Index(fields=["tenant", "reports_to"], name="ix_position_reports_to"),
        ]

    def __str__(self):
        return f"{self.title} [{self.status}]"
