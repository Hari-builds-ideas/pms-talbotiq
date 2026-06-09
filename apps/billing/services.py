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

from apps.audit.services import record
from apps.core.cache import invalidate_tenant_cache, tenant_cache_key
from apps.tenancy.context import tenant_context

from .models import DEFAULT_PACKS, Entitlement
from .packs import FULL_AI, agents_for_packs

#: Time-to-live (seconds) for a cached entitlement read.
_ENTITLEMENT_CACHE_TTL = 300
#: Cache key suffix identifying a tenant's cached entitlement.
_ENTITLEMENT_CACHE_PART = "entitlement"

#: Time-to-live (seconds) for a cached rate-limit map.
_RATE_LIMITS_CACHE_TTL = 300
#: Cache key suffix identifying a tenant's cached rate-limit map.
_RATE_LIMITS_CACHE_PART = "rate_limits"

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
