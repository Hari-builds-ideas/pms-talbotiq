"""
Module-11 per-tenant agent-call budgets + usage metering.

Headline properties: ``check_and_reserve_budget`` trips at the limit and isolates
per tenant (every counter key embeds the tenant id); the limit derives from the
entitlement (STARTER < FULL_AI) unless an explicit ``AgentBudget`` overrides it;
``record_usage`` writes ledger rows.
"""
import pytest

from apps.billing import packs
from apps.billing.exceptions import BudgetExceeded
from apps.billing.models import AgentBudget, TokenLedger
from apps.billing.services import (
    check_and_reserve_budget,
    get_or_create_entitlement,
    record_usage,
    resolve_budget_limit,
    upgrade_to_full_ai,
)
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


def _budget(tenant, *, agent_code="all", window="DAILY", limit):
    with tenant_context(tenant):
        return AgentBudget.objects.create(
            tenant_id=tenant.id, agent_code=agent_code, window=window, limit=limit
        )


# ── budget enforcement ─────────────────────────────────────────────────────────


def test_budget_trips_at_the_limit(tenant):
    get_or_create_entitlement(tenant)
    _budget(tenant, agent_code="agent1", limit=2)
    assert check_and_reserve_budget(tenant, "agent1")["reserved"] == 1
    assert check_and_reserve_budget(tenant, "agent1")["reserved"] == 2
    with pytest.raises(BudgetExceeded):
        check_and_reserve_budget(tenant, "agent1")


def test_budget_is_isolated_per_tenant(tenant, other_tenant):
    get_or_create_entitlement(tenant)
    get_or_create_entitlement(other_tenant)
    _budget(tenant, agent_code="agent1", limit=1)
    _budget(other_tenant, agent_code="agent1", limit=1)
    # tenant exhausts its budget...
    check_and_reserve_budget(tenant, "agent1")
    with pytest.raises(BudgetExceeded):
        check_and_reserve_budget(tenant, "agent1")
    # ...but other_tenant's counter is untouched (keys embed the tenant id).
    assert check_and_reserve_budget(other_tenant, "agent1")["reserved"] == 1


def test_explicit_agent_budget_overrides_the_tenant_wide_default(tenant):
    get_or_create_entitlement(tenant)
    _budget(tenant, agent_code="all", window="DAILY", limit=10)
    _budget(tenant, agent_code="agent1", window="DAILY", limit=1)
    # agent1 uses its specific budget (1), not the 'all' fallback (10).
    check_and_reserve_budget(tenant, "agent1")
    with pytest.raises(BudgetExceeded):
        check_and_reserve_budget(tenant, "agent1")
    # agent2 (no specific row) falls back to the 'all' budget (10) — still allowed.
    assert check_and_reserve_budget(tenant, "agent2")["reserved"] == 1


def test_budget_exceeded_carries_an_upgrade_hint(tenant):
    get_or_create_entitlement(tenant)
    _budget(tenant, agent_code="agent1", limit=1)
    check_and_reserve_budget(tenant, "agent1")
    with pytest.raises(BudgetExceeded) as exc:
        check_and_reserve_budget(tenant, "agent1")
    detail = exc.value.detail
    assert detail["code"] == "BUDGET_EXCEEDED"
    assert "upgrade_hint" in detail


# ── budget defaults derive from the entitlement ───────────────────────────────


def test_default_limit_is_higher_after_upgrade(tenant):
    get_or_create_entitlement(tenant)  # STARTER
    starter_daily = resolve_budget_limit(tenant, "agent1", "DAILY")
    assert starter_daily == packs.DEFAULT_AGENT_BUDGETS["DAILY"][packs.STARTER]

    upgrade_to_full_ai(tenant, actor=None)
    full_daily = resolve_budget_limit(tenant, "agent1", "DAILY")
    assert full_daily == packs.DEFAULT_AGENT_BUDGETS["DAILY"][packs.FULL_AI]
    assert full_daily > starter_daily  # an upgrade lifts budgets too


def test_the_tool_calling_agent_gets_room_for_the_same_number_of_ANSWERS(tenant):
    """The budget unit is a CALL, and that is right — a call is what costs money. But
    the caps were sized when every agent spent one call per answer, so the daily
    allowance also read as "questions you may ask". The function-calling assistant spends
    one call per tool ROUND, so on the flat cap a STARTER tenant's fifty calls bought
    about eight questions. Its default is scaled to match."""
    get_or_create_entitlement(tenant)
    ordinary = resolve_budget_limit(tenant, "chat", "DAILY")
    agentic = resolve_budget_limit(tenant, "chat_agent", "DAILY")

    assert agentic == ordinary * packs.AGENT_CALL_MULTIPLIERS["chat_agent"]
    assert agentic > ordinary


def test_the_multiplier_still_matches_the_loops_round_ceiling():
    """`packs` deliberately does NOT import from `apps.ai` — billing must not depend on
    the AI app. The cost of stating the number twice is that they can drift, so this is
    the thing that notices."""
    from apps.ai.agent_loop import MAX_ROUNDS

    assert packs.AGENT_CALL_MULTIPLIERS["chat_agent"] == MAX_ROUNDS


def test_an_explicit_budget_row_still_overrides_the_scaled_default(tenant):
    """The multiplier is a DEFAULT. A tenant that has been given an explicit ceiling
    keeps exactly that ceiling — scaling it behind their back would be the opposite of
    what an explicit row is for."""
    get_or_create_entitlement(tenant)
    _budget(tenant, agent_code="chat_agent", limit=7)

    assert resolve_budget_limit(tenant, "chat_agent", "DAILY") == 7


# ── usage metering ──────────────────────────────────────────────────────────────


def test_record_usage_writes_a_ledger_row(tenant):
    row = record_usage(
        tenant, agent_code="agent1", model="fake-llm", prompt_tokens=120, completion_tokens=80
    )
    assert row.total_tokens == 200
    with tenant_context(tenant):
        assert TokenLedger.objects.filter(agent_code="agent1").count() == 1


def test_token_ledger_is_tenant_scoped(tenant, other_tenant):
    record_usage(tenant, agent_code="agent1", model="m", prompt_tokens=1, completion_tokens=1)
    with tenant_context(other_tenant):
        assert TokenLedger.objects.count() == 0
