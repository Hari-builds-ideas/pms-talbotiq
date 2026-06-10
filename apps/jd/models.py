"""
JD Library — versioned job descriptions with a HITL gate and opt-in approval
routing (the second consumer of the Module-5 approval engine).

The MANUAL authoring path is fully functional now; the AI body text comes from
the JD Generator (Module 10) through the loud seam in ``generator.py`` —
Module 6 never fabricates a JD body.

Model split:
* ``JobDescription`` — the stable library entry. ``status`` tracks the WORKING
  version's lifecycle; ``current_version`` points at the live PUBLISHED version
  (null until first publish). Editing a published JD creates a NEW draft version
  and flips status back to DRAFT while ``current_version`` stays live, so the
  library never loses its published content mid-revision.
* ``JDVersion`` — an immutable-once-published body + the inputs snapshot used to
  author/generate it. A published version is frozen forever; the next edit makes
  a fresh draft version.

All models are :class:`~apps.tenancy.models.TenantScopedModel`.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class JobDescription(TenantScopedModel):
    """The stable library entry for a role's job description."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW", "Pending human review"
        IN_REVIEW = "IN_REVIEW", "In approval route"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manually authored"
        AI = "AI", "AI generated (Module 10)"

    title = models.CharField(max_length=255)
    level = models.CharField(max_length=64)
    department = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.DRAFT
    )
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.MANUAL)
    #: The live PUBLISHED version (null until first publish). Distinct from the
    #: working draft when a published JD is being revised.
    current_version = models.ForeignKey(
        "jd.JDVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jds_created",
    )
    #: Module 5 (opt-in): the in-flight approval route when approve is routed.
    approval_route = models.ForeignKey(
        "approvals.ApprovalRoute",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "jd_jobdescription"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="ix_jd_status"),
            models.Index(fields=["tenant", "title", "level"], name="ix_jd_title_level"),
        ]

    def __str__(self):
        return f"{self.title} ({self.level}) [{self.status}]"


class JDVersion(TenantScopedModel):
    """One immutable-once-published version of a JD body."""

    jd = models.ForeignKey(
        "jd.JobDescription", on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    #: {"summary": str, "responsibilities": [str], "must_haves": [str],
    #:  "nice_to_haves": [str]}
    body = models.JSONField(default=dict)
    #: The structured role inputs used to author/generate this version.
    inputs_snapshot = models.JSONField(default=dict, blank=True)
    #: Generator (Module 10) only; null for manual versions.
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    citations = models.JSONField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jd_versions_created",
    )

    class Meta:
        db_table = "jd_version"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "jd", "version_number"], name="uq_jdversion_jd_number"
            ),
        ]

    def __str__(self):
        return f"JD {self.jd_id} v{self.version_number}{' (published)' if self.is_published else ''}"


class JDTemplate(TenantScopedModel):
    """A reusable role-family scaffold seeded per tenant; instantiated into JDs."""

    role_family = models.CharField(max_length=128)
    title_pattern = models.CharField(max_length=255)
    level = models.CharField(max_length=64, blank=True)
    #: Default body scaffold: summary + responsibilities + must_haves + nice_to_haves.
    default_body = models.JSONField(default=dict)

    class Meta:
        db_table = "jd_template"
        ordering = ["role_family", "title_pattern"]

    def __str__(self):
        return f"{self.role_family}: {self.title_pattern}"


class JDRequest(TenantScopedModel):
    """A manager's request that HRBP/Admin author/generate a JD."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULFILLED = "FULFILLED", "Fulfilled"
        DECLINED = "DECLINED", "Declined"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="jd_requests"
    )
    title = models.CharField(max_length=255)
    level = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    #: Set when an HRBP fulfils the request by producing a JD.
    fulfilled_jd = models.ForeignKey(
        "jd.JobDescription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fulfilling_requests",
    )

    class Meta:
        db_table = "jd_request"
        ordering = ["-created_at"]

    def __str__(self):
        return f"JDRequest {self.title} [{self.status}]"
