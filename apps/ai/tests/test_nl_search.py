"""
RW_BUILD_5 — natural-language search. The LLM only CLASSIFIES the question into a
fixed supported search; the search is DETERMINISTIC and scope-bound (returns only
people the caller can see). FakeLLMProvider — no network; read-only.
"""
import datetime

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai import providers
from apps.ai.agents.nl_search import (  # registers the fake
    _monday,
    _run_employees_missing_goals,
    _run_reports_without_checkin,
    nl_search,
)
from apps.checkins.models import CheckIn
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"


def test_employees_missing_goals_is_scope_bound(org):
    with tenant_context(org.tenant):
        # report (under manager) has no active goal → appears as missing.
        ids = {r["id"] for r in _run_employees_missing_goals(org.manager)}
        assert str(org.report.id) in ids
        # Give report an active goal → no longer missing.
        GoalFactory(employee=org.report, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), status="ACTIVE")
        ids2 = {r["id"] for r in _run_employees_missing_goals(org.manager)}
        assert str(org.report.id) not in ids2
        # An employee has no reporting subtree → sees nobody.
        assert _run_employees_missing_goals(org.report) == []


def test_reports_without_checkin(org):
    with tenant_context(org.tenant):
        before = {r["id"] for r in _run_reports_without_checkin(org.manager)}
        assert str(org.report.id) in before  # no check-in this week
        CheckIn.objects.create(tenant_id=org.tenant.id, author=org.report, week_of=_monday(), mood=3)
        after = {r["id"] for r in _run_reports_without_checkin(org.manager)}
        assert str(org.report.id) not in after


@override_settings(LLM_PROVIDER=FAKE)
def test_nl_search_classifies_then_runs(org):
    with tenant_context(org.tenant):
        out = nl_search(org.manager, "who on my team is missing goals?")
    assert out["status"] == "ok"
    assert out["search"] == "employees_missing_goals"  # the fake classifier's key
    assert any(r["id"] == str(org.report.id) for r in out["results"])


@override_settings(LLM_PROVIDER=FAKE)
def test_unrecognised_query_is_unknown_empty(org):
    # Temporarily make the classifier return an unsupported key.
    providers.register_fake_output("nl_search", lambda p, m: {"search": "not_a_real_search"})
    try:
        with tenant_context(org.tenant):
            out = nl_search(org.manager, "what's the weather?")
    finally:
        from apps.ai.agents import nl_search as mod  # restore the real fake
        providers.register_fake_output("nl_search", mod._fake)
    assert out["search"] == "unknown" and out["results"] == []


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(LLM_PROVIDER=FAKE)
def test_endpoint_manager_only(org):
    ok = _client(org.manager).post("/api/ai/search", {"query": "who is missing goals"}, format="json")
    assert ok.status_code == 200 and "results" in ok.json()
    assert _client(org.report).post("/api/ai/search", {"query": "x"}, format="json").status_code == 403
    assert _client(org.manager).post("/api/ai/search", {"query": ""}, format="json").status_code == 400
