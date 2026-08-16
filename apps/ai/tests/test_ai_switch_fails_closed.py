"""
The tenant AI switch fails CLOSED (B4).

The original implementation failed OPEN on a read error, reasoning that this is a
preference rather than a security control. That reasoning was wrong: we tell
customers this switch is how they stop employee performance data leaving for a
model provider. Once that is the promise, "we could not read your preference, so
we sent the data anyway" is the one outcome that is never acceptable.
"""
import pytest

from apps.ai.tenant_switch import ai_enabled_for, set_ai_enabled
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory

pytestmark = pytest.mark.django_db

# ── behaviour


def test_ai_is_on_by_default_for_a_tenant_that_never_touched_the_setting():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        assert ai_enabled_for(t) is True


def test_switch_off_is_honoured():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        set_ai_enabled(t, False)
        assert ai_enabled_for(t) is False


def test_switch_fails_closed_when_it_cannot_be_read():
    """B4. The original implementation failed OPEN, which meant a database hiccup
    silently re-enabled sending employee data to a model provider — the exact
    thing the customer switched off."""
    import apps.ai.models as ai_models

    t = TenantFactory(slug="acme")

    class ExplodingManager:
        def filter(self, *a, **k):
            raise RuntimeError("database is having a moment")

    saved = ai_models.TenantAIConfig.objects
    try:
        ai_models.TenantAIConfig.objects = ExplodingManager()
        with tenant_context(t.id):
            assert ai_enabled_for(t) is False
    finally:
        ai_models.TenantAIConfig.objects = saved


def test_switch_is_off_without_a_tenant():
    # No tenant to consult; refusing is the safe reading.
    assert ai_enabled_for(None) is False


def test_legacy_pre_b1_setting_is_still_honoured():
    """Tenants who switched AI off before B1 stored it in TenantConfig.settings.
    Their choice must survive without a data migration."""
    from apps.administration.models import TenantConfig

    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        TenantConfig.objects.create(tenant=t, settings={"ai_enabled": False})
        assert ai_enabled_for(t) is False
