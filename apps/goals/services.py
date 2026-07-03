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


def add_goal_update(actor, goal, text):
    """Append a progress note to a goal's timeline (AGENT_UX_V3 Part 2.3). Audits
    ``goal.update.added`` BEFORE the write (project audit rule); the caller's scope on
    the goal is enforced at the view. Tenant-stamped from the goal (safe off-request)."""
    from rest_framework.exceptions import ValidationError

    from apps.audit.services import record

    from .models import GoalUpdate

    text = (text or "").strip()
    if not text:
        raise ValidationError({"text": "An update needs some text."})
    record(action="goal.update.added", actor=actor, target_type="goal", target_id=goal.id)
    return GoalUpdate.objects.create(
        tenant_id=goal.tenant_id, goal=goal, author=actor, text=text[:500],
    )
