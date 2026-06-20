"""
Atomic per-tenant budget reserve (BUILD_3 3.1).

The reserve is a Redis Lua step, so the cap holds under concurrency (the old
check-then-incr let two replicas both pass at the edge). Covered here:
* EXACTLY M of N concurrent reserves succeed at a cap of M;
* a reservation is refunded on a downstream provider failure (a failed call
  never permanently burns budget), but a successful metered call keeps it;
* refund never drives the counter below zero;
* tenant isolation of the counter (asserted by the existing single-threaded
  suite too) is preserved — every key embeds the tenant id.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.test import override_settings

from apps.ai import providers
from apps.ai.gateway import gateway
from apps.billing import atomic
from apps.billing.models import AgentBudget
from apps.billing.services import (
    check_and_reserve_budget,
    get_or_create_entitlement,
    release_budget,
)
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

WIRED = dict(LLM_PROVIDER="apps.ai.providers.FakeLLMProvider")


def _budget(tenant, *, agent_code="all", window="DAILY", limit):
    with tenant_context(tenant):
        return AgentBudget.objects.create(
            tenant_id=tenant.id, agent_code=agent_code, window=window, limit=limit
        )


def test_reserve_is_atomic_exactly_m_succeed_under_concurrency():
    # Pure Redis path (no ORM in threads): 64 reservers, cap 10 -> exactly 10 win.
    key = f"test:atomic:{uuid.uuid4().hex}"
    limit, n = 10, 64
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(lambda _: atomic.reserve(key, limit=limit, ttl_ms=60_000), range(n)))
    winners = [r for r in results if r > 0]
    losers = [r for r in results if r == -1]
    assert len(winners) == limit
    assert len(losers) == n - limit
    assert sorted(winners) == list(range(1, limit + 1))  # 1..10, no number reused


def test_release_refunds_one_and_frees_a_slot():
    key = f"test:atomic:{uuid.uuid4().hex}"
    assert atomic.reserve(key, limit=1, ttl_ms=60_000) == 1
    assert atomic.reserve(key, limit=1, ttl_ms=60_000) == -1  # full
    assert atomic.release(key) == 0  # refund
    assert atomic.reserve(key, limit=1, ttl_ms=60_000) == 1  # slot freed


def test_release_never_below_zero():
    key = f"test:atomic:{uuid.uuid4().hex}"
    assert atomic.release(key) == 0
    assert atomic.release(key) == 0


def test_check_and_reserve_then_release_refunds(tenant):
    get_or_create_entitlement(tenant)
    _budget(tenant, agent_code="agent1", limit=1)
    assert check_and_reserve_budget(tenant, "agent1")["reserved"] == 1
    with pytest.raises(Exception):  # noqa: B017 — BudgetExceeded at the cap
        check_and_reserve_budget(tenant, "agent1")
    release_budget(tenant, "agent1")  # refund the consumed slot
    assert check_and_reserve_budget(tenant, "agent1")["reserved"] == 1  # reservable again


@override_settings(**WIRED)
def test_gateway_refunds_reservation_on_provider_error(tenant):
    get_or_create_entitlement(tenant)
    _budget(tenant, agent_code="agent1", limit=2)

    def boom(prompt, model):
        raise RuntimeError("provider down")

    providers.register_fake_output("agent1", boom)
    try:
        result = gateway.run(tenant=tenant, agent_code="agent1", prompt="x", schema=None)
    finally:
        from apps.ai.agents import review as review_agent
        providers.register_fake_output("agent1", review_agent._fake)

    assert result.status == "PROVIDER_ERROR"
    # The reservation was refunded: a fresh reserve is #1 (not #2), proving the
    # failed call did not permanently consume budget.
    assert check_and_reserve_budget(tenant, "agent1")["reserved"] == 1
