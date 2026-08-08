"""
The AI usage + cost report (FINAL2 unit 3).

Every LLM call already wrote a TokenLedger row; nobody was reading the meter. What is
under test here is that reading it gives an operator a true picture — and that the parts
which cannot be true are labelled rather than guessed.
"""
import pytest
from django.test import override_settings
from django.utils import timezone

from datetime import timedelta

from apps.billing.models import TokenLedger
from apps.billing.usage import collect, price_for, resolve_model
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

PRICES = {"LLM_PRICES": {"gemini-2.5-flash": {"in": 1.0, "out": 10.0},
                         "free-model": {"in": 0.0, "out": 0.0}}}


def _usage(tenant, *, agent="chat", model="gemini-2.5-flash", p=1000, c=100, days_ago=0):
    with tenant_context(tenant.id):
        return TokenLedger.objects.create(
            tenant_id=tenant.id, agent_code=agent, model=model,
            prompt_tokens=p, completion_tokens=c, total_tokens=p + c,
            occurred_at=timezone.now() - timedelta(days=days_ago))


@override_settings(**PRICES)
def test_it_reads_the_ledger_that_the_gateway_writes(tenant):
    """The first version queried across tenants and reported ZERO against a ledger
    holding thousands of rows: every manager on a TenantScopedModel filters by the
    ambient tenant and returns nothing outside one. This is that regression."""
    _usage(tenant)
    _usage(tenant, agent="planner")

    usage = collect(days=30)

    assert usage.calls == 2, "reading the ledger must not depend on ambient tenant state"
    assert usage.total_tokens == 2200


@override_settings(**PRICES)
def test_the_cost_is_computed_per_million_tokens_split_in_and_out(tenant):
    _usage(tenant, p=1_000_000, c=1_000_000)

    usage = collect(days=30)

    # 1M in at $1 + 1M out at $10.
    assert round(usage.cost_usd, 4) == 11.0


@override_settings(**PRICES)
def test_the_window_excludes_older_usage(tenant):
    _usage(tenant, days_ago=1)
    _usage(tenant, days_ago=40)

    assert collect(days=7).calls == 1
    assert collect(days=90).calls == 2


@override_settings(**PRICES)
def test_one_tenants_usage_can_be_isolated(tenant, django_user_model):
    from apps.testsupport.factories import TenantFactory

    other = TenantFactory(slug="other-co")
    _usage(tenant)
    _usage(other)
    _usage(other)

    assert collect(days=30).calls == 3
    assert collect(days=30, tenant_slug="other-co").calls == 2


@override_settings(**PRICES)
def test_a_model_with_no_price_is_reported_not_silently_free(tenant):
    """Counting unknown usage as $0 would understate the bill without saying so."""
    _usage(tenant, model="some-new-model")

    usage = collect(days=30)

    assert usage.cost_usd == 0.0
    assert usage.unpriced_models == ["some-new-model"], \
        "an unpriced model has to surface, or the total quietly lies"


@override_settings(**PRICES, GEMINI_MODEL_MAP={"chat": "gemini-2.5-flash"})
def test_a_logical_tier_is_priced_as_the_model_it_runs_on(tenant):
    """Some rows record `chat`, the tier asked for, when the provider's response did
    not name a model. Treating those as unknown made the estimate understate real
    spend — on this repo's own ledger, by about 15%."""
    _usage(tenant, model="chat", p=1_000_000, c=0)

    usage = collect(days=30)

    assert resolve_model("chat") == "gemini-2.5-flash"
    assert usage.unpriced_models == []
    assert round(usage.cost_usd, 4) == 1.0


@override_settings(**PRICES)
def test_prefix_matching_prices_a_dated_model_id():
    assert price_for("gemini-2.5-flash-002")["in"] == 1.0
    assert price_for("something-else") == {}


@override_settings(**PRICES)
def test_the_rollup_orders_by_spend(tenant):
    _usage(tenant, agent="cheap", p=10, c=1)
    _usage(tenant, agent="dear", p=1_000_000, c=100_000)

    by_agent = collect(days=30).by("agent_code")

    assert [name for name, _ in by_agent] == ["dear", "cheap"], \
        "the expensive thing is what an operator opened this to find"
