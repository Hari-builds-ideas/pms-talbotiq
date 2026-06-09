"""
Tests for the Jira ingestion seam, :mod:`apps.goals.jira`.

The seam is a real, loud contract — not a silent stub. These tests prove the
default raises/skips loudly and that a configured provider's actuals flow through
the single write path (:func:`apps.goals.services.record_actual`).
"""
from decimal import Decimal

import pytest

from apps.goals import jira
from apps.goals.jira import (
    JiraActualProvider,
    JiraNotConfiguredError,
    NotConfiguredProvider,
    get_provider,
    sync_jira_actuals,
)
from apps.goals.models import KpiMeasurement
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _make_jira_kpi(tenant, cycle, external_ref="PROJ-1"):
    goal = GoalFactory(employee=UserFactory(tenant=tenant), cycle=cycle)
    return KpiFactory(goal=goal, source="JIRA", external_ref=external_ref)


# ── the default provider is loud, not silent ───────────────────────────────
def test_not_configured_provider_fetch_raises():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    kpi = _make_jira_kpi(t, cyc)
    with pytest.raises(JiraNotConfiguredError):
        NotConfiguredProvider().fetch_actual(kpi)


def test_get_provider_defaults_to_not_configured():
    provider = get_provider()
    assert isinstance(provider, NotConfiguredProvider)
    assert provider.configured is False


# ── no provider: log-and-skip, write nothing, never crash ───────────────────
def test_sync_with_no_provider_skips_and_writes_nothing():
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    _make_jira_kpi(t, cyc, external_ref="PROJ-1")  # something to skip

    with tenant_context(t):
        before = KpiMeasurement.objects.count()

    result = sync_jira_actuals(str(t.id), str(cyc.id))

    # Loud-but-safe: returns the no-provider summary and records nothing. (The
    # warning is logged to "pms.goals.jira"; not asserted via caplog because that
    # logger has propagate=False, which pytest's root capture handler can't see —
    # the summary's reason="no_provider" is the robust contract assertion.)
    assert result == {"synced": 0, "skipped": 1, "reason": "no_provider"}
    with tenant_context(t):
        assert KpiMeasurement.objects.count() == before  # recorded nothing


# ── configured provider: actuals flow through the single write path ─────────
class _FakeProvider(JiraActualProvider):
    """In-test concrete provider returning a fixed Decimal actual."""

    def __init__(self, value):
        self._value = value

    def fetch_actual(self, kpi) -> Decimal:
        return self._value


def test_sync_with_configured_provider_writes_jira_measurement(monkeypatch):
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    kpi = _make_jira_kpi(t, cyc, external_ref="PROJ-42")

    monkeypatch.setattr(jira, "get_provider", lambda: _FakeProvider(Decimal("88.5000")))

    result = sync_jira_actuals(str(t.id), str(cyc.id))

    assert result == {"synced": 1, "skipped": 0}
    with tenant_context(t):
        measurements = list(KpiMeasurement.objects.filter(kpi=kpi))
    assert len(measurements) == 1
    m = measurements[0]
    assert m.source == KpiMeasurement.Source.JIRA
    assert m.value == Decimal("88.5000")
    assert m.recorded_by_id is None  # system-written, no human


def test_sync_ignores_non_jira_kpis(monkeypatch):
    t = TenantFactory()
    cyc = CycleFactory(tenant=t)
    # A MANUAL KPI in the same cycle must NOT be synced.
    manual_goal = GoalFactory(employee=UserFactory(tenant=t), cycle=cyc)
    manual_kpi = KpiFactory(goal=manual_goal, source="MANUAL")

    monkeypatch.setattr(jira, "get_provider", lambda: _FakeProvider(Decimal("1.0000")))

    result = sync_jira_actuals(str(t.id), str(cyc.id))

    assert result == {"synced": 0, "skipped": 0}
    with tenant_context(t):
        assert KpiMeasurement.objects.filter(kpi=manual_kpi).count() == 0
