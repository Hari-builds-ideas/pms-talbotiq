"""
360° / continuous feedback + anonymised summaries.

Every model is a :class:`~apps.tenancy.models.TenantScopedModel`. The headline
guarantee of this module is ANONYMISATION AT THE EGRESS BOUNDARY:

* The giver identity IS stored on :class:`Feedback` — needed for dedup, audit,
  and letting a giver edit their own item — but it is NEVER egressed. The only
  API surface that may show a giver's identity is the giver viewing their OWN
  feedback. Everything a recipient / HRBP / Agent 3 consumes goes through
  :func:`apps.feedback.anonymize.build_anonymized_payload`, which strips giver
  UUID/name/email and substitutes opaque per-cycle pseudonyms.
* PEER and UPWARD groups are included only when they reach the per-group
  minimum-volume threshold (``constants.MIN_FEEDBACK_VOLUME``, overridable per
  cycle) — one identifiable peer response is never egressed alone.
* A deterministic anonymity-breach guard runs BEFORE any LLM (Module 10's
  Agent 3 adds a post-LLM check on top).

MySQL note on the one-360-per-giver rule: ``uq_feedback_cycle_giver`` is a plain
unique constraint over (tenant, cycle, giver). MySQL treats NULLs as distinct in
unique indexes, so unlimited cycle-less CONTINUOUS feedback rows coexist while
uniqueness binds exactly when ``cycle`` is set — the partial-index semantics we
need without one.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class FeedbackCycle(TenantScopedModel):
    """A 360° collection window for ONE subject."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        COLLECTING = "COLLECTING", "Collecting"
        CLOSED = "CLOSED", "Closed"

    #: Whose feedback this cycle is ABOUT.
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedback_cycles"
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_cycles_opened",
    )
    #: Optional alignment to a performance cycle — not required (a 360 can run
    #: ad hoc, e.g. ahead of a promotion case).
    performance_cycle = models.ForeignKey(
        "cycles.PerformanceCycle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_cycles",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    #: Per-cycle override of constants.MIN_FEEDBACK_VOLUME (None = default).
    min_volume = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "feedback_cycle"
        ordering = ["-created_at"]

    def __str__(self):
        return f"360 for {self.subject_id} [{self.status}]"

    @property
    def employee(self):
        # Lets RBAC WithinScope resolve the subject uniformly.
        return self.subject

    @property
    def effective_min_volume(self):
        from .constants import MIN_FEEDBACK_VOLUME

        return self.min_volume if self.min_volume is not None else MIN_FEEDBACK_VOLUME


class FeedbackRequest(TenantScopedModel):
    """An invitation to give 360 feedback — the designated-reviewer flow.

    This is what AUTHORISES a non-manager peer to give feedback about the
    subject (Module 3 deferred exactly this here). The relationship is fixed by
    the inviter on the invitation, never client-supplied at submit time. The
    Slack push for "notify reviewers" is Module 12; for MVP the invitation is
    the in-app/DB notification.
    """

    class Relationship(models.TextChoices):
        SELF = "SELF", "Self"
        MANAGER = "MANAGER", "Manager"
        PEER = "PEER", "Peer"
        UPWARD = "UPWARD", "Upward"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted"
        DECLINED = "DECLINED", "Declined"

    cycle = models.ForeignKey(
        "feedback.FeedbackCycle", on_delete=models.CASCADE, related_name="requests"
    )
    giver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback_requests"
    )
    relationship = models.CharField(max_length=8, choices=Relationship.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = "feedback_request"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cycle", "giver"], name="uq_request_cycle_giver"
            ),
        ]

    def __str__(self):
        return f"{self.relationship} request to {self.giver_id} [{self.status}]"

    @property
    def employee(self):
        return self.cycle.subject


