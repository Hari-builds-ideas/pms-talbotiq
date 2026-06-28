"""
Stale-goal nudge (RW_BUILD_5 quick win) — READ-ONLY + scope-bound. Deterministically
finds a manager's ACTIVE goals with no KPI measurement in the last N days, and (if any)
drafts ONE short follow-up suggestion via the LLMGateway. Advisory/HITL: it suggests,
it never writes or nudges anyone automatically. The deterministic list always returns;
the AI suggestion is a bonus that degrades to None with no provider. Tests use the
``FakeLLMProvider`` (registered below) — no network; the LLM is called at most once,
and only when there ARE stale goals.
"""
from __future__ import annotations

import datetime

from django.utils import timezone

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.ai.schemas import NonEmpty
from apps.rbac.scope import reporting_subtree_ids

AGENT_CODE = "stale_goal_nudge"
SCHEMA = {"suggestion": NonEmpty(8)}
DEFAULT_STALE_DAYS = 30


def _display(user) -> str:
    return (getattr(user, "display_name", "") or "").strip() or "a teammate"


def stale_goals_for(user, days: int = DEFAULT_STALE_DAYS) -> list[dict]:
    """ACTIVE goals in ``user``'s reporting subtree whose latest KPI measurement is
    older than ``days`` (or which have no measurement). Read-only, tenant-scoped."""
    from apps.goals.models import Goal

    subtree = reporting_subtree_ids(user)
    if not subtree:
        return []
    now = timezone.now()
    cutoff = now - datetime.timedelta(days=days)
    out = []
    goals = (
        Goal.objects.filter(employee_id__in=subtree, status=Goal.Status.ACTIVE)
        .select_related("employee")
        .prefetch_related("kpis__measurements")
    )
    for g in goals:
        latest = None
        for kpi in g.kpis.all():
            m = kpi.measurements.first()  # ordered -recorded_at
            if m and (latest is None or m.recorded_at > latest):
                latest = m.recorded_at
        if latest is None or latest < cutoff:
            out.append(
                {
                    "goal": g.title,
                    "employee": _display(g.employee),
                    "days_stale": (now - latest).days if latest else None,
                }
            )
    return out


def suggest_followup(user, stale: list[dict]) -> str | None:
    """Draft ONE short follow-up suggestion for the stale set (1 gateway call).
    Returns None if there's nothing stale or the AI is unavailable (the caller still
    has the deterministic list)."""
    if not stale:
        return None
    # The quality contract (name the specific goals/people, concrete action, no filler
    # — D37) lives in the SYSTEM prompt (agent_config 'stale_goal_nudge'); the user
    # turn just carries the stale goal list.
    titles = ", ".join(f"{s['goal']} ({s['employee']})" for s in stale[:10])
    prompt = f"These ACTIVE goals have had no progress recorded in ~30 days: {titles}."
    result = gateway.run(
        tenant=user.tenant_id, agent_code=AGENT_CODE, prompt=prompt, model="default", schema=SCHEMA
    )
    if not result.ok:
        return None
    return result.content.get("suggestion")


def _fake(prompt, model):
    return {
        "suggestion": "Schedule a short check-in on these goals — ask what's blocking progress and agree one concrete next step for each."
    }


register_fake_output(AGENT_CODE, _fake)
