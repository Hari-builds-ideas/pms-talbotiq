"""
``GET /api/billing/ai-usage`` — the admin-facing view of AI spend.

The enforcement side (AgentBudget + the gateway's reservation) already existed; this
endpoint is the half that lets an admin SEE it. The tests below care about two things:
that the numbers are real, and that an admin can only ever see their OWN tenant's.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user

pytestmark = pytest.mark.django_db

AI_USAGE = "/api/billing/ai-usage"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def other_org(db):
    """A SECOND tenant, so the isolation tests have a real boundary to cross.

    Defined here rather than in the shared conftest: only these tests need it, and a
    second tenant in the global fixture would quietly change what every other test
    is exercising.
    """
    from types import SimpleNamespace

    from apps.testsupport.factories import TenantFactory, UserFactory

    tenant = TenantFactory(slug="globex", name="Globex")
    admin = UserFactory(tenant=tenant, role="ADMIN", email="admin@globex.test")
    return SimpleNamespace(tenant=tenant, admin=admin)


def _ledger(tenant, *, agent_code="chat", model="gemini-2.5-flash",
            prompt=1000, completion=200, ago_days=1):
    """Write a TokenLedger row inside ``tenant``'s scope, as the gateway does."""
    from apps.billing.models import TokenLedger
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant.id):
        return TokenLedger.objects.create(
            tenant_id=tenant.id,
            agent_code=agent_code,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            occurred_at=timezone.now() - timedelta(days=ago_days),
        )


def test_admin_sees_their_own_usage(org):
    _ledger(org.tenant, agent_code="chat", prompt=1000, completion=200)
    _ledger(org.tenant, agent_code="review", prompt=500, completion=100)

    r = _client_for(org.admin).get(AI_USAGE)
    assert r.status_code == 200
    body = r.json()

    assert body["calls"] == 2
    assert body["prompt_tokens"] == 1500
    assert body["completion_tokens"] == 300
    assert body["total_tokens"] == 1800
    assert {a["agent_code"] for a in body["by_agent"]} == {"chat", "review"}
    assert body["by_model"][0]["model"] == "gemini-2.5-flash"


def test_cost_is_labelled_an_estimate_everywhere_it_appears(org):
    """A confident total from a price table in the repo would be a made-up number."""
    _ledger(org.tenant)
    body = _client_for(org.admin).get(AI_USAGE).json()

    assert body["cost_is_estimate"] is True
    assert "invoice" in body["note"].lower()
    assert isinstance(body["estimated_cost_usd"], float)


def test_an_unpriced_model_is_named_not_silently_counted_as_free(org):
    """Usage on a model with no price entry must surface, or the total reads as
    complete when it is not."""
    _ledger(org.tenant, model="some-model-we-have-no-price-for")
    body = _client_for(org.admin).get(AI_USAGE).json()

    assert "some-model-we-have-no-price-for" in body["unpriced_models"]


def test_usage_never_crosses_a_tenant_boundary(org, other_org):
    """The whole point of the endpoint scoping. An admin of one tenant must not see
    another tenant's consumption — the view takes the slug from the CALLER, and there
    is deliberately no parameter to name a different one."""
    _ledger(org.tenant, agent_code="chat", prompt=1000, completion=200)
    _ledger(other_org.tenant, agent_code="chat", prompt=999_000, completion=999_000)

    body = _client_for(org.admin).get(AI_USAGE).json()

    assert body["calls"] == 1
    assert body["total_tokens"] == 1200  # NOT 1_999_200


def test_a_query_param_cannot_widen_the_tenant(org, other_org):
    """Belt and braces: even if a caller guesses the parameter name the CLI uses,
    the response must stay their own."""
    _ledger(org.tenant, prompt=100, completion=10)
    _ledger(other_org.tenant, prompt=888_000, completion=888_000)

    for attempt in (f"?tenant={other_org.tenant.slug}",
                    f"?tenant_slug={other_org.tenant.slug}",
                    "?tenant="):
        body = _client_for(org.admin).get(AI_USAGE + attempt).json()
        assert body["total_tokens"] == 110, f"{attempt} widened the scope"


def test_days_window_is_clamped(org):
    """An unbounded ?days= is an unbounded scan."""
    _ledger(org.tenant, ago_days=200)

    inside = _client_for(org.admin).get(AI_USAGE + "?days=365").json()
    outside = _client_for(org.admin).get(AI_USAGE + "?days=7").json()
    assert inside["calls"] == 1
    assert outside["calls"] == 0

    assert _client_for(org.admin).get(AI_USAGE + "?days=99999").json()["days"] == 365
    assert _client_for(org.admin).get(AI_USAGE + "?days=0").json()["days"] == 1
    assert _client_for(org.admin).get(AI_USAGE + "?days=nonsense").json()["days"] == 30


def test_budgets_in_force_are_reported(org):
    """The caps the usage runs against, so the number has something to mean."""
    from apps.billing.models import AgentBudget
    from apps.tenancy.context import tenant_context

    with tenant_context(org.tenant.id):
        AgentBudget.objects.create(tenant_id=org.tenant.id, agent_code="chat",
                                   window="DAILY", limit=250)

    body = _client_for(org.admin).get(AI_USAGE).json()
    assert {"agent_code": "chat", "window": "DAILY", "limit": 250} in body["budgets"]


@pytest.mark.parametrize("role", ["manager", "report"])
def test_non_admins_are_refused(org, role):
    """Spend is admin-only: it is commercially sensitive and tenant-wide."""
    assert _client_for(getattr(org, role)).get(AI_USAGE).status_code == 403


def test_anonymous_is_refused():
    assert APIClient().get(AI_USAGE).status_code == 401
