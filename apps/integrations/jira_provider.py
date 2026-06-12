"""
The concrete Jira actuals provider — fills the Module-2 seam
(``apps.goals.jira.get_provider`` via ``settings.JIRA_ACTUAL_PROVIDER``).

For a KPI with ``source=JIRA`` it fetches the current actual through an injectable
HTTP client (a FAKE in tests; the real client is inert without a token). It writes
NOTHING here — the Module-2 ``sync_jira_actuals`` task calls ``fetch_actual`` and
routes every value through the single ``record_actual`` write path. When a tenant
has NO enabled Jira integration, ``fetch_actual`` raises ``JiraNotConfiguredError``,
so the task falls back to the Module-2 log-and-skip (no_provider) — unchanged.
"""
from __future__ import annotations

from decimal import Decimal

from apps.goals.jira import JiraActualProvider as _BaseJiraActualProvider
from apps.goals.jira import JiraNotConfiguredError

from .clients import get_jira_client
from .models import TenantIntegration


class JiraActualProvider(_BaseJiraActualProvider):
    """Resolves the current tenant's enabled Jira integration and fetches a KPI's
    actual via the (injectable) HTTP client. Runs inside the task's
    ``tenant_context`` (so ``TenantIntegration.objects`` is tenant-scoped)."""

    configured = True

    def fetch_actual(self, kpi) -> Decimal:
        integration = TenantIntegration.objects.filter(
            kind=TenantIntegration.Kind.JIRA, enabled=True
        ).first()
        if integration is None:
            # No enabled Jira integration for this tenant → preserve the Module-2
            # no-provider behaviour (the task catches this and log-and-skips).
            raise JiraNotConfiguredError(
                "No enabled Jira integration for this tenant."
            )
        client = get_jira_client(integration)
        return Decimal(str(client.fetch_issue_value(kpi.external_ref)))
