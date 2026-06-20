"""
Reviews & appraisal cycles — the first HITL module.

Every model is a :class:`~apps.tenancy.models.TenantScopedModel`. The headline
guarantee is the HITL gate: a review can NEVER become FINALIZED without a human
approver recorded. It is enforced in DEPTH:

1. State machine guard — ``finalize()`` requires state == APPROVED and a
   non-null ``human_reviewer`` (``apps/reviews/state_machine.py``).
2. DB CHECK constraint — ``ck_review_finalized_has_reviewer`` rejects ANY write
   of state=FINALIZED with a null ``human_reviewer``, even direct ORM/raw SQL
   (MySQL 8 enforces CHECK constraints).
3. API — finalizing an unapproved review returns 422 HITL_APPROVAL_REQUIRED.

Reviews attach to the EXISTING Module-2 ``PerformanceCycle`` (kept minimal for
exactly this); no second cycle model. ``confidence_score``/``citations`` exist
for Agent 1 (Module 10) and stay null on the manual path.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class Review(TenantScopedModel):
    """One employee's review in one cycle (unique per tenant+employee+cycle)."""

    class State(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        AI_DRAFTING = "AI_DRAFTING", "AI drafting"
        PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW", "Pending human review"
        EDITING = "EDITING", "Editing"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        FINALIZED = "FINALIZED", "Finalized"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual draft"
        AI = "AI", "AI draft (Agent 1)"

    #: The subject — whose performance is being reviewed.
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews_received"
    )
    #: The author — the manager who owns/drafts the review.
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviews_authored",
    )
    cycle = models.ForeignKey(
        "cycles.PerformanceCycle", on_delete=models.PROTECT, related_name="reviews"
    )
    state = models.CharField(max_length=24, choices=State.choices, default=State.DRAFT)
    draft_body = models.TextField(blank=True)
    final_body = models.TextField(blank=True)
    #: THE HITL gate: NULL until a human approves; set only by the approve
    #: transition; immutable afterwards (re-approve is an illegal transition).
    human_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviews_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.MANUAL)
    # Agent 1 (Module 10) fills these; always null on the manual path.
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    citations = models.JSONField(null=True, blank=True)
    # Module 5 (opt-in): an in-flight approval route when finalize is routed.
    # Null when no "review" workflow is active (then finalize is single-step,
    # exactly as Module 3). The Module-3 state machine is otherwise unchanged.
    approval_route = models.ForeignKey(
        "approvals.ApprovalRoute",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "reviews_review"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee", "cycle"], name="uq_review_tenant_emp_cycle"
            ),
            # HITL in depth, layer 2: the DATABASE refuses a FINALIZED review
            # with no human approver — even via direct ORM/raw SQL writes that
            # bypass the state machine. (MySQL 8.0.16+ enforces CHECK.)
            models.CheckConstraint(
                check=~models.Q(state="FINALIZED") | models.Q(human_reviewer__isnull=False),
                name="ck_review_finalized_has_reviewer",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "cycle", "state"], name="ix_review_cycle_state"),
            # Serves the default paginated list for the broad (Manager/HRBP/Admin)
            # scopes: WHERE tenant=? ORDER BY -created_at LIMIT page — no filesort
            # over the full tenant set. Employee-scope filtering is already covered
            # by the (tenant, employee, cycle) unique constraint's index.
            models.Index(fields=["tenant", "-created_at"], name="ix_review_tenant_recent"),
        ]

    def __str__(self):
        return f"review(emp={self.employee_id}, cycle={self.cycle_id}) [{self.state}]"


class ReviewAssessment(TenantScopedModel):
    """A captured assessment feeding a review: SELF / MANAGER / PEER / UPWARD.

    One row per (review, assessor) — SELF re-submission upserts (the subject
    refining their self-evaluation); other types reject duplicates.
    """

    class Type(models.TextChoices):
        SELF = "SELF", "Self"
        MANAGER = "MANAGER", "Manager"
        PEER = "PEER", "Peer"
        UPWARD = "UPWARD", "Upward"

    review = models.ForeignKey(
        "reviews.Review", on_delete=models.CASCADE, related_name="assessments"
    )
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assessments_given"
    )
    assessment_type = models.CharField(max_length=8, choices=Type.choices)
    body = models.TextField()
    #: Server-set on every submit/upsert; never client-supplied.
    submitted_at = models.DateTimeField()

    class Meta:
        db_table = "reviews_assessment"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "review", "assessor"], name="uq_assessment_review_assessor"
            ),
        ]

    def __str__(self):
        return f"{self.assessment_type} by {self.assessor_id} on {self.review_id}"

    @property
    def employee(self):
        # Lets RBAC WithinScope resolve the subject uniformly.
        return self.review.employee


class ReviewStateTransition(TenantScopedModel):
    """Append-style transition log powering the approval-tracker / timeline.

    Complements (does not replace) the immutable AuditLog: the AuditLog is the
    tamper-proof evidence written BEFORE each transition; this table is the
    queryable per-review timeline the UI renders.
    """

    review = models.ForeignKey(
        "reviews.Review", on_delete=models.CASCADE, related_name="transitions"
    )
    from_state = models.CharField(max_length=24)
    to_state = models.CharField(max_length=24)
    #: Null for system transitions (e.g. the Agent-1 worker locking a draft).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_transitions",
    )
    at = models.DateTimeField()
    note = models.TextField(blank=True)

    class Meta:
        db_table = "reviews_statetransition"
        ordering = ["at", "created_at"]

    def __str__(self):
        return f"{self.review_id}: {self.from_state} -> {self.to_state}"

    @property
    def employee(self):
        return self.review.employee
