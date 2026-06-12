"""
Analytics services — deterministic, cache-backed aggregation over already-built
data. NO new persisted model: performance comes from the Module-2 ``CycleScore``,
the calibration grid reuses the Module-8 9-box ``NineBoxPlacement``, and a
"department" is a manager + their reporting subtree (the Module-1/7 ``User.manager``
tree). Reads only — nothing here mutates, so there is no audit write.

THE HEADLINE SAFETY PROPERTY — MIN-COHORT SUPPRESSION (``constants.MIN_COHORT`` = 5):
a department/cohort view with fewer than 5 members returns aggregate-only with
individual values SUPPRESSED, so a small team can never be de-anonymised by its
manager. (Distinct from the Module-4 360 per-group min-volume of 3 — see
``constants``.)

SCOPE: an Employee sees only their OWN individual analytics (and is barred from
department analytics by the capability); a Manager covers their reporting line;
HRBP/Admin the tenant. An out-of-scope / cross-tenant subject raises ``NotFound``
(404), consistent with the rest of the system.
"""
from __future__ import annotations

import json
from statistics import mean, median

from rest_framework.exceptions import NotFound

from apps.core.cache import invalidate_tenant_cache, tenant_cache_key
from apps.goals.models import CycleScore
from apps.identity.models import User
from apps.rbac.scope import actor_can_access, reporting_subtree_ids
from apps.succession.models import NineBoxPlacement
from apps.tenancy.context import tenant_context

from . import constants as C

#: TTL (seconds) for a cached department aggregate.
_DEPT_CACHE_TTL = 300
_ANALYTICS_CACHE_PART = "analytics"


def _tenant_id(x) -> str:
    return str(getattr(x, "id", x))


# ── cache invalidation (wired to the Module-2 recompute signal) ───────────────


def invalidate_analytics_cache(tenant) -> None:
    """Clear the tenant's analytics cache namespace (called after a recompute)."""
    invalidate_tenant_cache(_tenant_id(tenant), _ANALYTICS_CACHE_PART)


def _on_cycle_scores_recomputed(sender, **kwargs):
    """Signal receiver: a Module-2 recompute changes the numbers analytics roll up,
    so drop the tenant's cached aggregates. The signal carries ``tenant_id`` (str)."""
    tenant_id = kwargs.get("tenant_id")
    if tenant_id:
        invalidate_analytics_cache(tenant_id)


# ── scope ──────────────────────────────────────────────────────────────────────


def _require_in_scope(actor, subject):
    """404 unless ``subject`` (a user) is within ``actor``'s data scope."""
    if subject is None or not actor_can_access(actor, subject):
        raise NotFound("No such analytics subject in your scope.")


# ── individual analytics (own performance trend) ──────────────────────────────


def individual_trend(actor, employee) -> dict:
    """An employee's performance trend across cycles — their OWN performance data
    (no cohort aggregation, so no min-cohort suppression). Scoped: an Employee may
    see only themselves; a Manager their reports; HRBP/Admin the tenant."""
    _require_in_scope(actor, employee)
    with tenant_context(actor.tenant_id):
        scores = list(
            CycleScore.objects.filter(employee_id=employee.id).order_by("computed_at")
        )
    return {
        "employee": str(employee.id),
        "trend": [
            {
                "cycle": str(s.cycle_id),
                "raw_score": str(s.raw_score),
                "t_score": str(s.t_score),
                "risk_status": s.risk_status,
                "pace_behind": s.pace_behind,
                "computed_at": s.computed_at.isoformat(),
            }
            for s in scores
        ],
    }


# ── department analytics (cohort rollup with min-cohort suppression) ──────────


