"""AGENT_INTEL — name-typo tolerance.

A misspelled name that no exact token matches gets a scope-limited "did you mean…?"
suggestion — but ONLY for people the caller may already see (never a leak).
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}
CHAT = "/api/ai/chat"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _name(user, name):
    user.display_name = name
    user.save(update_fields=["display_name"])


@override_settings(**FAKE)
def test_typo_suggests_correct_name_in_scope(org):
    with tenant_context(org.tenant):
        _name(org.report, "Anastasia")   # the manager's report
    c = _client(org.manager)
    r = c.post(CHAT, {"query": "how is Anastaesia doing?"}, format="json")
    ans = r.json()["answer"]
    assert "did you mean" in ans.lower()
    assert "Anastasia" in ans


@override_settings(**FAKE)
def test_typo_suggestion_is_scope_limited_no_leak(org):
    """An employee mistyping a PEER's name gets NO suggestion — the peer is outside
    their scope, so the assistant must not even hint the name exists."""
    with tenant_context(org.tenant):
        _name(org.peer, "Bartholomew")   # not visible to the employee
    c = _client(org.report)  # EMPLOYEE — OWN scope
    r = c.post(CHAT, {"query": "how is Bartholmew doing?"}, format="json")
    ans = r.json()["answer"]
    assert "Bartholomew" not in ans
    assert "couldn't find" in ans.lower()
