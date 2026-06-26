"""
RW_BUILD_5 — stale-goal nudge. READ-ONLY + scope-bound: a manager's ACTIVE goals with
no KPI progress in ~30 days, plus one AI-drafted follow-up suggestion (advisory; the
deterministic list always returns even with no AI provider). FakeLLMProvider — no
network. Persists/nudges nothing.
"""
import datetime

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai.agents.stale_goals import stale_goals_for, suggest_followup  # registers the fake
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    KpiMeasurementFactory,
)

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"


def _goal_with_measurement_age(org, employee, *, title, days_ago):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    g = GoalFactory(employee=employee, cycle=cycle, status="ACTIVE", title=title)
    kpi = KpiFactory(goal=g)
    KpiMeasurementFactory(kpi=kpi, recorded_at=timezone.now() - datetime.timedelta(days=days_ago))
    return g


def test_stale_detection_is_scope_bound(org):
    with tenant_context(org.tenant):
        _goal_with_measurement_age(org, org.report, title="Stale goal", days_ago=40)
        _goal_with_measurement_age(org, org.report, title="Fresh goal", days_ago=2)
        titles = {s["goal"] for s in stale_goals_for(org.manager)}
        assert "Stale goal" in titles  # 40 days → stale
        assert "Fresh goal" not in titles  # 2 days → fresh
        # An employee has no reporting subtree → sees nothing (scope-bound).
        assert stale_goals_for(org.report) == []


@override_settings(LLM_PROVIDER=FAKE)
def test_suggestion_drafted_only_when_stale(org):
    with tenant_context(org.tenant):
        _goal_with_measurement_age(org, org.report, title="Stale goal", days_ago=45)
        stale = stale_goals_for(org.manager)
        assert stale  # there is a stale goal
        assert isinstance(suggest_followup(org.manager, stale), str)
        # Nothing stale → no suggestion (and no LLM call).
        assert suggest_followup(org.manager, []) is None


def test_suggestion_none_without_provider(org):
    with tenant_context(org.tenant):
        _goal_with_measurement_age(org, org.report, title="Stale goal", days_ago=45)
        stale = stale_goals_for(org.manager)
        assert suggest_followup(org.manager, stale) is None  # NotConfigured → graceful None


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(LLM_PROVIDER=FAKE)
def test_endpoint_manager_only(org):
    with tenant_context(org.tenant):
        _goal_with_measurement_age(org, org.report, title="Stale goal", days_ago=40)
    ok = _client(org.manager).get("/api/ai/stale-goals")
    assert ok.status_code == 200
    body = ok.json()
    assert "Stale goal" in {s["goal"] for s in body["stale"]}
    assert isinstance(body["suggestion"], str)  # drafted (stale present)
    # An employee lacks VIEW_TEAM_SCORES → 403.
    assert _client(org.report).get("/api/ai/stale-goals").status_code == 403
