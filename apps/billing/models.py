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
