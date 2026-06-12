"""
Chat Assistant — the safety-critical agent, over the REAL /api/ai/chat route with
the FakeLLMProvider. The HEADLINE proof: chat inherits the caller's RBAC and can
NEVER surface data the caller couldn't already see (an employee asking for a peer's
goals gets nothing — identical to a direct scoped API call); write/approval intents
are BLOCKED; the chat budget trips at 429; the entitlement gate denies a tenant
without the chat feature; no LLM provider → 503.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.billing.models import AgentBudget, Entitlement
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, UserFactory

pytestmark = pytest.mark.django_db

CHAT = "/api/ai/chat"
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _seed_goals(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        GoalFactory(employee=org.report, cycle=cycle, title="Report goal")
        GoalFactory(employee=org.peer, cycle=cycle, title="Peer goal")


@override_settings(**FAKE)
def test_employee_sees_own_goals(org):
    _seed_goals(org)
    resp = _client_for(org.report).post(CHAT, {"query": "show me my goals"}, format="json")
    assert resp.status_code == 200, resp.content
    assert "Report goal" in resp.json()["data"]


@override_settings(**FAKE)
def test_employee_cannot_see_a_peers_goals_via_chat(org):
    """HEADLINE: chat is RBAC-bound. An employee asking for a PEER's goals gets
    nothing — exactly like a direct scoped API call would."""
    _seed_goals(org)
    resp = _client_for(org.report).post(
        CHAT, {"query": f"show me {org.peer.email} goals"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["data"] == []  # NO peer data leaked
    assert "Peer goal" not in str(body)
    assert "scope" in body["answer"].lower()


@override_settings(**FAKE)
def test_manager_can_see_a_report_goals_via_chat(org):
    _seed_goals(org)
    resp = _client_for(org.manager).post(
        CHAT, {"query": f"show me {org.report.email} goals"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert "Report goal" in resp.json()["data"]  # in the manager's scope


@override_settings(**FAKE)
def test_write_intent_is_blocked(org):
    resp = _client_for(org.manager).post(CHAT, {"query": "approve review 123"}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["intent"] == "write"


@override_settings(**FAKE)
def test_cross_tenant_target_returns_nothing(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="out@other.test")
    resp = _client_for(org.manager).post(
        CHAT, {"query": f"show me {outsider.email} goals"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"] == []  # cross-tenant target never resolves


@override_settings(**FAKE)
def test_chat_budget_trips_at_429(org):
    with tenant_context(org.tenant):
        AgentBudget.objects.create(tenant_id=org.tenant.id, agent_code="chat", window="DAILY", limit=1)
    client = _client_for(org.report)
    assert client.post(CHAT, {"query": "my goals"}, format="json").status_code == 200
    assert client.post(CHAT, {"query": "my goals"}, format="json").status_code == 429


@override_settings(**FAKE)
def test_tenant_without_chat_entitlement_is_403(org, other_tenant):
    # A tenant with an empty pack set does not hold the chat feature → 403.
    user = UserFactory(tenant=other_tenant, role="EMPLOYEE", email="nochat@other.test")
    with tenant_context(other_tenant):
        Entitlement.objects.create(tenant_id=other_tenant.id, seat_count=1, feature_packs=[])
    assert _client_for(user).post(CHAT, {"query": "my goals"}, format="json").status_code == 403


def test_unconfigured_llm_is_503(org):
    # No LLM_PROVIDER (default NotConfigured) → the chat surfaces a loud 503.
    resp = _client_for(org.report).post(CHAT, {"query": "my goals"}, format="json")
    assert resp.status_code == 503


def test_unauthenticated_is_401(org):
    assert APIClient().post(CHAT, {"query": "my goals"}, format="json").status_code == 401
