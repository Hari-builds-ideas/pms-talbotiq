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
#: Keyword cues for the deterministic FakeLLMProvider classifier (tests + the
#: no-real-key path). The real LLM classifies via the _CHAT system prompt.
_CAPABILITY_PHRASES = (
    "what can you do", "what do you do", "who are you", "what are you",
    "how do you work", "what can i ask", "capabilit", "your purpose", "what are your",
)
_PERF_WORDS = (
    "goal", "kpi", "score", "rating", "review", "performance", "risk", "progress",
    "feedback", "cycle", "objective", "assessment", "appraisal", "how am i doing",
)

#: A read-only performance assistant answers capability + general questions in
#: plain language — it must NEVER dump a metrics summary for them (BUG 4).
_CAPABILITY_ANSWER = (
    "I'm your read-only performance assistant. I can summarise your goals, KPIs, "
    "cycle scores, and review status — and, if you manage people, your team's — all "
    "within what you're allowed to see. I can't make changes or approvals. "
    "Try: “what are my goals?” or “how am I doing this cycle?”"
)
_GENERAL_ANSWER = (
    "I'm a read-only performance assistant, so that's outside what I can help with — "
    "but I can tell you about your goals, KPIs, cycle scores, or reviews (within your "
    "access). For example: “how am I doing this cycle?”"
)


def _scoped_goal_titles(caller, target):
    """Goal titles for ``target`` — ONLY if the caller may see them (else empty).
    Reads through the tenant-scoped manager; never crosses scope or tenant."""
    from apps.goals.models import Goal

    if not actor_can_access(caller, target):
        return None
    return list(Goal.objects.filter(employee_id=target.id).values_list("title", flat=True))


def _latest_score(target):
    """The target's latest CycleScore (for grounding the answer). The caller's
    access to ``target`` is already gated by ``_scoped_goal_titles`` upstream, so
    this only runs for an in-scope subject. Tenant-scoped."""
    from apps.goals.models import CycleScore

    return CycleScore.objects.filter(employee_id=target.id).order_by("-computed_at").first()


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

    intent = result.content.get("intent", "general")
    if intent == "write":
        # Propose-and-confirm (RW_BUILD_4): if the write maps to a SUPPORTED action
        # the caller is allowed to perform, return an inert PROPOSAL for the UI to
        # confirm (nothing executes here). Otherwise the read-only refusal holds —
        # the assistant never writes on its own say-so.
        from apps.ai.actions import propose_action

        proposal = propose_action(caller, query)
        if proposal is not None:
            return {
                "status": "proposal",
                "intent": "write",
                "proposal": proposal,
                "answer": proposal["summary"],
            }
        return {
            "status": "blocked",
            "intent": "write",
            "answer": "I'm a read-only assistant — I can't make changes or approvals.",
        }
    if intent == "capability":
        return {"status": "ok", "intent": "capability", "answer": _CAPABILITY_ANSWER, "data": []}
    if intent not in ("performance", "read"):  # "read" = legacy alias for performance
        # General / conversational / out-of-domain ("what day is today?", "I feel
        # lonely"). Decline politely + redirect — NEVER a performance-metrics dump.
        return {"status": "ok", "intent": "general", "answer": _GENERAL_ANSWER, "data": []}

    # PERFORMANCE intent. Resolve a target person from the RAW query (if any); the
    # fetch is ALWAYS scope-checked, so this can never surface out-of-scope data.
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

    # Grounded answer: name the goals and (if present + in scope) the latest cycle
    # score/risk — never vague. Still read-only; the data is exactly what a scoped
    # API read would return.
    is_self = target.id == caller.id
    who = "You" if is_self else target.display
    verb = "have" if is_self else "has"
    if titles:
        answer = f"{who} {verb} {len(titles)} goal(s): {', '.join(titles)}."
    else:
        answer = f"{who} {verb} no goals on record."
    score = _latest_score(target)
    if score is not None:
        answer += (
            f" Latest cycle score: T-score {float(score.t_score):.0f}"
            f" ({score.get_risk_status_display()})"
            f"{' — behind pace' if score.pace_behind else ''}."
        )
    return {"status": "ok", "intent": intent, "answer": answer, "data": titles}


def _fake(prompt, model):
    """Deterministic intent classifier for the FakeLLMProvider (tests + no-key path):
    write → capability → performance → general. Write is checked FIRST (safety), so
    'approve this review' is a write even though it mentions 'review'."""
    lowered = (prompt or "").lower()
    if any(w in lowered for w in _WRITE_WORDS):
        return {"intent": "write"}
    if lowered.strip() in ("help", "?") or any(p in lowered for p in _CAPABILITY_PHRASES):
        return {"intent": "capability"}
    if any(w in lowered for w in _PERF_WORDS):
        return {"intent": "performance"}
    return {"intent": "general"}


register_fake_output(AGENT_CODE, _fake)
