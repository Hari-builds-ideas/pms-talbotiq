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

# --- Non-agent gated feature codes (Module 11 surfaces these as feature flags) -
#: The Chat Assistant (Module 10, Fast + read-only) — ships in STARTER.
CHAT = "chat"
#: The AI JD Generator (Module 6 seam, filled in Module 10) — FULL_AI only.
JD_GENERATOR = "jd_generator"
#: The Career Roadmap agent (Module 9 seam, filled in Module 10) — FULL_AI only.
CAREER_ROADMAP = "career_roadmap"

#: pack code -> the agents that pack unlocks. COMMERCIAL PACKAGING (Hari's decision,
#: resolving NEEDS_HARI_pack_mapping): every GENERATIVE agent — including Agent 1
#: (Review Assistant) — is PREMIUM. STARTER ships only Agent 2 (KPI Intelligence,
#: the Fast nudge lane); FULL_AI unlocks the whole suite (1-5). Independent of
#: seat_count.
FEATURE_PACKS: dict[str, frozenset[str]] = {
    STARTER: frozenset({AGENT2}),
    FULL_AI: frozenset({AGENT1, AGENT2, AGENT3, AGENT4, AGENT5}),
}

#: pack code -> the FULL feature set it unlocks (agents PLUS the non-agent features
#: chat / jd_generator / career_roadmap). A SUPERSET of ``FEATURE_PACKS`` and what
#: ``feature_flags_for`` (Module 11) resolves. STARTER's "AI taste" is Agent 2 +
#: Chat (the Fast, read-only lane); every generative surface — Agent 1 + Agents 3-5,
#: the JD generator and the career roadmap — is FULL_AI-only.
PACK_FEATURES: dict[str, frozenset[str]] = {
    STARTER: frozenset({AGENT2, CHAT}),
    FULL_AI: frozenset(
        {AGENT1, AGENT2, AGENT3, AGENT4, AGENT5, CHAT, JD_GENERATOR, CAREER_ROADMAP}
    ),
}

#: Every gated feature code in the system — the stable key set ``feature_flags_for``
#: always returns a boolean for (so the frontend can rely on a complete map).
ALL_FEATURES: frozenset[str] = frozenset(
    {AGENT1, AGENT2, AGENT3, AGENT4, AGENT5, CHAT, JD_GENERATOR, CAREER_ROADMAP}
)


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


def features_for_packs(pack_codes) -> set[str]:
    """Return the union of ALL features (agents + non-agent) unlocked by
    ``pack_codes``. Unknown codes contribute nothing (never raises)."""
    unlocked: set[str] = set()
    for code in pack_codes or ():
        unlocked |= PACK_FEATURES.get(code, frozenset())
    return unlocked


#: Default per-agent call budgets per window, by pack tier (Module 11). STARTER
#: caps lower than FULL_AI. Used by ``check_and_reserve_budget`` when a tenant has
#: no explicit ``AgentBudget`` row. Derived from the entitlement (FULL_AI present
#: → the higher cap), so an upgrade lifts budgets along with feature flags.
DEFAULT_AGENT_BUDGETS: dict[str, dict[str, int]] = {
    "DAILY": {STARTER: 50, FULL_AI: 500},
    "MONTHLY": {STARTER: 1000, FULL_AI: 10000},
}


def default_budget_limit(window: str, has_full_ai: bool) -> int:
    """The entitlement-derived default budget limit for ``window`` (DAILY/MONTHLY),
    choosing the FULL_AI cap when the tenant holds that pack, else the STARTER cap.
    An unknown window falls back to the DAILY caps (never raises)."""
    tier = FULL_AI if has_full_ai else STARTER
    return DEFAULT_AGENT_BUDGETS.get(window, DEFAULT_AGENT_BUDGETS["DAILY"])[tier]


def tier_label(pack_codes) -> str:
    """DISPLAY ONLY — a human-friendly badge for the UI.

    This is **never** used for enforcement: access is decided solely by the
    seats × packs the entitlement actually holds (see ``agents_for_packs`` and
    the entitlement gate). Returns ``"Full AI"`` when the FULL_AI pack is
    present, otherwise ``"Starter"``.
    """
    codes = set(pack_codes or ())
    return "Full AI" if FULL_AI in codes else "Starter"
