"""
Billing & entitlements services — the only sanctioned way to read and mutate a
tenant's commercial state.

Every mutation keeps the two commercial axes independent: ``set_seats`` touches
only ``seat_count``; ``upgrade_to_full_ai`` touches only ``feature_packs``.
Consequential mutations write an immutable :class:`~apps.audit.models.AuditLog`
row *before* the change takes effect, per the project's audit rules.

Tenant resolution is robust to context: these helpers accept a ``Tenant``
instance and bind it explicitly for the duration of the work, so they behave
identically whether called from an endpoint (tenant already bound by
``TenantMiddleware``) or from provisioning/system code (no context bound).
"""
from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

from apps.audit.services import record
from apps.core.cache import invalidate_tenant_cache, tenant_cache_key
from apps.tenancy.context import tenant_context

from .exceptions import BudgetExceeded
from .models import DEFAULT_PACKS, AgentBudget, Entitlement, TokenLedger
from .packs import (
    ALL_FEATURES,
    FULL_AI,
    agents_for_packs,
    default_budget_limit,
    features_for_packs,
)

#: Time-to-live (seconds) for a cached entitlement read.
_ENTITLEMENT_CACHE_TTL = 300
#: Cache key suffix identifying a tenant's cached entitlement.
_ENTITLEMENT_CACHE_PART = "entitlement"

#: Time-to-live (seconds) for a cached rate-limit map.
_RATE_LIMITS_CACHE_TTL = 300
#: Cache key suffix identifying a tenant's cached rate-limit map.
_RATE_LIMITS_CACHE_PART = "rate_limits"

#: Time-to-live (seconds) for a cached feature-flag map.
_FEATURE_FLAGS_CACHE_TTL = 300
#: Cache key suffix identifying a tenant's cached feature-flag map.
_FEATURE_FLAGS_CACHE_PART = "feature_flags"

#: Cache-key prefix for an agent-call budget counter. EVERY counter key embeds the
#: tenant id (cross-tenant budget isolation is treated as a security control).
_BUDGET_COUNTER_PART = "agent_budget"

#: DRF rate strings per entitlement, keyed by the throttle scope. STARTER tenants
#: get the conservative limits; adding the FULL_AI pack lifts every bucket. These
#: are the single source of truth for throttle rates — call sites must NOT
#: hardcode their own (they resolve through :func:`rate_limits_for`).
_RATE_LIMITS_STARTER = {"tenant": "600/min", "user": "120/min", "ai": "20/min"}
_RATE_LIMITS_FULL_AI = {"tenant": "3000/min", "user": "600/min", "ai": "120/min"}


def _tenant_id(tenant) -> str:
    return str(getattr(tenant, "id", tenant))


def get_or_create_entitlement(tenant, *, default_seats=0, default_packs=None) -> Entitlement:
    """Return ``tenant``'s entitlement, creating a default one if absent.

    A newly provisioned tenant defaults to ``seat_count=default_seats`` and the
    STARTER pack (override via ``default_packs``). Works whether or not a tenant
    context is already bound: the read is performed inside a bound context (so
    the scoped manager resolves) and the create passes ``tenant`` explicitly (the
    system/provisioning write path).
    """
    tid = _tenant_id(tenant)
    with tenant_context(tid):
        existing = Entitlement.objects.filter(tenant_id=tid).first()
        if existing is not None:
            return existing
        packs = list(default_packs) if default_packs is not None else list(DEFAULT_PACKS)
        entitlement = Entitlement(tenant_id=tid, seat_count=default_seats, feature_packs=packs)
        entitlement.save()
        return entitlement


def get_entitlement_cached(tenant) -> Entitlement:
    """Return ``tenant``'s entitlement, served from the per-tenant cache.

    The READ path for the hot gate: on a cache hit the stored :class:`Entitlement`
    instance is returned directly (django-redis pickles the model, so
    ``.has_agent()`` and friends keep working); on a miss it loads via
    :func:`get_or_create_entitlement`, caches the instance under a tenant-scoped
    key for :data:`_ENTITLEMENT_CACHE_TTL` seconds, and returns it.

    Mutation paths deliberately do NOT use this — they read fresh from the DB and
    then invalidate, so a stale row can never be persisted.
    """
    key = tenant_cache_key(_tenant_id(tenant), _ENTITLEMENT_CACHE_PART)
    cached = cache.get(key)
    if cached is not None:
        return cached
    entitlement = get_or_create_entitlement(tenant)
    cache.set(key, entitlement, _ENTITLEMENT_CACHE_TTL)
    return entitlement


