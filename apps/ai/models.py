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
    #: Loose reference to the INPUT artifact (NOT a DB FK — see D4).
    #: ``target_type`` e.g. "review"; ``target_id`` the artifact UUID (may be set
    #: up front when a PENDING placeholder is created before the work runs).
    target_type = models.CharField(max_length=32)
    target_id = models.UUIDField(null=True, blank=True)
    #: The artifact the run PRODUCED, set on SUCCEEDED. For mutate-in-place seams
    #: (review/JD/feedback) this equals ``target_id``; for create-new seams
    #: (succession/career) it's the NEW AI plan/roadmap — so the client can
    #: navigate to what was created, which ``target_id`` (the input) can't tell it.
    result_id = models.UUIDField(null=True, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    #: Agent-specific extra args the seam task needs beyond (tenant, target, actor)
    #: — e.g. the career agent's ``target_ref``. Server-set at enqueue; never a
    #: free-form client channel into the task.
    params = models.JSONField(default=dict, blank=True)

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


# ── Agentic chat V2 (OVERNIGHT_A) — session memory + plan → per-step approve ────
#
# The chat becomes an AGENT: a request can span multiple turns and multiple steps.
# These rows persist that WITHOUT weakening any invariant — a ChatPlan is INERT
# data (nothing runs on plan-emit); a step executes ONLY through the existing
# ``execute_action`` gate on an explicit human Approve, re-checking capability +
# scope on the real targets. All rows are :class:`TenantScopedModel` (tenant_id +
# UUID pk), so the tenant-scoped manager isolates them per tenant automatically; we
# additionally bind each session/plan to its ``owner`` so one user can never read or
# approve another's (a cross-user id is filtered out → 404/403).

#: A chat session is "live" for this long since its last activity. Older sessions
#: return empty history and never resolve prior references (short-term memory only).
CHAT_SESSION_TTL_HOURS = 24


class ChatSession(TenantScopedModel):
    """A short-term chat memory scope for ONE user. Turns and plans hang off it so a
    user can close and reopen the panel within the TTL and resume the conversation.
    Bound to ``owner``; never shared across users (or tenants — the manager scopes
    that). Not an audit record — it's convenience memory, safe to expire/prune."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions"
    )
    #: A short human label (derived from the first user message) for the recent-chats picker.
    title = models.CharField(max_length=120, blank=True, default="")
    #: Bumped on every turn; drives the TTL (see :attr:`is_expired`).
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_chat_session"
        ordering = ["-last_activity"]
        indexes = [models.Index(fields=["tenant", "owner", "-last_activity"], name="ix_chatsess_owner")]

    def __str__(self):
        return f"ChatSession(owner={self.owner_id}) [{self.last_activity:%Y-%m-%d %H:%M}]"

    @property
    def is_expired(self) -> bool:
        """True once the session has been idle past the TTL — history and prior
        references are then treated as gone (short-term memory only)."""
        from datetime import timedelta

        from django.utils import timezone

        return timezone.now() - self.last_activity > timedelta(hours=CHAT_SESSION_TTL_HOURS)


class ChatTurn(TenantScopedModel):
    """One message in a :class:`ChatSession` — the user's text or the assistant's
    reply. ``refs`` records the real, in-scope objects the turn referenced (e.g. the
    review just drafted) so a LATER turn can resolve "the review we just drafted"
    against them — but resolution ALWAYS re-checks the caller can still see the
    object (a ref never widens access; see :mod:`apps.ai.sessions`)."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="turns")
    role = models.CharField(max_length=10, choices=Role.choices)
    text = models.TextField(blank=True, default="")
    #: [{"type": "review"|"user"|..., "id": "<uuid>", "label": "<display>"}] — the
    #: objects this turn was grounded in. Data only; never re-interpreted as a command.
    refs = models.JSONField(default=list, blank=True)
    #: The plan this assistant turn emitted, if any (nullable).
    plan = models.ForeignKey("ai.ChatPlan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "ai_chat_turn"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["tenant", "session", "created_at"], name="ix_chatturn_session")]

    def __str__(self):
        return f"ChatTurn({self.role}, session={self.session_id})"


class ChatPlan(TenantScopedModel):
    """An ordered, INERT plan the agent proposed for a multi-step request. Emitting a
    plan runs NOTHING — each step executes only on an explicit per-step human Approve
    (:class:`ChatPlanStep`). Bound to ``owner`` so only its author can view/approve it."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_plans"
    )
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="plans")
    #: The originating user request (verbatim, data only).
    message = models.TextField(blank=True, default="")
    #: A natural-language summary of the plan (may explain omissions — e.g. a step
    #: dropped because nothing was in scope — WITHOUT revealing out-of-scope objects).
    summary = models.TextField(blank=True, default="")
    #: The planner's confidence (from the gateway), for the UI to show low-confidence.
    confidence = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "ai_chat_plan"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "owner", "-created_at"], name="ix_chatplan_owner")]

    def __str__(self):
        return f"ChatPlan(owner={self.owner_id}, steps={self.steps.count()})"


class ChatPlanStep(TenantScopedModel):
    """ONE step of a :class:`ChatPlan` — exactly one registered action, its
    deterministically-resolved params, a grounded reason, and its lifecycle status.
    Params are resolved in Python (never LLM-generated); the step executes only via
    ``execute_action`` on Approve, which re-checks capability + scope."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved (executing)"
        DONE = "done", "Done"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    class Feel(models.TextChoices):
        CONFIRM = "confirm", "Confirm in chat"
        NAVIGATE = "navigate", "Open a screen"
        CLARIFY = "clarify", "Ask a question"

    plan = models.ForeignKey(ChatPlan, on_delete=models.CASCADE, related_name="steps")
    #: 0-based position in the plan.
    ordinal = models.PositiveSmallIntegerField()
    #: A registered action name (or "clarify"). Validated against the registry at build.
    action = models.CharField(max_length=48)
    feel = models.CharField(max_length=10, choices=Feel.choices, default=Feel.CONFIRM)
    #: Deterministically-resolved params (scope-bound; never model-extracted).
    params = models.JSONField(default=dict, blank=True)
    #: The human-facing one-liner (the proposal summary).
    summary = models.TextField(blank=True, default="")
    #: The grounded "why" — composed in Python from real, fetched, in-scope facts.
    reason = models.TextField(blank=True, default="")
    #: Small preview payload (e.g. [{"employee": "Vera"}]) for the UI.
    preview = models.JSONField(default=list, blank=True)
    #: navigate steps carry a deep-link + prefill (completed on the screen, never in chat).
    deeplink = models.CharField(max_length=255, blank=True, default="")
    prefill = models.JSONField(default=dict, blank=True)
    #: clarify steps carry candidate options (scoped to the caller).
    candidates = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    #: The execute_action result (job/audit ids) once approved+run; data only.
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_chat_plan_step"
        ordering = ["ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "ordinal"], name="uq_planstep_plan_ordinal")
        ]

    def __str__(self):
        return f"ChatPlanStep(#{self.ordinal} {self.action} [{self.status}])"
