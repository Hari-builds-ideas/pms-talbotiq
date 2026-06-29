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
_WRITE_WORDS = (
    "approve", "reject", "delete", "change", "update", "finalize", "publish", "set ",
    # AGENTIC_CHAT verbs — drive an app action (propose-and-confirm); each maps to a
    # registered action (or, if none matches, the read-only refusal still holds).
    "draft", "enrich", "initiate", "create",
)
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
#: Cues for a TEAM "find people" query (RW_BUILD_5 NL search). Checked BEFORE the
#: performance words (a search mentions 'goal'/'check-in' too) so a manager's
#: "who's missing goals?" routes to search, not a self-performance answer.
_SEARCH_PHRASES = (
    "missing goal", "missing a goal", "missing goals", "no active goal", "without a goal",
    "without goals", "no goal set", "who has no goal", "who is missing",
    "haven't checked in", "hasn't checked in", "not checked in", "without a check-in",
    "no check-in", "missing check-in", "checked in this week", "who on my team",
    "which of my reports", "who hasn't",
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

#: Per-search phrasing for the chat surface: (clause, empty-set answer). The count +
#: subject grammar is composed in :func:`_answer_search`.
_SEARCH_LABELS = {
    "employees_missing_goals": (
        "no active goal set", "Everyone on your team has an active goal set."
    ),
    "reports_without_checkin": (
        "not submitted a check-in this week",
        "Everyone on your team has submitted a check-in this week.",
    ),
}


def _answer_search(caller, query: str) -> dict:
    """Route a TEAM 'find people' query to the deterministic, scope-bound NL search
    (RW_BUILD_5). Manager/HR only (gated by the caller); the names ride back in
    ``data`` exactly like a scoped read, so the chat UI renders them with no change."""
    from apps.ai.agents.nl_search import nl_search

    out = nl_search(caller, query)
    if out["status"] == "not_configured":
        return {"status": "not_configured"}
    if out["status"] == "budget":
        return {"status": "budget", "errors": out.get("errors")}
    if out["status"] != "ok":
        return {"status": "error", "detail": out.get("detail")}
    if out["search"] == "unknown":
        return {
            "status": "ok", "intent": "search", "data": [],
            "answer": "I couldn't map that to a supported search. Try: “who's missing "
                      "goals?” or “who hasn't checked in this week?”",
        }
    names = [r["employee"] for r in out["results"]]
    clause, empty = _SEARCH_LABELS[out["search"]]
    n = len(names)
    answer = empty if n == 0 else (
        f"{n} {'person' if n == 1 else 'people'} on your team "
        f"{'has' if n == 1 else 'have'} {clause}:"
    )
    return {"status": "ok", "intent": "search", "answer": answer, "data": names}


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
        from apps.ai.actions import propose_action, write_refusal

        proposal = propose_action(caller, query)
        if proposal is not None:
            return {
                "status": "proposal",
                "intent": "write",
                "proposal": proposal,
                "answer": proposal["summary"],
            }
        # No proposal: give a PRECISE reason (capability refusal / "what would you like")
        # instead of a blanket read-only line — but keep genuine refusals refusing, and
        # never reveal a sensitive feature (succession) the caller can't see.
        return {
            "status": "blocked",
            "intent": "write",
            "answer": write_refusal(caller, query)
            or "I'm a read-only assistant — I can't make changes or approvals.",
        }
    if intent == "search":
        # Team "find people" search is a manager/HR capability (VIEW_TEAM_SCORES). An
        # employee's search-shaped query falls through to the general redirect — the
        # feature is never exposed to employees (the deterministic search is also
        # scope-bound, so it would return nothing anyway — this is belt-and-braces).
        from apps.rbac.matrix import Capability, role_has_capability

        if role_has_capability(caller.role, Capability.VIEW_TEAM_SCORES):
            return _answer_search(caller, query)
        intent = "general"
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
    if "360" in lowered and any(v in lowered for v in ("start", "begin", "launch", "set up", "kick off")):
        return {"intent": "write"}  # "start a 360 for X"
    if lowered.strip() in ("help", "?") or any(p in lowered for p in _CAPABILITY_PHRASES):
        return {"intent": "capability"}
    if any(p in lowered for p in _SEARCH_PHRASES):  # team "find people" — before perf
        return {"intent": "search"}
    if any(w in lowered for w in _PERF_WORDS):
        return {"intent": "performance"}
    return {"intent": "general"}


register_fake_output(AGENT_CODE, _fake)
