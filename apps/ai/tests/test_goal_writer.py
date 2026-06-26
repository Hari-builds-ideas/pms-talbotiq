"""
RW_BUILD_5 — AI Goal-writer. Drafts a SMART goal through the LLMGateway (so it's
budget-bounded + metered + degrades to 503 with no provider), and is HITL: it
persists NOTHING — the human edits the draft and creates the goal the normal way.
Tests use the FakeLLMProvider (no network); the endpoint is gated to goal-creators.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.agents.goal_writer import draft_goal  # import registers the fake output
from apps.goals.models import Goal
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"


@override_settings(LLM_PROVIDER=FAKE)
def test_draft_returns_structured_draft_and_persists_nothing(org):
    with tenant_context(org.tenant):
        before = Goal.objects.count()
        out = draft_goal(org.manager, "improve our sales response time")
        after = Goal.objects.count()
    assert out["status"] == "ok"
    draft = out["draft"]
    assert draft["title"] and draft["objective"]
    assert isinstance(draft["kpis"], list)
    assert after == before  # a DRAFT — nothing was created


def test_no_provider_degrades_gracefully(org):
    # Default LLM_PROVIDER = NotConfigured (tests pin it off) → clean 503-class result.
    with tenant_context(org.tenant):
        out = draft_goal(org.manager, "improve sales")
    assert out["status"] == "not_configured"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(LLM_PROVIDER=FAKE)
def test_endpoint_drafts_for_a_goal_creator_only(org):
    # A manager (MANAGE_REPORTS_GOALS) gets a draft…
    resp = _client(org.manager).post("/api/goals/ai-draft", {"prompt": "improve sales"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["draft"]["title"]
    # …an employee can't draft goals (no MANAGE_REPORTS_GOALS) → 403.
    emp = _client(org.report).post("/api/goals/ai-draft", {"prompt": "improve sales"}, format="json")
    assert emp.status_code == 403
    # Empty prompt → 400.
    bad = _client(org.manager).post("/api/goals/ai-draft", {"prompt": "  "}, format="json")
    assert bad.status_code == 400