class Feedback(TenantScopedModel):
    """One feedback item — the sensitive record.

    ``giver`` is stored (dedup/audit/self-edit) but NEVER egressed except to the
    giver themselves; see the module docstring. ``sentiment`` stays null until
    Module 10's Fast-AI tagger. ``cycle`` is null for CONTINUOUS feedback.
    """

    class Relationship(models.TextChoices):
        SELF = "SELF", "Self"
        MANAGER = "MANAGER", "Manager"
        PEER = "PEER", "Peer"
        UPWARD = "UPWARD", "Upward"

    class Kind(models.TextChoices):
        THREE_SIXTY = "THREE_SIXTY", "360 cycle feedback"
        CONTINUOUS = "CONTINUOUS", "Continuous feedback"

    cycle = models.ForeignKey(
        "feedback.FeedbackCycle",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="items",
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedback_received"
    )
    giver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedback_given"
    )
    relationship = models.CharField(max_length=8, choices=Relationship.choices)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    body = models.TextField()
    #: Module 10 Fast-AI sentiment tag — always null until then.
    sentiment = models.CharField(max_length=16, null=True, blank=True)
    giver_marked_sensitive = models.BooleanField(default=False)

    class Meta:
        db_table = "feedback_item"
        ordering = ["-created_at"]
        constraints = [
            # One 360 submission per giver per cycle. MySQL's NULL-distinct
            # unique-index semantics exempt cycle-less CONTINUOUS rows.
            models.UniqueConstraint(
                fields=["tenant", "cycle", "giver"], name="uq_feedback_cycle_giver"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "subject", "kind"], name="ix_feedback_subject"),
        ]

    def __str__(self):
        return f"{self.relationship}/{self.kind} on {self.subject_id}"

    @property
    def employee(self):
        return self.subject


class OneOnOneNote(TenantScopedModel):
    """A 1:1 meeting note shared ONLY between the two participants.

    Not anonymised, not summarised by Agent 3 — it is mutual working context,
    not anonymous input. Kept deliberately lean.
    """

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="one_on_ones_led"
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="one_on_ones_attended"
    )
    body = models.TextField()
    meeting_date = models.DateField()

    class Meta:
        db_table = "feedback_oneonone"
        ordering = ["-meeting_date", "-created_at"]

    def __str__(self):
        return f"1:1 {self.manager_id}/{self.employee_id} @ {self.meeting_date}"

    def is_participant(self, user):
        return user.id in (self.manager_id, self.employee_id)


class FeedbackSummary(TenantScopedModel):
    """The (eventually Agent-3-written) anonymised theme summary for a cycle.

    Mirrors Module 3's locked-PENDING discipline: a summary is RELEASED only
    after the anonymity gates pass and — when held — an HRBP approves it.
    ``sections`` stays NULL until Agent 3 (Module 10) writes the 4 theme
    sections; Module 4 NEVER fabricates theme text.
    """

    class Status(models.TextChoices):
        PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW", "Pending human review"
        HRBP_HOLD = "HRBP_HOLD", "Held for HRBP"
        APPROVED = "APPROVED", "Approved"
        RELEASED = "RELEASED", "Released"

    cycle = models.ForeignKey(
        "feedback.FeedbackCycle", on_delete=models.CASCADE, related_name="summaries"
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedback_summaries"
    )
    #: The 4 theme sections — written ONLY by Agent 3 (Module 10); null until then.
    sections = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING_HUMAN_REVIEW
    )
    anonymity_passed = models.BooleanField(default=True)
    sensitive = models.BooleanField(default=False)
    volume_total = models.PositiveIntegerField(default=0)
    #: Relationship groups excluded for being below the min-volume threshold.
    insufficient_groups = models.JSONField(default=list, blank=True)
    insufficient_volume = models.BooleanField(default=False)
    #: Agent-3 confidence — null on the deterministic-only path.
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    generated_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_summaries_reviewed",
    )

    class Meta:
        db_table = "feedback_summary"
        ordering = ["-generated_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "cycle"], name="uq_summary_cycle"),
        ]

    def __str__(self):
        return f"summary(cycle={self.cycle_id}) [{self.status}]"

    @property
    def employee(self):
        return self.subject
