"""
Feature packs — pure data + functions, no Django.

The commercial model is **decoupled**: a tenant's entitlement is the product of
two INDEPENDENT axes —

* ``seat_count`` — a plain integer, owned by the ``Entitlement`` model.
* ``feature_packs`` — a set of pack codes; each pack unlocks a set of AI agents.

"Tier" is **not** an enforcement concept. ``tier_label`` exists only to render a
friendly badge in the UI; nothing in the system ever gates on a tier. Seats and
packs move independently of each other and of any label.

This module is pure data + pure functions (no Django, no DB, no I/O), so it is
trivially testable and importable from anywhere (models, services, views).
"""
from __future__ import annotations

# --- Pack codes -------------------------------------------------------------
STARTER = "STARTER"
FULL_AI = "FULL_AI"

# --- Agent codes ------------------------------------------------------------
AGENT1 = "agent1"
AGENT2 = "agent2"
AGENT3 = "agent3"
AGENT4 = "agent4"
AGENT5 = "agent5"

#: pack code -> the agents that pack unlocks. STARTER ships agents 1-2; FULL_AI
#: unlocks the whole suite (1-5). These sets are independent of seat_count.
FEATURE_PACKS: dict[str, frozenset[str]] = {
    STARTER: frozenset({AGENT1, AGENT2}),
    FULL_AI: frozenset({AGENT1, AGENT2, AGENT3, AGENT4, AGENT5}),
}


def agents_for_packs(pack_codes) -> set[str]:
    """Return the union of agents unlocked by ``pack_codes``.

    Unknown pack codes are ignored safely (they contribute no agents), so a
    persisted list with a stale/typo code never raises — it just unlocks
    nothing for that entry. ``pack_codes`` may be any iterable of strings.
    """
    unlocked: set[str] = set()
    for code in pack_codes or ():
        unlocked |= FEATURE_PACKS.get(code, frozenset())
    return unlocked


def tier_label(pack_codes) -> str:
    """DISPLAY ONLY — a human-friendly badge for the UI.

    This is **never** used for enforcement: access is decided solely by the
    seats × packs the entitlement actually holds (see ``agents_for_packs`` and
    the entitlement gate). Returns ``"Full AI"`` when the FULL_AI pack is
    present, otherwise ``"Starter"``.
    """
    codes = set(pack_codes or ())
    return "Full AI" if FULL_AI in codes else "Starter"
