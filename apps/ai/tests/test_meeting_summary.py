"""
RW_BUILD_5 — AI 1-on-1 / meeting summary. Stateless DRAFT through the LLMGateway:
notes in → {summary, action_items} out, persists nothing, degrades to 503 with no
provider. FakeLLMProvider — no network.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.agents.meeting_summary import summarize_meeting  # registers the fake
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"
NOTES = "Talked about the launch blocker and Q3 goals; Ada to escalate the design review."


@override_settings(LLM_PROVIDER=FAKE)
def test_summarize_returns_summary_and_action_items(org):
    with tenant_context(org.tenant):
        out = summarize_meeting(org.manager, NOTES)
    assert out["status"] == "ok"
    assert out["summary"]["summary"]
    assert isinstance(out["summary"]["action_items"], list)


def test_no_provider_degrades(org):
    with tenant_context(org.tenant):
        assert summarize_meeting(org.manager, NOTES)["status"] == "not_configured"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(LLM_PROVIDER=FAKE)
def test_endpoint_summarises_and_validates(org):
    # Any authenticated user may summarise their own notes (USE_CHAT).
    resp = _client(org.report).post("/api/ai/meeting-summary", {"notes": NOTES}, format="json")
    assert resp.status_code == 200
    assert resp.json()["summary"]["summary"]
    # Empty notes → 400.
    bad = _client(org.report).post("/api/ai/meeting-summary", {"notes": "  "}, format="json")
    assert bad.status_code == 400