def tenant_has_agent(tenant, agent_code: str) -> bool:
    """True iff ``tenant``'s entitlement unlocks ``agent_code``.

    Reads through the cache (:func:`get_entitlement_cached`) so the gate's hot
    path avoids a DB round-trip, then checks the agent against the union of the
    entitlement's packs.
    """
    entitlement = get_entitlement_cached(tenant)
    return entitlement.has_agent(agent_code)


def tenant_has_feature(tenant, feature_code: str) -> bool:
    """True iff ``tenant``'s entitlement unlocks ``feature_code`` — the SUPERSET that
    covers both agents (agent1..5) and the non-agent features (chat / jd_generator /
    career_roadmap). Reads through the entitlement cache (the gate's hot path)."""
    return get_entitlement_cached(tenant).has_feature(feature_code)


def rate_limits_for(tenant_id) -> dict:
    """Return the DRF rate strings for ``tenant_id``, derived from its entitlement.

    The map is keyed by throttle scope (``"tenant"``, ``"user"``, ``"ai"``): a
    STARTER tenant gets the conservative limits, a FULL_AI tenant the lifted ones
    (see :data:`_RATE_LIMITS_STARTER` / :data:`_RATE_LIMITS_FULL_AI`). Rates are
    NOT hardcoded at the call site — every throttle resolves through here so an
    upgrade lifts limits everywhere at once.

    Mirrors the entitlement cache pattern: on a cache hit the stored dict is
    returned directly; on a miss the entitlement is read (itself cached) and the
    chosen dict is cached under a tenant-scoped key for
    :data:`_RATE_LIMITS_CACHE_TTL` seconds. Accepts a ``Tenant`` or a bare id
    (passed straight through to :func:`get_entitlement_cached`).
    """
    key = tenant_cache_key(_tenant_id(tenant_id), _RATE_LIMITS_CACHE_PART)
    cached = cache.get(key)
    if cached is not None:
        return cached
    entitlement = get_entitlement_cached(tenant_id)
    limits = _RATE_LIMITS_FULL_AI if entitlement.has_pack(FULL_AI) else _RATE_LIMITS_STARTER
    cache.set(key, limits, _RATE_LIMITS_CACHE_TTL)
    return limits


def set_seats(tenant, seat_count: int, *, actor=None) -> Entitlement:
    """Set ``seat_count`` independently of packs and audit the change.

    Leaves ``feature_packs`` untouched. Writes a ``billing.seats_changed`` audit
    row (recording the old and new seat counts) before persisting.
    """
    tid = _tenant_id(tenant)
    entitlement = get_or_create_entitlement(tenant)
    previous = entitlement.seat_count
    with tenant_context(tid):
        record(
            action="billing.seats_changed",
            actor=actor,
            target_type="tenant",
            target_id=tid,
            metadata={"previous_seats": previous, "new_seats": seat_count},
            tenant=tid,
        )
        entitlement.seat_count = seat_count
        entitlement.save(update_fields=["seat_count", "updated_at"])
    # Clear the WHOLE tenant namespace, not just the entitlement key: the cached
    # rate-limit map (rate_limits_for) is derived from the same entitlement, so
    # both must refresh together. Clearing everything still satisfies the
    # entitlement-key invalidation the cache tests assert.
    invalidate_tenant_cache(tid)
    return entitlement


