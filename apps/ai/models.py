"""
AI job tracking (BUILD_2) — the status record behind the async AI seams.

Every AI seam (review draft, feedback summary, succession enrich, JD generate,
career enrich) used to run SYNCHRONOUSLY inside the HTTP request, holding a
gunicorn worker for the whole (slow, retrying) Groq call. BUILD_2 moves them to
Celery: the endpoint creates an :class:`AIJob`, enqueues the work, and returns
``202`` immediately; the client polls the job for status + result.

The AIJob is a tenant-scoped CORRELATION/STATUS record, not the source of truth.
The artifact it produces (a Review, FeedbackSummary, SuccessionPlan,
JobDescription or DevelopmentRoadmap) remains the authoritative, tenant-scoped
row in its own table, locked ``PENDING_HUMAN_REVIEW`` exactly as before — async
changes WHEN/WHERE the work runs, never WHAT it produces or its HITL/metering/
anonymisation guarantees. The job references the artifact loosely
(``target_type`` + ``target_id``) precisely so it stays decoupled from those
tables (see DECISIONS.md D4 for why this over a GenericForeignKey).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class AIJob(TenantScopedModel):
    """One async AI run: its agent, target artifact, lifecycle status and result.

    Lifecycle: ``QUEUED`` (enqueued) → ``RUNNING`` (worker picked it up) →
    ``SUCCEEDED`` (artifact produced + PENDING) | ``DEGRADED`` (graceful
    non-result: no provider / over budget / global ceiling — the structured
    GatewayResult status is in ``error_code``, the artifact is untouched) |
    ``FAILED`` (a hard error; artifact left in its pre-AI state).
    """

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        DEGRADED = "DEGRADED", "Degraded"
        FAILED = "FAILED", "Failed"

    #: The human who requested the run (RBAC-accountable). Nullable so a job row
    #: survives the user's deactivation/removal as an audit trace.
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Which agent ran — e.g. ``agent1`` (review), ``agent3`` (feedback),
    #: ``agent4`` (succession), ``jd``, ``career``.
    agent_code = models.CharField(max_length=32)
    #: Loose reference to the produced/affected artifact (NOT a DB FK — see D4).
    #: ``target_type`` e.g. "review"; ``target_id`` the artifact UUID (may be set
    #: up front when a PENDING placeholder is created before the work runs).
    target_type = models.CharField(max_length=32)
    target_id = models.UUIDField(null=True, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    #: Result summary. ``confidence`` from the GatewayResult on success;
    #: ``token_ledger`` the usage row the gateway metered (best-effort link);
    #: ``error_code`` the structured status on DEGRADED/FAILED
    #: (NOT_CONFIGURED / BUDGET_EXCEEDED / PROVIDER_ERROR / SCHEMA_INVALID / ...).
    confidence = models.FloatField(null=True, blank=True)
    token_ledger = models.ForeignKey(
        "billing.TokenLedger", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    error_code = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "ai_job"
        ordering = ["-created_at"]
        indexes = [
            # The poll path: a tenant's recent jobs, and "latest job for an
            # artifact" — both tenant-leading, created_at-trailing.
            models.Index(fields=["tenant", "-created_at"], name="ix_aijob_tenant_recent"),
            models.Index(fields=["tenant", "target_type", "target_id"], name="ix_aijob_target"),
        ]

    def __str__(self):
        return f"AIJob({self.agent_code}, {self.target_type}:{self.target_id}) [{self.status}]"

    @property
    def is_terminal(self) -> bool:
        """True once the job has reached a final state (no further transitions)."""
        return self.status in {self.Status.SUCCEEDED, self.Status.DEGRADED, self.Status.FAILED}
