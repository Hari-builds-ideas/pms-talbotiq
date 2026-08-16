"""
Honest "AI unavailable" states (B3).

Four different situations used to arrive at the client as one generic 503, so a
person had no way to tell whether to call their admin, wait until next month, or
retry in a minute. These pin that each situation now carries its own code.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.http import (
    AI_BUDGET_EXHAUSTED,
    AI_DISABLED,
    AI_NOT_CONFIGURED,
    AI_PROVIDER_ERROR,
    unavailable_code,
)
from apps.ai.tenant_switch import set_ai_enabled
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

PW = "pw12345!"


@pytest.fixture
def api():
    return APIClient()


def _login(api, email="u@acme.test", slug="acme"):
    resp = api.post(
        "/api/auth/login",
        {"tenant_slug": slug, "email": email, "password": PW},
        format="json",
    ).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp['access']}")


@pytest.fixture
def tenant_user():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        u = UserFactory(tenant=t, email="u@acme.test", password=PW, role="ADMIN")
    return t, u


# ── the mapping ───────────────────────────────────────────────────────────────

def test_switched_off_is_distinguished_from_never_configured(tenant_user):
    t, _u = tenant_user
    with tenant_context(t.id):
        # Nobody ever set a key: not configured.
        assert unavailable_code(t) == AI_NOT_CONFIGURED
        # The admin switched it off: a different problem, a different fix.
        set_ai_enabled(t, False)
        assert unavailable_code(t) == AI_DISABLED


def test_budget_and_provider_failures_keep_their_own_codes(tenant_user):
    t, _u = tenant_user
    with tenant_context(t.id):
        assert unavailable_code(t, gateway_status="BUDGET_EXCEEDED") == AI_BUDGET_EXHAUSTED
        assert unavailable_code(t, gateway_status="PROVIDER_ERROR") == AI_PROVIDER_ERROR
        # A malformed answer is a provider problem from the user's point of view.
        assert unavailable_code(t, gateway_status="SCHEMA_INVALID") == AI_PROVIDER_ERROR


def test_budget_exhaustion_is_429_not_503(tenant_user):
    """Returning 503 for a budget cap tells a monitoring system the service is
    broken when it is behaving exactly as configured."""
    from apps.ai.http import unavailable_response

    t, _u = tenant_user
    with tenant_context(t.id):
        assert unavailable_response(t, gateway_status="BUDGET_EXCEEDED").status_code == 429
        assert unavailable_response(t, gateway_status="PROVIDER_ERROR").status_code == 503
        assert unavailable_response(t).status_code == 503


# ── end to end through a real endpoint ────────────────────────────────────────

@override_settings(LLM_PROVIDER="apps.ai.providers.NotConfiguredProvider")
def test_chat_reports_not_configured_with_a_code(api, tenant_user):
    _login(api)
    resp = api.post("/api/ai/chat", {"query": "how am I doing?"}, format="json")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == AI_NOT_CONFIGURED
    # The sentence has to tell the reader what to DO.
    assert "administrator" in body["detail"].lower()


@override_settings(LLM_PROVIDER="apps.ai.providers.FakeLLMProvider")
def test_chat_reports_switched_off_with_its_own_code(api, tenant_user):
    t, _u = tenant_user
    with tenant_context(t.id):
        set_ai_enabled(t, False)
    _login(api)
    resp = api.post("/api/ai/chat", {"query": "how am I doing?"}, format="json")
    assert resp.status_code == 503
    body = resp.json()
    # Not "not configured": the fix is different, and blaming setup for an
    # admin's deliberate choice sends people to the wrong place.
    assert body["code"] == AI_DISABLED
    assert "switched off" in body["detail"].lower()


@override_settings(LLM_PROVIDER="apps.ai.providers.NotConfiguredProvider")
def test_meeting_summary_uses_the_same_contract(api, tenant_user):
    _login(api)
    resp = api.post("/api/ai/meeting-summary", {"notes": "we met"}, format="json")
    assert resp.status_code == 503
    assert resp.json()["code"] == AI_NOT_CONFIGURED


@override_settings(LLM_PROVIDER="apps.ai.providers.NotConfiguredProvider")
def test_every_ai_surface_returns_a_code_not_just_prose(api, tenant_user):
    """The point of B3 is that this is uniform — a client should not need a
    per-endpoint special case to know what happened."""
    _login(api)
    for path, payload in [
        ("/api/ai/chat", {"query": "hi"}),
        ("/api/ai/chat/plan", {"query": "hi"}),
        ("/api/ai/meeting-summary", {"notes": "hi"}),
        ("/api/ai/review-quality", {"text": "hi"}),
        ("/api/ai/search", {"query": "hi"}),
    ]:
        resp = api.post(path, payload, format="json")
        if resp.status_code in (503, 429):
            assert "code" in resp.json(), f"{path} returned no code"
            assert resp.json()["code"].startswith("ai_"), path