def upgrade_to_full_ai(tenant, *, actor=None) -> Entitlement:
    """The demoable commercial switch: add the FULL_AI pack, unlocking agents 3-5.

    Touches ONLY ``feature_packs`` — ``seat_count`` is left exactly as it was.
    Idempotent: a tenant already holding FULL_AI is returned unchanged (and no
    audit row is written, since nothing changed). When the pack is added, a
    ``entitlement.upgraded`` audit row is recorded *before* the change takes
    effect, capturing the pack added and the resulting unlocked agents.
    """
    tid = _tenant_id(tenant)
    entitlement = get_or_create_entitlement(tenant)
    if entitlement.has_pack(FULL_AI):
        return entitlement

    with tenant_context(tid):
        resulting_packs = list(entitlement.feature_packs or []) + [FULL_AI]
        record(
            action="entitlement.upgraded",
            actor=actor,
            target_type="tenant",
            target_id=tid,
            metadata={
                "pack_added": FULL_AI,
                "unlocked_agents": sorted(agents_for_packs(resulting_packs)),
            },
            tenant=tid,
        )
        entitlement.add_pack(FULL_AI)
        entitlement.save(update_fields=["feature_packs", "updated_at"])
    # Clear the WHOLE tenant namespace, not just the entitlement key: the cached
    # rate-limit map (rate_limits_for) is derived from the same entitlement, so
    # an upgrade must refresh both. Clearing everything still satisfies the
    # entitlement-key invalidation the cache tests assert.
    invalidate_tenant_cache(tid)
    return entitlement


# ── Module 11: generic pack management ────────────────────────────────────────


def add_pack(tenant, pack_code: str, *, actor=None) -> Entitlement:
    """Add ``pack_code`` to a tenant's entitlement (idempotent), audited + cache
    invalidated. Touches ONLY ``feature_packs`` — seats are untouched. This is the
    generic form behind ``upgrade_to_full_ai`` (which is ``add_pack(FULL_AI)``)."""
    tid = _tenant_id(tenant)
    entitlement = get_or_create_entitlement(tenant)
    if entitlement.has_pack(pack_code):
        return entitlement
    with tenant_context(tid):
        record(
            action="entitlement.pack_added",
            actor=actor,
            target_type="tenant",
            target_id=tid,
            metadata={
                "pack_added": pack_code,
                "unlocked_features": sorted(
                    features_for_packs(list(entitlement.feature_packs or []) + [pack_code])
                ),
            },
            tenant=tid,
        )
        entitlement.add_pack(pack_code)
        entitlement.save(update_fields=["feature_packs", "updated_at"])
    invalidate_tenant_cache(tid)
    return entitlement


def remove_pack(tenant, pack_code: str, *, actor=None) -> Entitlement:
    """Remove ``pack_code`` from a tenant's entitlement (idempotent), audited +
    cache invalidated. Touches ONLY ``feature_packs`` — seats are untouched."""
    tid = _tenant_id(tenant)
    entitlement = get_or_create_entitlement(tenant)
    if not entitlement.has_pack(pack_code):
        return entitlement
    with tenant_context(tid):
        record(
            action="entitlement.pack_removed",
            actor=actor,
            target_type="tenant",
            target_id=tid,
            metadata={"pack_removed": pack_code},
            tenant=tid,
        )
        entitlement.remove_pack(pack_code)
        entitlement.save(update_fields=["feature_packs", "updated_at"])
    invalidate_tenant_cache(tid)
    return entitlement


# ── Module 11: feature flags (the API/UI feature-flag map) ────────────────────


def feature_flags_for(tenant) -> dict:
    """Return the complete ``{feature_code: bool}`` flag map for ``tenant``, derived
    from its entitlement's packs (NOT its seat_count — the two axes stay
    independent). Every key in ``ALL_FEATURES`` is present, so the frontend gets a
    complete, stable map. Cached per-tenant (mirrors the entitlement cache); the
    whole tenant namespace is cleared on any entitlement change, so an upgrade flips
    flags instantly."""
    key = tenant_cache_key(_tenant_id(tenant), _FEATURE_FLAGS_CACHE_PART)
    cached = cache.get(key)
    if cached is not None:
        return cached
    entitlement = get_entitlement_cached(tenant)
    unlocked = entitlement.unlocked_features()
    flags = {feature: (feature in unlocked) for feature in sorted(ALL_FEATURES)}
    cache.set(key, flags, _FEATURE_FLAGS_CACHE_TTL)
    return flags


def upgrade_prompt(tenant) -> dict:
    """Data for an in-app upgrade prompt: the current packs/flags, the features
    still LOCKED, and what unlocking with FULL_AI would add — CONCEPTUAL only, no
    pricing / payment (Phase 2)."""
    entitlement = get_entitlement_cached(tenant)
    flags = feature_flags_for(tenant)
    locked = sorted(f for f, on in flags.items() if not on)
    would_unlock = sorted(
        features_for_packs(list(entitlement.feature_packs or []) + [FULL_AI])
        - entitlement.unlocked_features()
    )
    return {
        "current_packs": list(entitlement.feature_packs or []),
        "tier_label": entitlement.tier_label,
        "feature_flags": flags,
        "locked_features": locked,
        "upgrade": {
            "pack": FULL_AI,
            "would_unlock": would_unlock,
            "note": "Conceptual only — no pricing or payment is captured (Phase 2).",
        },
    }


