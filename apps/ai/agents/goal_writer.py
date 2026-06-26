"""
AI Goal-writer (RW_BUILD_5 quick win) — turns a one-line intent ("improve sales
response time") into an editable SMART goal DRAFT (title + objective + 1–3 measurable
KPIs). It DRAFTS, it never decides: the result is returned to the New-Goal form for
the human to edit and create through the existing (RBAC-gated, audited) goal-create
endpoint — nothing is persisted here.

Like every agent it goes through the one ``LLMGateway`` (budget reserve → PII-scrub →
provider call → schema-validate → meter → confidence), so it's metered, budget-bounded,
and degrades to a clean 503 when no provider is configured. Tests use the
``FakeLLMProvider`` (registered below) — no network.
"""
from __future__ import annotations

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.ai.schemas import NonEmpty

AGENT_CODE = "goal_draft"
#: A real title + objective, and a (possibly empty) KPI list. The form lets the
#: human fix anything; we only reject a blank title/objective (no hollow draft).
SCHEMA = {"title": NonEmpty(4), "objective": NonEmpty(8), "kpis": list}


def draft_goal(user, intent: str) -> dict:
    """Draft a SMART goal from ``intent`` for ``user``'s tenant. Returns a status
    dict the view maps to HTTP: ok | not_configured | budget | error. The draft is
    NOT saved — it's a proposal for the human to edit + create."""
    prompt = (
        f'Turn this manager\'s intent into ONE specific, measurable goal: "{intent}".\n'
        "Respond with ONLY a JSON object: {\"title\": str, \"objective\": str, "
        "\"kpis\": [{\"name\": str, \"target_value\": str, \"unit\": str, "
        "\"direction\": \"INCREASING\"|\"DECREASING\"}]}. Title is a short phrase; "
        "objective is one concrete sentence; 1-3 KPIs, each measurable with a numeric "
        "target. No prose outside the JSON."
    )
    result = gateway.run(
        tenant=user.tenant_id, agent_code=AGENT_CODE, prompt=prompt, model="goals", schema=SCHEMA
    )
    if result.status == "NOT_CONFIGURED":
        return {"status": "not_configured"}
    if result.status == "BUDGET_EXCEEDED":
        return {"status": "budget", "errors": result.errors}
    if not result.ok:
        return {"status": "error", "detail": result.status}
    return {"status": "ok", "draft": result.content, "confidence": result.confidence}


def _fake(prompt, model):
    return {
        "title": "Grow qualified sales pipeline",
        "objective": "Increase the qualified sales pipeline through targeted outbound and faster follow-up.",
        "kpis": [
            {"name": "Qualified opportunities created", "target_value": "30", "unit": "count", "direction": "INCREASING"},
            {"name": "Avg. lead response time", "target_value": "4", "unit": "hours", "direction": "DECREASING"},
        ],
    }


register_fake_output(AGENT_CODE, _fake)
