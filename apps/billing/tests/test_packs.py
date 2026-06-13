"""
Unit tests for the pure-data pack layer (no DB).

Proves the agent mapping, the safe-ignore behaviour for unknown packs, the
union semantics across multiple packs, and that ``tier_label`` is a pure display
helper.
"""
from apps.billing.packs import (
    AGENT1,
    AGENT2,
    AGENT3,
    AGENT4,
    AGENT5,
    FULL_AI,
    STARTER,
    agents_for_packs,
    tier_label,
)


def test_starter_unlocks_only_agent_2():
    # Commercial repackaging: Agent 1 is now PREMIUM (FULL_AI). STARTER's only agent
    # is Agent 2 (the Fast KPI-nudge lane).
    assert agents_for_packs([STARTER]) == {AGENT2}


def test_full_ai_unlocks_all_five_agents():
    assert agents_for_packs([FULL_AI]) == {AGENT1, AGENT2, AGENT3, AGENT4, AGENT5}


def test_agents_for_packs_unions_across_packs():
    assert agents_for_packs([STARTER, FULL_AI]) == {AGENT1, AGENT2, AGENT3, AGENT4, AGENT5}


def test_unknown_pack_codes_are_ignored_safely():
    assert agents_for_packs(["NOPE"]) == set()
    assert agents_for_packs([STARTER, "NOPE"]) == {AGENT2}


def test_empty_and_none_pack_lists_unlock_nothing():
    assert agents_for_packs([]) == set()
    assert agents_for_packs(None) == set()


def test_tier_label_is_display_only():
    assert tier_label([STARTER]) == "Starter"
    assert tier_label([FULL_AI]) == "Full AI"
    assert tier_label([STARTER, FULL_AI]) == "Full AI"
    assert tier_label([]) == "Starter"
