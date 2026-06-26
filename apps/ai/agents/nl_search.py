"""
Natural-language search (RW_BUILD_5 quick win) — READ-ONLY + scope-bound. The LLM
ONLY classifies the user's question into one of a fixed set of SUPPORTED searches;
the search itself is DETERMINISTIC and runs through the caller's reporting scope, so
it can only ever return people/rows the caller is already allowed to see. The model
never composes a query or touches data. Tests use the ``FakeLLMProvider`` — no network.
"""
from __future__ import annotations

import datetime

from django.utils import timezone

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.ai.schemas import NonEmpty
from apps.rbac.scope import reporting_subtree_ids

AGENT_CODE = "nl_search"
SCHEMA = {"search": NonEmpty(2)}


def _display(user) -> str:
    return (getattr(user, "display_name", "") or "").strip() or "a teammate"


def _monday(now=None) -> datetime.date:
    now = now or timezone.now()
    d = now.date()
    return d - datetime.timedelta(days=d.weekday())


def _run_employees_missing_goals(user) -> list[dict]:
    from apps.goals.models import Goal
    from apps.identity.models import User

    subtree = reporting_subtree_ids(user)
    if not subtree:
        return []
    with_goals = set(
        Goal.objects.filter(
            employee_id__in=subtree, status=Goal.Status.ACTIVE
        ).values_list("employee_id", flat=True)
    )
    missing = User.objects.filter(id__in=subtree, is_active=True).exclude(id__in=with_goals)
    return [{"id": str(u.id), "employee": _display(u)} for u in missing]


def _run_reports_without_checkin(user) -> list[dict]:
    from apps.checkins.models import CheckIn
    from apps.identity.models import User

    subtree = reporting_subtree_ids(user)
    if not subtree:
        return []
    week = _monday()
    checked = set(
        CheckIn.objects.filter(author_id__in=subtree, week_of=week).values_list(
            "author_id", flat=True
        )
    )
    missing = User.objects.filter(id__in=subtree, is_active=True).exclude(id__in=checked)
    return [{"id": str(u.id), "employee": _display(u)} for u in missing]


#: key -> {description (for the classifier prompt), run(user) -> scoped results}.
SEARCHES: dict[str, dict] = {
    "employees_missing_goals": {
        "description": "people on the team with NO active goal set",
        "run": _run_employees_missing_goals,
    },
    "reports_without_checkin": {
        "description": "reports who have NOT submitted a check-in this week",
        "run": _run_reports_without_checkin,
    },
}


def nl_search(user, query: str) -> dict:
    """Classify ``query`` into a supported search (LLM, via the gateway), then run it
    DETERMINISTICALLY within the caller's scope. Returns a status dict the view maps
    to HTTP. ``search`` is "unknown" when the query matches nothing supported."""
    options = " | ".join(f"{k} ({v['description']})" for k, v in SEARCHES.items())
    prompt = (
        f"Classify this question into exactly one supported search, or 'unknown'. "
        f"Options: {options} | unknown. Question: \"{query}\". Respond with ONLY "
        '{"search": "<key>"}. No text outside the JSON.'
    )
    result = gateway.run(
        tenant=user.tenant_id, agent_code=AGENT_CODE, prompt=prompt, model="default", schema=SCHEMA
    )
    if result.status == "NOT_CONFIGURED":
        return {"status": "not_configured"}
    if result.status == "BUDGET_EXCEEDED":
        return {"status": "budget", "errors": result.errors}
    if not result.ok:
        return {"status": "error", "detail": result.status}
    key = (result.content.get("search") or "unknown").strip()
    spec = SEARCHES.get(key)
    if spec is None:
        return {"status": "ok", "search": "unknown", "results": []}
    return {"status": "ok", "search": key, "results": spec["run"](user)}


def _fake(prompt, model):
    return {"search": "employees_missing_goals"}


register_fake_output(AGENT_CODE, _fake)
