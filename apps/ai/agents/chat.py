"""
Chat Assistant (Fast, READ-ONLY) — the safety-critical agent. A natural-language
query is classified (read vs write) by the LLM through the gateway, then routed
DETERMINISTICALLY against the EXISTING scoped data using the CALLER's identity +
RBAC. It can NEVER surface data the caller could not already see (every data fetch
goes through ``actor_can_access`` / the tenant-scoped managers — identical to a
direct scoped API call), and any write/approval intent is BLOCKED (Phase 2).

The LLM classifies intent on the (PII-scrubbed) query; the target person is resolved
from the RAW query but the lookup is ALWAYS scope-checked against the caller, so the
classification step can never widen access.
"""
from __future__ import annotations

import re

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.rbac.scope import actor_can_access

AGENT_CODE = "chat"
SCHEMA = {"intent": str}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_WRITE_WORDS = ("approve", "reject", "delete", "change", "update", "finalize", "publish", "set ")


def _scoped_goal_titles(caller, target):
    """Goal titles for ``target`` — ONLY if the caller may see them (else empty).
    Reads through the tenant-scoped manager; never crosses scope or tenant."""
    from apps.goals.models import Goal

    if not actor_can_access(caller, target):
        return None
    return list(Goal.objects.filter(employee_id=target.id).values_list("title", flat=True))


def chat_answer(caller, query: str) -> dict:
    """Answer ``query`` for ``caller`` (read-only, RBAC-bound). Returns a dict with
    a ``status`` the view maps to HTTP: ok | not_configured | budget | blocked."""
    result = gateway.run(
        tenant=caller.tenant_id, agent_code=AGENT_CODE, prompt=query, model="chat", schema=SCHEMA
    )
    if result.status == "NOT_CONFIGURED":
        return {"status": "not_configured"}
    if result.status == "BUDGET_EXCEEDED":
        return {"status": "budget", "errors": result.errors}
    if not result.ok:
        return {"status": "error", "detail": result.status}

    intent = result.content.get("intent", "unknown")
    if intent == "write":
        return {
            "status": "blocked",
            "intent": "write",
            "answer": "I'm a read-only assistant — I can't make changes or approvals.",
        }

    # READ intent. Resolve a target person from the RAW query (if any); the fetch is
    # ALWAYS scope-checked, so this can never surface out-of-scope data.
    from apps.identity.models import User

    match = _EMAIL_RE.search(query or "")
    target = caller
    if match:
        found = User.objects.filter(email=match.group(0)).first()  # tenant-scoped
        target = found  # may be None (cross-tenant / unknown) → empty answer

    if target is None:
        return {"status": "ok", "intent": intent, "answer": "No matching person in your scope.", "data": []}

    titles = _scoped_goal_titles(caller, target)
    if titles is None:
        # Out of the caller's scope — return nothing, exactly like a scoped API call.
        return {"status": "ok", "intent": intent, "answer": "No data in your scope.", "data": []}
    return {
        "status": "ok",
        "intent": intent,
        "answer": f"{target.email} has {len(titles)} goal(s).",
        "data": titles,
    }


def _fake(prompt, model):
    """Classify read vs write from the (scrubbed) query keywords — deterministic."""
    lowered = (prompt or "").lower()
    if any(w in lowered for w in _WRITE_WORDS):
        return {"intent": "write"}
    return {"intent": "read"}


register_fake_output(AGENT_CODE, _fake)
