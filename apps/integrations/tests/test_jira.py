"""
Jira integration — the concrete provider fills the Module-2 seam: a JIRA-sourced
KPI's actual is fetched via an INJECTED fake client and written through the EXISTING
``record_actual`` path. An unconfigured tenant preserves the Module-2 log-and-skip.
NO real network call runs (the fake client is injected via settings).
"""
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.goals.jira import sync_jira_actuals
from apps.goals.models import KpiMeasurement
from apps.integrations.models import TenantIntegration
from apps.integrations.tests.fakes import set_jira_canned
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, GoalFactory, KpiFactory, UserFactory

pytestmark = pytest.mark.django_db

_CONFIGURED = dict(
    JIRA_ACTUAL_PROVIDER="apps.integrations.jira_provider.JiraActualProvider",
    JIRA_HTTP_CLIENT_FACTORY="apps.integrations.tests.fakes.build_fake_jira_client",
)


def _jira_kpi(tenant, *, external_ref="PROJ-1"):
    emp = UserFactory(tenant=tenant, role="EMPLOYEE")
    cycle = CycleFactory(tenant=tenant, status="ACTIVE")
    with tenant_context(tenant):
        goal = GoalFactory(employee=emp, cycle=cycle)
        kpi = KpiFactory(goal=goal, source="JIRA", external_ref=external_ref,
                         target_value=Decimal("100.0000"))
    return cycle, kpi


def _enable_jira(tenant):
    with tenant_context(tenant):
        return TenantIntegration.objects.create(
            tenant_id=tenant.id, kind="JIRA", enabled=True,
            config={"base_url": "https://jira.example", "email": "x@y.z"},
        )


@override_settings(**_CONFIGURED)
def test_sync_writes_actuals_via_record_actual(tenant):
    cycle, kpi = _jira_kpi(tenant, external_ref="PROJ-42")
    _enable_jira(tenant)
    set_jira_canned({"PROJ-42": 87})

    result = sync_jira_actuals(str(tenant.id), str(cycle.id))
    assert result == {"synced": 1, "skipped": 0}
    with tenant_context(tenant):
        latest = (
            KpiMeasurement.objects.filter(kpi=kpi).order_by("-recorded_at", "-created_at").first()
        )
    assert latest.value == Decimal("87.0000")
    assert latest.source == KpiMeasurement.Source.JIRA


@override_settings(**_CONFIGURED)
def test_unconfigured_tenant_log_and_skips(tenant):
    # The provider is set, but this tenant has NO enabled Jira integration →
    # fetch_actual raises JiraNotConfiguredError → the Module-2 no_provider skip.
    cycle, _ = _jira_kpi(tenant)
    result = sync_jira_actuals(str(tenant.id), str(cycle.id))
    assert result["reason"] == "no_provider"
    assert result["synced"] == 0


def test_default_provider_unset_is_module2_no_provider(tenant):
    # With NO JIRA_ACTUAL_PROVIDER configured (base default), the Module-2
    # NotConfigured behaviour is preserved verbatim.
    cycle, _ = _jira_kpi(tenant)
    result = sync_jira_actuals(str(tenant.id), str(cycle.id))
    assert result["reason"] == "no_provider"


@override_settings(**_CONFIGURED)
def test_jira_config_is_tenant_isolated(tenant, other_tenant):
    cycle_a, kpi_a = _jira_kpi(tenant, external_ref="A-1")
    _enable_jira(tenant)
    # other_tenant has its own JIRA KPI but NO enabled integration → skipped.
    cycle_b, _ = _jira_kpi(other_tenant, external_ref="B-1")
    set_jira_canned({"A-1": 10, "B-1": 20})

    assert sync_jira_actuals(str(tenant.id), str(cycle_a.id)) == {"synced": 1, "skipped": 0}
    # other_tenant: no enabled integration → no_provider (isolation: A's config
    # never bleeds into B).
    assert sync_jira_actuals(str(other_tenant.id), str(cycle_b.id))["reason"] == "no_provider"
