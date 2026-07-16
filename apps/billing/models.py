"""
Billing & entitlements model.

``Entitlement`` is the per-tenant commercial state. It deliberately models the
two commercial axes as INDEPENDENT fields:

* ``seat_count`` — how many seats the tenant has bought (a plain integer).
* ``feature_packs`` — which packs the tenant holds (a list of pack codes).

Nothing here stores or enforces a "tier": the tier is a display label derived
from the packs (see ``packs.tier_label``). Seats and packs change independently
— e.g. buying more seats never touches packs, and upgrading to FULL_AI never
touches seats.

The model is a :class:`~apps.tenancy.models.TenantScopedModel`, so reads via the
default ``objects`` manager are tenant-scoped and fail closed, and there is at
most one entitlement row per tenant (enforced by a UniqueConstraint).
"""
from __future__ import annotations

from django.db import models

from apps.tenancy.models import TenantScopedModel

from .packs import STARTER, agents_for_packs, features_for_packs, tier_label


class Entitlement(TenantScopedModel):
    #: Independent of packs: changing seats never touches feature_packs.
    seat_count = models.PositiveIntegerField(default=0)
    #: Independent of seats: a list of pack codes (see ``packs.FEATURE_PACKS``).
    feature_packs = models.JSONField(default=list)

    class Meta:
        db_table = "billing_entitlement"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uq_entitlement_tenant"),
        ]

    def __str__(self):
        return f"Entitlement(tenant={self.tenant_id}, seats={self.seat_count}, packs={self.feature_packs})"

    def unlocked_agents(self) -> set[str]:
        """The set of agent codes this entitlement unlocks, across all packs."""
        return agents_for_packs(self.feature_packs)

    def has_agent(self, agent_code: str) -> bool:
        """True iff ``agent_code`` is unlocked by one of this tenant's packs."""
        return agent_code in self.unlocked_agents()

    def has_pack(self, code: str) -> bool:
        """True iff this entitlement currently holds the pack ``code``."""
        return code in (self.feature_packs or [])

    def add_pack(self, code: str) -> None:
        """Add ``code`` to ``feature_packs`` in place (no-op if already present).

        Does not persist — the caller saves. Touches only packs, never seats.
        """
        if self.feature_packs is None:
            self.feature_packs = []
        if code not in self.feature_packs:
            self.feature_packs.append(code)

    def unlocked_features(self) -> set[str]:
        """The set of ALL feature codes (agents + non-agent) this entitlement
        unlocks. The superset behind ``feature_flags_for``."""
        return features_for_packs(self.feature_packs)

    def has_feature(self, feature_code: str) -> bool:
        """True iff ``feature_code`` is unlocked by one of this tenant's packs."""
        return feature_code in self.unlocked_features()

    def remove_pack(self, code: str) -> None:
        """Remove ``code`` from ``feature_packs`` in place (no-op if absent). Does
        not persist — the caller saves. Touches only packs, never seats."""
        if self.feature_packs and code in self.feature_packs:
            self.feature_packs = [c for c in self.feature_packs if c != code]

    @property
    def tier_label(self) -> str:
        """DISPLAY ONLY label derived from the packs — never used to gate access."""
        return tier_label(self.feature_packs)


# Default pack a freshly provisioned tenant starts on.
DEFAULT_PACKS = [STARTER]


class TokenLedger(TenantScopedModel):
    """One recorded LLM-usage event — the meter the Module-10 ``LLMGateway`` writes
    to on EVERY call. Captures the agent, model, and prompt/completion/total tokens
    so usage can be rolled up per tenant + agent. Append-style (no edits); reads are
    tenant-scoped like every other ``TenantScopedModel``."""

    agent_code = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    occurred_at = models.DateTimeField()

    class Meta:
        db_table = "billing_token_ledger"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(
                fields=["tenant", "agent_code", "-occurred_at"],
                name="ix_ledger_tenant_agent",
            ),
        ]

    def __str__(self):
        return f"usage(tenant={self.tenant_id}, agent={self.agent_code})={self.total_tokens}t"


class AgentBudget(TenantScopedModel):
    """A per-tenant cap on agent CALLS within a rolling window. An explicit row for
    a specific ``agent_code`` overrides the entitlement-derived default; an
    ``agent_code="all"`` row is a tenant-wide fallback. The Module-10 LLMGateway
    reserves against this BEFORE running an agent (``check_and_reserve_budget``);
    over budget → a clear 429 with an upgrade hint."""

    class Window(models.TextChoices):
        DAILY = "DAILY", "Daily"
        MONTHLY = "MONTHLY", "Monthly"

    #: Sentinel agent_code for a tenant-wide budget that applies to every agent.
    AGENT_ALL = "all"

    agent_code = models.CharField(max_length=32, default=AGENT_ALL)
    window = models.CharField(max_length=8, choices=Window.choices, default=Window.DAILY)
    limit = models.PositiveIntegerField()

    class Meta:
        db_table = "billing_agent_budget"
        ordering = ["agent_code", "window"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "agent_code", "window"],
                name="uq_agentbudget_tenant_agent_window",
            ),
        ]

    def __str__(self):
        return f"budget(tenant={self.tenant_id}, {self.agent_code}/{self.window})={self.limit}"


