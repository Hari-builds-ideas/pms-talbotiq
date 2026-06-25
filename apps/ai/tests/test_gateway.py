"""
The LLMGateway — the single LLM choke + safety pipeline: NotConfigured → 503-class
result; per-tenant budget enforced BEFORE the call; PII scrubbed before the provider
sees the prompt; output schema-validated; usage metered to the TokenLedger;
confidence + low-confidence flag. The gateway NEVER raises to its caller.
"""
import pytest
from django.test import override_settings

from apps.ai import providers
from apps.ai.gateway import gateway
from apps.ai.providers import llm_configured
from apps.billing.models import AgentBudget, TokenLedger
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"
_SEEN_PROMPTS = []


def _register(agent_code="test_agent", *, content=None):
    def builder(prompt, model):
        _SEEN_PROMPTS.append(prompt)
        return content if content is not None else {"summary": "ok"}

    providers.register_fake_output(agent_code, builder)


@pytest.fixture(autouse=True)
def _reset():
    _SEEN_PROMPTS.clear()
    yield


# ── NotConfigured (production default) ────────────────────────────────────────


def test_not_configured_is_a_structured_result_not_an_exception(tenant):
    # Default LLM_PROVIDER = NotConfiguredProvider.
    assert llm_configured() is False
    result = gateway.run(tenant=tenant, agent_code="test_agent", prompt="hi")
    assert result.status == "NOT_CONFIGURED"
    assert result.ok is False


@override_settings(LLM_PROVIDER=FAKE)
def test_fake_provider_runs_the_full_pipeline(tenant):
    assert llm_configured() is True
    _register(content={"summary": "Quarterly review draft."})
    result = gateway.run(
        tenant=tenant, agent_code="test_agent", prompt="draft please",
        schema={"summary": str},
    )
    assert result.status == "OK" and result.ok
    assert result.content["summary"] == "Quarterly review draft."
    assert result.confidence == 0.9
    assert result.usage["total_tokens"] > 0
    # Usage metered to the TokenLedger.
    with tenant_context(tenant):
        assert TokenLedger.objects.filter(agent_code="test_agent").count() == 1


# ── budget enforced BEFORE the call ───────────────────────────────────────────


@override_settings(LLM_PROVIDER=FAKE)
def test_budget_is_enforced_before_the_call(tenant):
    _register()
    with tenant_context(tenant):
        AgentBudget.objects.create(tenant_id=tenant.id, agent_code="test_agent", window="DAILY", limit=1)
    assert gateway.run(tenant=tenant, agent_code="test_agent", prompt="x").status == "OK"
    over = gateway.run(tenant=tenant, agent_code="test_agent", prompt="x")
    assert over.status == "BUDGET_EXCEEDED"
    # The over-budget call did NOT meter a second usage row (it never called out).
    with tenant_context(tenant):
        assert TokenLedger.objects.filter(agent_code="test_agent").count() == 1


# ── PII scrubbed before the provider sees it ──────────────────────────────────


@override_settings(LLM_PROVIDER=FAKE)
def test_pii_is_scrubbed_before_the_provider(tenant):
    _register()
    gateway.run(tenant=tenant, agent_code="test_agent", prompt="email alice@acme.test now")
    assert _SEEN_PROMPTS  # the provider was called
    assert "alice@acme.test" not in _SEEN_PROMPTS[0]
    assert "[REDACTED-EMAIL]" in _SEEN_PROMPTS[0]


# ── schema validation rejects malformed output ────────────────────────────────


@override_settings(LLM_PROVIDER=FAKE)
def test_schema_invalid_output_is_flagged(tenant):
    _register(content={"wrong_key": "x"})  # missing required "summary"
    result = gateway.run(
        tenant=tenant, agent_code="test_agent", prompt="x", schema={"summary": str}
    )
    assert result.status == "SCHEMA_INVALID"
    assert any("summary" in e for e in result.errors)


# ── low-confidence flag ────────────────────────────────────────────────────────


@override_settings(LLM_PROVIDER=FAKE)
def test_low_confidence_is_flagged(tenant):
    _register()
    providers.set_fake_confidence("test_agent", 0.5)
    try:
        result = gateway.run(tenant=tenant, agent_code="test_agent", prompt="x")
    finally:
        providers.set_fake_confidence("test_agent", 0.9)
    assert result.ok
    assert result.low_confidence is True


# ── usage is tenant-isolated ───────────────────────────────────────────────────


@override_settings(LLM_PROVIDER=FAKE)
def test_usage_is_tenant_isolated(tenant, other_tenant):
    _register()
    gateway.run(tenant=tenant, agent_code="test_agent", prompt="x")
    with tenant_context(other_tenant):
        assert TokenLedger.objects.count() == 0


# ── global ceiling degrades GRACEFULLY (audit Finding A) ─────────────────────────


@override_settings(LLM_PROVIDER=FAKE)
def test_global_ceiling_maps_to_budget_exceeded_and_refunds(tenant):
    """A run-wide LLM-ceiling hit is a graceful limit, not a provider failure: the
    gateway returns BUDGET_EXCEEDED (→ async DEGRADED / chat 429), NOT PROVIDER_ERROR
    (→ FAILED / 503), and REFUNDS the per-tenant reservation (no real call happened)."""
    from apps.ai.exceptions import LLMGlobalCeilingError

    def ceiling(prompt, model):
        raise LLMGlobalCeilingError("Global LLM call ceiling (1) reached for this run.")

    providers.register_fake_output("ceil_agent", ceiling)
    with tenant_context(tenant):
        AgentBudget.objects.create(
            tenant_id=tenant.id, agent_code="ceil_agent", window="DAILY", limit=1
        )

    res = gateway.run(tenant=tenant, agent_code="ceil_agent", prompt="x")
    assert res.status == "BUDGET_EXCEEDED"  # graceful, NOT PROVIDER_ERROR
    assert any("ceiling" in str(e).lower() for e in res.errors)
    with tenant_context(tenant):
        assert TokenLedger.objects.filter(agent_code="ceil_agent").count() == 0  # never metered

    # The reservation was refunded: the limit-1 budget is intact, so a real call
    # still succeeds (had the ceiling burned the reservation, this would be 429'd).
    providers.register_fake_output("ceil_agent", lambda p, m: {"summary": "ok"})
    ok = gateway.run(
        tenant=tenant, agent_code="ceil_agent", prompt="x", schema={"summary": str}
    )
    assert ok.status == "OK"
