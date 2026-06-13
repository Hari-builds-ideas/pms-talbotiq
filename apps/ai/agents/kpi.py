"""
Agent 2 — KPI Intelligence (Fast). Subscribes to the Module-2
``cycle_scores_recomputed`` signal (and is also weekly-beat callable) and, per the
nudge rules, surfaces a nudge to the manager dashboard + Slack (Module 12). It is
READ-ONLY: it NEVER changes performance data — the risk is already classified by
the deterministic Module-2 engine; Agent 2 only decides whether/how to nudge.

Nudge rules (deterministic):
  * ON_TRACK                          → no nudge (None)
  * CRITICAL (worsening)              → a CRITICAL nudge
  * AT_RISK and days_remaining ≤ 14   → SUPPRESS the routine nudge + a WARNING
                                        (too late to course-correct; flag for review)
  * AT_RISK with time remaining       → a STANDARD nudge
"""
from __future__ import annotations

import logging

from apps.ai.providers import register_fake_output  # noqa: F401 (kept for symmetry)

logger = logging.getLogger("pms.ai.agent2")

AGENT_CODE = "agent2"
NUDGE_AT_RISK_SUPPRESS_DAYS = 14


def classify_nudge(risk_status: str, days_remaining: int | None) -> dict | None:
    """Apply the deterministic nudge rules. Returns ``None`` (no nudge) or a dict
    ``{"level", "message"}``."""
    if risk_status == "CRITICAL":
        return {"level": "CRITICAL", "message": "Performance is critical — immediate attention needed."}
    if risk_status == "AT_RISK":
        if days_remaining is not None and days_remaining <= NUDGE_AT_RISK_SUPPRESS_DAYS:
            return {
                "level": "SUPPRESSED",
                "message": (
                    f"At risk with {days_remaining} day(s) left — routine nudge "
                    "suppressed; flag for manager review."
                ),
            }
        return {"level": "STANDARD", "message": "At risk — a check-in is recommended."}
    return None  # ON_TRACK (or unknown) → no nudge


def _days_remaining_for_cycle(cycle_id):
    from django.utils import timezone

    from apps.cycles.models import PerformanceCycle

    cycle = PerformanceCycle.objects.filter(id=cycle_id).first()
    if cycle is None or cycle.end_date is None:
        return None
    return (cycle.end_date - timezone.now().date()).days


def run_kpi_nudges(tenant_id, cycle_id, scores) -> dict:
    """Classify + DELIVER nudges for ``scores`` (a list of the signal's per-employee
    dicts). Delivery is best-effort Slack (no-op if unconfigured). Returns a count
    summary. NEVER mutates performance data."""
    from apps.integrations.notifications import notify_kpi_nudge
    from apps.tenancy.context import tenant_context

    delivered = 0
    with tenant_context(tenant_id):
        days_remaining = _days_remaining_for_cycle(cycle_id)
        for s in scores or []:
            nudge = classify_nudge(s.get("risk_status"), days_remaining)
            if nudge is None:
                continue
            notify_kpi_nudge(tenant_id, message=f"[{nudge['level']}] {nudge['message']}")
            delivered += 1
    return {"considered": len(scores or []), "delivered": delivered}


def on_cycle_scores_recomputed(sender, **kwargs):
    """Signal receiver — best-effort (a nudge failure never affects scoring)."""
    try:
        run_kpi_nudges(kwargs.get("tenant_id"), kwargs.get("cycle_id"), kwargs.get("scores"))
    except Exception:  # noqa: BLE001 — never let a nudge break the recompute
        logger.warning("Agent-2 KPI nudge failed (best-effort).", exc_info=True)


def _nudges_for_employee_ids(employee_ids) -> list[dict]:
    """Classify the current nudge for each employee id from their LATEST CycleScore
    (reusing ``classify_nudge`` — no recompute). Caller is inside ``tenant_context``."""
    from apps.goals.models import CycleScore

    out = []
    for eid in employee_ids:
        score = CycleScore.objects.filter(employee_id=eid).order_by("-computed_at").first()
        if score is None:
            continue
        nudge = classify_nudge(score.risk_status, _days_remaining_for_cycle(score.cycle_id))
        if nudge is not None:
            out.append({"employee": str(eid), **nudge})
    return out


def manager_nudges(manager) -> list[dict]:
    """The manager dashboard read: current nudges for the manager's reports' latest
    scores (deterministic, scope-bounded). READ-ONLY."""
    from apps.rbac.scope import reporting_subtree_ids
    from apps.tenancy.context import tenant_context

    with tenant_context(manager.tenant_id):
        return _nudges_for_employee_ids(reporting_subtree_ids(manager))


def team_nudges(actor) -> list[dict]:
    """The scope-aware dashboard read used by the HTTP surface: a Manager (TEAM) sees
    their reporting subtree; HRBP/Admin (TENANT) see the whole active tenant. Reuses
    the SAME nudge classification (``classify_nudge`` over the latest CycleScore) — it
    never recomputes scoring. READ-ONLY."""
    from apps.identity.models import User
    from apps.rbac.scope import Scope, reporting_subtree_ids, scope_for_role
    from apps.tenancy.context import tenant_context

    with tenant_context(actor.tenant_id):
        if scope_for_role(actor.role) is Scope.TENANT:
            ids = set(User.objects.filter(is_active=True).values_list("id", flat=True))
        else:
            ids = reporting_subtree_ids(actor)
        return _nudges_for_employee_ids(ids)
