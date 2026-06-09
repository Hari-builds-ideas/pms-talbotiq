"""
KPI actuals — the SINGLE write path.

Every actual value for a KPI is written through :func:`record_actual` and ONLY
through it: the manual-entry endpoint and the Jira ingestion seam
(:mod:`apps.goals.jira`) both call this function. Centralising the write keeps
one set of invariants — Decimal coercion, append-only history, and explicit
tenant stamping — so there is exactly one place to reason about correctness.

Measurements append to history: the latest by ``recorded_at`` is the current
actual the scoring engine reads. Prior rows are NEVER mutated.
"""
from decimal import Decimal

from django.utils import timezone

from .models import KpiMeasurement


def record_actual(
    kpi,
    value,
    *,
    source=KpiMeasurement.Source.MANUAL,
    recorded_at=None,
    recorded_by=None,
) -> KpiMeasurement:
    """Record one actual value for ``kpi`` and return the new ``KpiMeasurement``.

    This is the one and only way an actual value is written. ``value`` is coerced
    to ``Decimal`` (no float drift); ``recorded_at`` defaults to ``timezone.now()``
    when None. A new measurement is appended — prior rows are never mutated, so
    the latest by ``recorded_at`` is the current actual.

    The measurement is tenant-scoped to the KPI's tenant: it is created with
    ``tenant_id=kpi.tenant_id`` explicitly, so it works whether called inside a
    request (tenant already bound) or from a worker (no bound context).
    ``TenantScopedModel.save`` then stamps/validates — an explicit matching
    tenant is accepted on both paths.
    """
    if recorded_at is None:
        recorded_at = timezone.now()
    return KpiMeasurement.objects.create(
        tenant_id=kpi.tenant_id,
        kpi=kpi,
        value=Decimal(str(value)),
        recorded_at=recorded_at,
        recorded_by=recorded_by,
        source=source,
    )
