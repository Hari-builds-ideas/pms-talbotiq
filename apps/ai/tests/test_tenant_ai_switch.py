"""
The per-tenant AI on/off switch (item 11).

Enforced at the LLMGateway because that is the single choke point every agent goes
through — a switch enforced in the UI leaves every endpoint reachable, and one
enforced in `run` alone leaves `run_tools` (the whole chat assistant) running.
"""
import pytest

from apps.administration.models import TenantConfig
from apps.ai.gateway import AI_DISABLED_DETAIL, LLMGateway
from apps.ai.tenant_switch import AI_ENABLED_KEY, ai_enabled_for
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _set_switch(tenant, value):
    with tenant_context(tenant.id):
        config, _ = TenantConfig.objects.get_or_create(
            tenant_id=tenant.id, defaults={"settings": {}}
        )
        config.settings = {**(config.settings or {}), AI_ENABLED_KEY: value}
        config.save(update_fields=["settings"])


# ── the helper ───────────────────────────────────────────────────────────────


def test_absent_config_means_enabled(org):
    """Default ON: a tenant is never silently deprived of a feature they pay for by
    a config row that has not been written yet."""
    assert ai_enabled_for(org.tenant) is True


def test_switch_off_is_read(org):
    _set_switch(org.tenant, False)
    assert ai_enabled_for(org.tenant) is False


def test_switch_back_on(org):
    _set_switch(org.tenant, False)
    _set_switch(org.tenant, True)
    assert ai_enabled_for(org.tenant) is True


def test_other_keys_in_the_bag_are_untouched(org):
    """It shares TenantConfig.settings with unrelated tenant preferences."""
    with tenant_context(org.tenant.id):
        TenantConfig.objects.create(tenant_id=org.tenant.id, settings={"locale": "en-GB"})
    _set_switch(org.tenant, False)
    with tenant_context(org.tenant.id):
        assert TenantConfig.objects.get(tenant_id=org.tenant.id).settings["locale"] == "en-GB"


def test_it_fails_open(org, monkeypatch):
    """A database hiccup must not read as "AI off" for every tenant at once. The
    security controls are the entitlement gate, RBAC and tenant scoping — this is a
    customer preference, and failing closed here is the worse outcome."""
    import apps.ai.tenant_switch as mod

    def boom(*a, **k):
        raise RuntimeError("database is having a moment")

    monkeypatch.setattr(mod, "tenant_context", boom, raising=False)
    assert ai_enabled_for(org.tenant) is True


# ── enforcement at the gateway ───────────────────────────────────────────────


@pytest.mark.django_db
def test_run_is_blocked_when_switched_off(org, settings):
    settings.LLM_PROVIDER = FAKE["LLM_PROVIDER"]
    _set_switch(org.tenant, False)

    result = LLMGateway().run(tenant=org.tenant, agent_code="chat", prompt="hello")

    assert result.ok is False
    assert result.status == "NOT_CONFIGURED"
    assert AI_DISABLED_DETAIL in result.errors


@pytest.mark.django_db
def test_run_tools_is_blocked_too(org, settings):
    """The other door. A kill switch covering one of two is not a kill switch —
    run_tools is the path the whole chat assistant uses."""
    settings.LLM_PROVIDER = FAKE["LLM_PROVIDER"]
    _set_switch(org.tenant, False)

    result = LLMGateway().run_tools(
        tenant=org.tenant, agent_code="chat",
        messages=[{"role": "user", "content": "hello"}], tools=[],
    )

    assert result.ok is False
    assert result.status == "NOT_CONFIGURED"
    assert AI_DISABLED_DETAIL in result.errors


@pytest.mark.django_db
def test_switched_on_still_reaches_the_provider(org, settings):
    """The switch must not become a permanent off — the default path still works."""
    settings.LLM_PROVIDER = FAKE["LLM_PROVIDER"]
    _set_switch(org.tenant, True)

    result = LLMGateway().run(tenant=org.tenant, agent_code="chat", prompt="hello")

    assert AI_DISABLED_DETAIL not in (result.errors or [])


@pytest.mark.django_db
def test_a_disabled_tenant_does_not_disable_another(org, settings):
    """Switching AI off is per tenant, like everything else here."""
    from apps.testsupport.factories import TenantFactory

    settings.LLM_PROVIDER = FAKE["LLM_PROVIDER"]
    other = TenantFactory(slug="globex-ai", name="Globex")
    _set_switch(org.tenant, False)

    assert ai_enabled_for(org.tenant) is False
    assert ai_enabled_for(other) is True
