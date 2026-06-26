"""
AI 1-on-1 / meeting summary (RW_BUILD_5 quick win) — STATELESS: free-text notes in,
a concise summary + concrete action items out. It DRAFTS, it never decides and it
persists NOTHING (the caller keeps/uses the draft). Through the one ``LLMGateway``
(budget → PII-scrub → schema-validate → meter → confidence), so it's metered,
budget-bounded, and degrades to a clean 503 with no provider. Tests use the
``FakeLLMProvider`` (registered below) — no network.
"""
from __future__ import annotations

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.ai.schemas import NonEmpty

AGENT_CODE = "meeting_summary"
#: A real summary + a (possibly empty) list of action items.
SCHEMA = {"summary": NonEmpty(12), "action_items": list}


def summarize_meeting(user, notes: str) -> dict:
    """Summarise ``notes`` into {summary, action_items} for ``user``'s tenant.
    Returns a status dict the view maps to HTTP: ok | not_configured | budget |
    error. Nothing is persisted — it's a draft for the human."""
    prompt = (
        "Summarise these 1-on-1 / meeting notes. Respond with ONLY a JSON object: "
        '{"summary": str, "action_items": [str]}. The summary is 2-4 sentences of '
        "the key points and decisions; action_items are concrete, owner-implied next "
        "steps (0-6 items). Invent nothing not in the notes. No text outside the JSON.\n"
        f"Notes:\n{notes}"
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
    return {"status": "ok", "summary": result.content, "confidence": result.confidence}


def _fake(prompt, model):
    return {
        "summary": "Discussed Q3 priorities and the launch blocker; agreed to escalate the design review.",
        "action_items": ["Escalate the design review by Friday", "Share the updated KPI targets with the team"],
    }


register_fake_output(AGENT_CODE, _fake)
