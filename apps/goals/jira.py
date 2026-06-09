"""
Jira ingestion SEAM — interface only.

This module defines the contract for pulling a JIRA-sourced KPI's current actual
and the Celery task that drives a sync, but it contains NO real Jira client. The
concrete client (HTTP/JQL, auth, rate limiting) lands in Module 12 and is swapped
in via the ``JIRA_ACTUAL_PROVIDER`` setting — no code change here.

Until then the default provider is :class:`NotConfiguredProvider`, which raises
loudly on use. The sync task therefore logs a clear warning and skips cleanly
rather than crashing or silently doing nothing. All actual values that the task
does write go through the single write path, :func:`apps.goals.services.record_actual`.
"""
import abc
import logging
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.utils.module_loading import import_string

from apps.tenancy.context import tenant_context

from .models import Kpi, KpiMeasurement
from .services import record_actual

logger = logging.getLogger("pms.goals.jira")


class JiraNotConfiguredError(Exception):
    """Raised when an actual is requested but no concrete Jira provider exists."""


class JiraActualProvider(abc.ABC):
    """Interface for fetching the current actual of one JIRA-sourced KPI.

    The CONCRETE client is Module 12. This MVP ships only the abstract contract
    plus :class:`NotConfiguredProvider` as the default.
    """

    # Concrete, working providers set this True so callers can detect a real one.
    configured = True

    @abc.abstractmethod
    def fetch_actual(self, kpi) -> Decimal:
        """Return the current actual for ``kpi`` resolved from its ``external_ref``.

        ``external_ref`` holds the Jira issue key / JQL for the KPI.
        """
        raise NotImplementedError


class NotConfiguredProvider(JiraActualProvider):
    """Default provider for the MVP: there is no Jira client yet, so any fetch
    raises :class:`JiraNotConfiguredError`. The ``configured`` marker lets callers
    detect this without catching the exception."""

    configured = False

    def fetch_actual(self, kpi) -> Decimal:
        raise JiraNotConfiguredError(
            "No Jira provider configured; the concrete client lands in Module 12."
        )


def get_provider() -> JiraActualProvider:
    """Return the configured :class:`JiraActualProvider`.

    Resolves the ``JIRA_ACTUAL_PROVIDER`` setting (an import string) when present,
    so Module 12 can swap in its concrete client via config alone. For the MVP no
    setting is configured, so this returns a :class:`NotConfiguredProvider`.
    """
    dotted = getattr(settings, "JIRA_ACTUAL_PROVIDER", None)
    if dotted:
        return import_string(dotted)()
    return NotConfiguredProvider()


@shared_task
def sync_jira_actuals(tenant_id, cycle_id):
    """Sync actuals for every JIRA-sourced KPI in ``cycle_id`` (within ``tenant_id``).

    Reads are tenant-scoped, so the whole task runs inside ``tenant_context``.
    With no provider configured (or one that raises ``JiraNotConfiguredError``),
    this logs a clear warning and skips cleanly, returning a no-provider summary —
    it never crashes. When a real provider is configured, each KPI's actual is
    written through the single write path; a per-KPI fetch error is logged and
    skipped, not fatal.
    """
    with tenant_context(tenant_id):
        kpis = list(
            Kpi.objects.filter(source=Kpi.Source.JIRA, goal__cycle_id=cycle_id)
        )

        provider = get_provider()
        if not getattr(provider, "configured", False):
            logger.warning(
                "Jira sync skipped for tenant=%s cycle=%s: no provider configured "
                "(concrete client lands in Module 12); %d JIRA KPI(s) skipped.",
                tenant_id,
                cycle_id,
                len(kpis),
            )
            return {"synced": 0, "skipped": len(kpis), "reason": "no_provider"}

        synced = 0
        skipped = 0
        for kpi in kpis:
            try:
                value = provider.fetch_actual(kpi)
            except JiraNotConfiguredError:
                # A configured-looking provider that still can't serve this KPI.
                logger.warning(
                    "Jira sync skipped for tenant=%s cycle=%s: provider reported "
                    "not configured.",
                    tenant_id,
                    cycle_id,
                )
                return {"synced": synced, "skipped": len(kpis) - synced, "reason": "no_provider"}
            except Exception:  # noqa: BLE001 - one bad KPI must not fail the batch
                logger.warning(
                    "Jira fetch failed for kpi=%s (ref=%s); skipping.",
                    kpi.id,
                    kpi.external_ref,
                    exc_info=True,
                )
                skipped += 1
                continue
            record_actual(kpi, value, source=KpiMeasurement.Source.JIRA)
            synced += 1
        return {"synced": synced, "skipped": skipped}