def department_analytics(actor, head, cycle) -> dict:
    """A department rollup: aggregate performance over ``head``'s reporting subtree
    for ``cycle``. ``head`` must be within ``actor``'s scope (404 otherwise).

    MIN-COHORT SUPPRESSION: when the (active) cohort is smaller than
    ``MIN_COHORT`` (5), the per-individual breakdown is SUPPRESSED — only the
    aggregate is returned, so the team cannot be de-anonymised. Cached per
    (tenant, head, cycle); the cache is dropped on a Module-2 recompute."""
    _require_in_scope(actor, head)
    tid = actor.tenant_id
    key = tenant_cache_key(tid, _ANALYTICS_CACHE_PART, "dept", str(head.id), str(cycle.id))
    from django.core.cache import cache

    cached = cache.get(key)
    if cached is not None:
        return cached

    with tenant_context(tid):
        member_ids = reporting_subtree_ids(head)  # transitive reports (head excluded)
        active_member_ids = set(
            User.objects.filter(id__in=member_ids, is_active=True).values_list("id", flat=True)
        )
        cohort_size = len(active_member_ids)
        scores = list(
            CycleScore.objects.filter(cycle_id=cycle.id, employee_id__in=active_member_ids)
        )

    t_scores = [float(s.t_score) for s in scores]
    risk = {"ON_TRACK": 0, "AT_RISK": 0, "CRITICAL": 0}
    for s in scores:
        risk[s.risk_status] = risk.get(s.risk_status, 0) + 1

    suppressed = cohort_size < C.MIN_COHORT
    result = {
        "head": str(head.id),
        "cycle": str(cycle.id),
        "cohort_size": cohort_size,
        "min_cohort": C.MIN_COHORT,
        "suppressed": suppressed,
        "aggregate": {
            "headcount": cohort_size,
            "scored": len(scores),
            "mean_t_score": round(mean(t_scores), 2) if t_scores else None,
            "median_t_score": round(median(t_scores), 2) if t_scores else None,
            "risk_distribution": risk,
        },
    }
    if suppressed:
        # No individual values for a sub-threshold cohort — aggregate only.
        result["individuals"] = []
        result["note"] = (
            f"Cohort too small (<{C.MIN_COHORT}); individual values suppressed."
        )
    else:
        result["individuals"] = [
            {
                "employee": str(s.employee_id),
                "t_score": str(s.t_score),
                "risk_status": s.risk_status,
            }
            for s in scores
        ]

    cache.set(key, result, _DEPT_CACHE_TTL)
    return result


# ── calibration grid (reuses the Module-8 9-box) ──────────────────────────────


def calibration_grid(actor, cycle) -> dict:
    """The 9-box calibration grid for ``cycle`` — box counts + the placements.
    HRBP/Admin only (gated at the view); reuses the Module-8 ``NineBoxPlacement``
    (already management-only succession data), tenant-scoped by its manager."""
    with tenant_context(actor.tenant_id):
        placements = list(NineBoxPlacement.objects.filter(cycle_id=cycle.id))
    grid = {str(box): 0 for box in range(1, 10)}
    for p in placements:
        grid[str(p.box)] = grid.get(str(p.box), 0) + 1
    return {
        "cycle": str(cycle.id),
        "total": len(placements),
        "grid": grid,
        "placements": [
            {
                "employee": str(p.employee_id),
                "box": p.box,
                "performance_band": p.performance_band,
                "potential_band": p.potential_band,
            }
            for p in placements
        ],
    }


# ── export (text / JSON only — no binary) ─────────────────────────────────────


def export_department(actor, head, cycle, *, fmt="json") -> tuple[str, str]:
    """Export a department rollup as JSON or plain text (NO binary). Returns
    ``(content, content_type)``. Honours the same scope + min-cohort suppression as
    ``department_analytics`` (it calls it)."""
    data = department_analytics(actor, head, cycle)
    if fmt == "text":
        lines = [
            f"Department rollup — head {data['head']}, cycle {data['cycle']}",
            f"Cohort size: {data['cohort_size']} (min cohort {data['min_cohort']}, "
            f"suppressed={data['suppressed']})",
            f"Mean T: {data['aggregate']['mean_t_score']}  "
            f"Median T: {data['aggregate']['median_t_score']}",
            f"Risk: {data['aggregate']['risk_distribution']}",
        ]
        if not data["suppressed"]:
            lines.append("Individuals:")
            lines += [
                f"  {row['employee']}: T={row['t_score']} [{row['risk_status']}]"
                for row in data["individuals"]
            ]
        else:
            lines.append(data["note"])
        return "\n".join(lines), "text/plain"
    return json.dumps(data, indent=2), "application/json"
