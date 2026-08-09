"""
What the AI has actually cost (FINAL2 unit 3).

Every LLM call already writes a :class:`~apps.billing.models.TokenLedger` row through
the gateway — agent, model, prompt/completion tokens, timestamp. That is a meter nobody
was reading. This turns it into calls, tokens and an estimated bill.

**The cost is an ESTIMATE and says so.** Prices come from ``settings.LLM_PRICES`` (USD
per million tokens, overridable via ``LLM_PRICES_JSON``), because published prices move
and only the provider's invoice is authoritative. Reporting a confident figure from a
hardcoded table would be inventing a number, which is the one thing this codebase spends
most of its effort not doing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone


def resolve_model(model: str) -> str:
    """Turn a LOGICAL tier into the model id it actually runs on.

    Some ledger rows record ``chat`` or ``default`` rather than a concrete id — the
    logical name the gateway was asked for, kept when the provider's response did not
    name a model. Pricing those as unknown made the estimate silently understate the
    bill, so they are resolved through the same per-agent map the provider uses.
    """
    name = (model or "").strip()
    if not name:
        return name
    for attr in ("GEMINI_MODEL_MAP", "LLM_MODEL_MAP"):
        mapping = getattr(settings, attr, {}) or {}
        if name in mapping and mapping[name] != name:
            return str(mapping[name])
    return name


def price_for(model: str) -> dict:
    """USD per million tokens for ``model``, matched longest-prefix first.

    Prefix matching so a dated or suffixed id — ``gemini-2.5-flash-002`` — is priced
    like the family it belongs to instead of silently costing nothing.
    """
    prices = getattr(settings, "LLM_PRICES", {}) or {}
    name = resolve_model(model).lower()
    best = None
    for key, value in prices.items():
        if name.startswith(key.lower()) and (best is None or len(key) > len(best[0])):
            best = (key, value)
    return dict(best[1]) if best else {}


@dataclass
class Row:
    """One (tenant, agent, model) group."""

    tenant: str
    agent_code: str
    model: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def priced(self) -> bool:
        """False when no price is known — reported as unknown, never as zero."""
        return bool(price_for(self.model))

    @property
    def cost_usd(self) -> float:
        p = price_for(self.model)
        if not p:
            return 0.0
        return (self.prompt_tokens / 1_000_000) * float(p.get("in", 0)) + (
            self.completion_tokens / 1_000_000) * float(p.get("out", 0))


@dataclass
class Usage:
    days: int
    since: object
    rows: list = field(default_factory=list)

    @property
    def calls(self):
        return sum(r.calls for r in self.rows)

    @property
    def prompt_tokens(self):
        return sum(r.prompt_tokens for r in self.rows)

    @property
    def completion_tokens(self):
        return sum(r.completion_tokens for r in self.rows)

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self):
        return sum(r.cost_usd for r in self.rows)

    @property
    def unpriced_models(self):
        """Models with usage but no price — the gap between this estimate and the bill."""
        return sorted({r.model for r in self.rows if not r.priced and r.total_tokens})

    def by(self, key):
        """Roll the rows up by one attribute, biggest spend first."""
        out: dict = {}
        for row in self.rows:
            bucket = out.setdefault(getattr(row, key), [0, 0, 0.0])
            bucket[0] += row.calls
            bucket[1] += row.total_tokens
            bucket[2] += row.cost_usd
        return sorted(out.items(), key=lambda kv: -kv[1][2])


def collect(days: int = 30, tenant_slug: str = "") -> Usage:
    """Usage over the last ``days``, grouped by tenant, agent and model.

    Aggregates one tenant at a time, INSIDE each tenant's context. The ledger is a
    ``TenantScopedModel``, so every manager on it — including ``all_objects``, which
    only widens to soft-deleted rows — filters by the ambient tenant and returns
    nothing at all outside one. The first version of this queried across tenants and
    cheerfully reported zero usage against a ledger holding thousands of rows.

    Looping is also the honest shape: an operator's roll-up over tenants, each read
    through the same scoping every other read uses, rather than a query that steps
    around the isolation rule because it happens to be convenient.
    """
    from apps.billing.models import TokenLedger
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import Tenant

    since = timezone.now() - timedelta(days=days)
    tenants = Tenant.objects.all()
    if tenant_slug:
        tenants = tenants.filter(slug=tenant_slug)

    rows: list[Row] = []
    for tenant in tenants:
        with tenant_context(tenant.id):
            grouped = (TokenLedger.objects
                       .filter(occurred_at__gte=since)
                       .values("agent_code", "model")
                       .annotate(calls=Count("id"),
                                 p=Sum("prompt_tokens"),
                                 c=Sum("completion_tokens"))
                       .order_by())
            rows.extend(
                Row(tenant=tenant.slug, agent_code=g["agent_code"], model=g["model"],
                    calls=g["calls"], prompt_tokens=g["p"] or 0,
                    completion_tokens=g["c"] or 0)
                for g in grouped
            )
    return Usage(days=days, since=since, rows=rows)
