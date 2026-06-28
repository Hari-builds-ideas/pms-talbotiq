"""
RW_BUILD_5 — AI review bias/quality flag. ASSISTIVE, stateless, never blocking:
draft text in → advisory {flags:[{type,note}]} out (empty = clean). Through the
LLMGateway; persists nothing. FakeLLMProvider — no network. Gated to reviewers.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.agents.review_quality import flag_review_quality  # registers the fake
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"
TEXT = "Ada had strong delivery this cycle and is great. Recently she nailed the launch."


@override_settings(LLM_PROVIDER=FAKE)
def test_returns_advisory_flags(org):
    with tenant_context(org.tenant):
        out = flag_review_quality(org.manager, TEXT)
    assert out["status"] == "ok"
    assert isinstance(out["flags"], list) and out["flags"]
    assert {"type", "note"} <= set(out["flags"][0])


def test_no_provider_degrades(org):
    with tenant_context(org.tenant):
        assert flag_review_quality(org.manager, TEXT)["status"] == "not_configured"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(LLM_PROVIDER=FAKE)
def test_endpoint_gated_to_reviewers(org):
    # A reviewer (MANAGE_REVIEWS) gets flags…
    ok = _client(org.manager).post("/api/ai/review-quality", {"text": TEXT}, format="json")
    assert ok.status_code == 200 and isinstance(ok.json()["flags"], list)
    # …an employee can't (no MANAGE_REVIEWS) → 403.
    emp = _client(org.report).post("/api/ai/review-quality", {"text": TEXT}, format="json")
    assert emp.status_code == 403
    # Empty text → 400.
    bad = _client(org.manager).post("/api/ai/review-quality", {"text": ""}, format="json")
    assert bad.status_code == 400


def test_system_prompt_encodes_quality_contract():
    # D37: each note QUOTES the offending phrase verbatim + gives a concrete fix, no filler.
    from apps.ai.agent_config import system_prompt_for

    sysp = system_prompt_for("review_quality").lower()
    assert "verbatim" in sysp           # preserve the specific offending phrase
    assert "concretely" in sysp         # actionable fix, not generic advice
    assert "no filler" in sysp
