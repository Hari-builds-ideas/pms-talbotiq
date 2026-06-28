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
from apps.ai.schemas import ListOf, NonEmpty

AGENT_CODE = "meeting_summary"
#: A real summary STRING + a NON-EMPTY list of non-blank action-item strings. The
#: list is required non-empty (Finding D) so a hollow / shape-drifted answer (missing
#: key, empty list, or items that aren't strings) fails as SCHEMA_INVALID rather than
#: reaching the human — the prompt always emits >= 1 string item to match.
SCHEMA = {"summary": NonEmpty(12), "action_items": ListOf(NonEmpty(1))}


def summarize_meeting(user, notes: str) -> dict:
    """Summarise ``notes`` into {summary, action_items} for ``user``'s tenant.
    Returns a status dict the view maps to HTTP: ok | not_configured | budget |
    error. Nothing is persisted — it's a draft for the human."""
    # The quality contract (preserve specifics verbatim, no filler, actionable +
    # assigned items) lives in the SYSTEM prompt (agent_config._MEETING_SUMMARY) so
    # it's tunable in one place; the user turn just carries the notes (no duplicate,
    # possibly-conflicting instructions here).
    prompt = f"Summarise these 1-on-1 / meeting notes.\n\nNotes:\n{notes}"
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
    # Models the quality bar (DECISIONS D37): specifics kept verbatim, no filler
    # opener, action item moves work forward. Owner-agnostic — these demo notes name
    # no doer, so the item invents no name (owners are taken from the real notes).
    return {
        "summary": "Shipped the recognition-feed slice; blocked on the design review for the check-in form.",
        "action_items": ["Follow up on the design review for the check-in form with the design team"],
    }


register_fake_output(AGENT_CODE, _fake)