# ── Module 11: usage metering (the TokenLedger the LLMGateway writes to) ──────


def record_usage(
    tenant, *, agent_code, model, prompt_tokens=0, completion_tokens=0, occurred_at=None
) -> TokenLedger:
    """Record one LLM-usage event to the ``TokenLedger`` (binds the tenant, so it is
    safe off-request — the Module-10 gateway calls it from a Celery task). Returns
    the row. ``total_tokens`` is computed from prompt + completion."""
    tid = _tenant_id(tenant)
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    with tenant_context(tid):
        return TokenLedger.objects.create(
            tenant_id=tid,
            agent_code=agent_code,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            occurred_at=occurred_at or timezone.now(),
        )


# ── Module 11: per-tenant agent-call budgets (reserved BEFORE an agent runs) ──


def _budget_period(window: str, now=None) -> str:
    """The current period stamp for ``window`` — ``YYYY-MM-DD`` for DAILY,
    ``YYYY-MM`` for MONTHLY — so a counter naturally resets when the period rolls."""
    now = now or timezone.now()
    return now.strftime("%Y-%m") if window == AgentBudget.Window.MONTHLY else now.strftime("%Y-%m-%d")


def _budget_ttl(window: str) -> int:
    """A safety TTL on the counter key (the period stamp already scopes it; the TTL
    just reaps stale keys). Daily ~ 2 days; monthly ~ 32 days."""
    return 60 * 60 * 24 * 32 if window == AgentBudget.Window.MONTHLY else 60 * 60 * 24 * 2


def resolve_budget_limit(tenant, agent_code, window=AgentBudget.Window.DAILY) -> int:
    """The effective budget limit for (tenant, agent_code, window): an explicit
    per-agent ``AgentBudget`` row wins; else a tenant-wide ``agent_code='all'`` row;
    else the entitlement-derived default (FULL_AI tenants get the higher cap)."""
    tid = _tenant_id(tenant)
    with tenant_context(tid):
        row = AgentBudget.objects.filter(agent_code=agent_code, window=window).first()
        if row is None:
            row = AgentBudget.objects.filter(
                agent_code=AgentBudget.AGENT_ALL, window=window
            ).first()
        if row is not None:
            return row.limit
    entitlement = get_entitlement_cached(tenant)
    return default_budget_limit(window, entitlement.has_pack(FULL_AI))


def check_and_reserve_budget(
    tenant, agent_code, *, window=AgentBudget.Window.DAILY, now=None
) -> dict:
    """Reserve one agent call against the tenant's budget for ``window``, or raise
    ``BudgetExceeded`` (429) when the limit is already reached.

    The counter lives in the cache under a key that EMBEDS THE TENANT ID (and the
    agent + window + period), so budgets are isolated per tenant — a security
    control, like the throttle counters. Like the DRF throttle, this is a
    fixed-window counter (the period stamp resets it); check-then-reserve is not
    strictly atomic across replicas, which is acceptable for the MVP and documented
    (the precise-enforcement upgrade path is a Redis Lua INCR, same as throttling).
    The Module-10 LLMGateway calls this BEFORE invoking an agent.
    """
    tid = _tenant_id(tenant)
    limit = resolve_budget_limit(tenant, agent_code, window)
    period = _budget_period(window, now)
    key = tenant_cache_key(tid, _BUDGET_COUNTER_PART, agent_code, window, period)
    current = cache.get(key) or 0
    if current >= limit:
        raise BudgetExceeded(agent_code=agent_code, window=window, limit=limit)
    # Reserve: ensure the key exists (with the window TTL) then atomically incr.
    cache.add(key, 0, _budget_ttl(window))
    try:
        reserved = cache.incr(key)
    except ValueError:
        # The key expired between add and incr (a rare race) — re-seed at 1.
        cache.set(key, 1, _budget_ttl(window))
        reserved = 1
    return {"reserved": reserved, "limit": limit, "window": window, "agent_code": agent_code}