class Subscription(TenantScopedModel):
    """The tenant's INTERNAL subscription (PHASE2 L1.4) — plan + lifecycle status,
    driven by an admin (no payment gateway; that's the human-reviewed payments
    lane, docs/PHASE2/PAYMENTS_DESIGN.md). The subscription is the single source
    of truth: setting the plan syncs the Entitlement's packs, and the feature
    flags flip immediately. Features stay on through TRIAL/ACTIVE/PAST_DUE/GRACE
    and turn off in CANCELLED/EXPIRED (the core PMS itself is never gated)."""

    class Plan(models.TextChoices):
        STARTER = "STARTER", "Starter"
        PROFESSIONAL = "PROFESSIONAL", "Professional"
        ENTERPRISE = "ENTERPRISE", "Enterprise"

    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Trial"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        GRACE = "GRACE", "Grace period"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    #: from → the set of allowed next states (same-state is always allowed).
    TRANSITIONS = {
        Status.TRIAL: {Status.ACTIVE, Status.CANCELLED, Status.EXPIRED},
        Status.ACTIVE: {Status.PAST_DUE, Status.CANCELLED, Status.EXPIRED},
        Status.PAST_DUE: {Status.ACTIVE, Status.GRACE, Status.CANCELLED},
        Status.GRACE: {Status.ACTIVE, Status.EXPIRED},
        Status.CANCELLED: {Status.ACTIVE},
        Status.EXPIRED: {Status.ACTIVE},
    }

    plan = models.CharField(max_length=16, choices=Plan.choices, default=Plan.STARTER)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_subscription"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uq_subscription_tenant"),
        ]

    @property
    def features_active(self) -> bool:
        return self.status in (
            self.Status.TRIAL, self.Status.ACTIVE, self.Status.PAST_DUE, self.Status.GRACE
        )

    def __str__(self):
        return f"subscription(tenant={self.tenant_id}, {self.plan}/{self.status})"


# ─── Payments (PROD_C) — the money layer on top of Subscription ──────────────
# All tenant-scoped, additive. The Subscription state machine above stays the
# single source of truth for entitlements; these models only RECORD money events
# and let a verified webhook DRIVE the subscription transitions. No card data is
# ever stored here — that stays with the provider (PCI boundary).


class BillingProfile(TenantScopedModel):
    """Per-tenant billing identity (1:1). Which provider bills this tenant, its
    currency/country, and the provider-side customer id. No secrets, no card data."""

    class Provider(models.TextChoices):
        STRIPE = "STRIPE", "Stripe"
        RAZORPAY = "RAZORPAY", "Razorpay"

    provider = models.CharField(
        max_length=16, choices=Provider.choices, default=Provider.STRIPE
    )
    currency = models.CharField(max_length=3, default="USD")
    country = models.CharField(max_length=2, default="US")
    billing_email = models.EmailField(blank=True, default="")
    provider_customer_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "billing_profile"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uq_billing_profile_tenant"),
        ]

    def __str__(self):
        return f"billing_profile(tenant={self.tenant_id}, {self.provider})"


class PaymentEvent(TenantScopedModel):
    """Append-only record of a provider webhook event. ``(provider, event_id)`` is
    UNIQUE, so the SAME event delivered twice can never double-activate — the second
    insert violates the constraint and is treated as an idempotent no-op."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSED = "PROCESSED", "Processed"
        IGNORED = "IGNORED", "Ignored"
        ERROR = "ERROR", "Error"

    provider = models.CharField(max_length=16)
    event_id = models.CharField(max_length=191)
    type = models.CharField(max_length=64)
    #: Redacted event payload (no card/PII); enough to audit + reprocess.
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_payment_event"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"], name="uq_payment_event_provider_id"
            ),
        ]

    def __str__(self):
        return f"payment_event({self.provider}:{self.event_id} {self.status})"


class Payment(TenantScopedModel):
    """A recorded money movement (amount in MINOR units — cents/paise)."""

    class Status(models.TextChoices):
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially refunded"

    subscription = models.ForeignKey(
        "billing.Subscription", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    provider = models.CharField(max_length=16)
    provider_payment_id = models.CharField(max_length=191, blank=True, default="")
    amount = models.PositiveIntegerField(default=0)  # minor units
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices)

    class Meta:
        db_table = "billing_payment"

    def __str__(self):
        return f"payment(tenant={self.tenant_id}, {self.amount}{self.currency}/{self.status})"


class Invoice(TenantScopedModel):
    """A stored invoice per successful payment. ``number`` is sequential per tenant."""

    number = models.CharField(max_length=32)
    payment = models.ForeignKey(
        "billing.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    line_items = models.JSONField(default=list)
    total = models.PositiveIntegerField(default=0)  # minor units
    currency = models.CharField(max_length=3, default="USD")
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_invoice"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uq_invoice_tenant_number"),
        ]

    def __str__(self):
        return f"invoice(tenant={self.tenant_id}, {self.number}, {self.total}{self.currency})"
