"""
AI review bias / quality flag (RW_BUILD_5 quick win) — ASSISTIVE, never blocking.
Given a draft review's text, it returns advisory flags (recency bias, harsh or
unprofessional wording, missing evidence/specifics, vague language). It DRAFTS
suggestions, it never decides and never blocks the review; it persists NOTHING.
Stateless (the caller passes the text they're editing) and through the one
``LLMGateway``. Tests use the ``FakeLLMProvider`` (registered below) — no network.
"""
from __future__ import annotations

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output

AGENT_CODE = "review_quality"
#: A list of advisory flags; an empty list means "nothing flagged" (clean text).
SCHEMA = {"flags": list}


def flag_review_quality(user, text: str) -> dict:
    """Return advisory quality/bias flags for ``text``. Status dict the view maps to
    HTTP: ok | not_configured | budget | error. Assistive only — nothing is saved or
    blocked."""
    prompt = (
        "Review this DRAFT performance-review text for quality and bias. Respond with "
        'ONLY a JSON object {"flags": [{"type": str, "note": str}]} where type is one '
        "of recency_bias | harsh_wording | missing_evidence | vague | other, and note "
        "is a short, constructive suggestion. Flag only real issues; return an EMPTY "
        "list if the text is balanced, specific and professional. This is ASSISTIVE — "
        "never a verdict. No text outside the JSON.\n"
        f"Draft review text:\n{text}"
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
    return {"status": "ok", "flags": result.content.get("flags", []), "confidence": result.confidence}


def _fake(prompt, model):
    return {
        "flags": [
            {"type": "missing_evidence", "note": "The 'strong delivery' claim isn't tied to a specific goal or metric."},
            {"type": "recency_bias", "note": "Most examples are from the last few weeks; consider the whole cycle."},
        ]
    }


register_fake_output(AGENT_CODE, _fake)
