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

from django.conf import settings

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.rbac.scope import actor_can_access

AGENT_CODE = "chat"
SCHEMA = {"intent": str}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Destructive intent — deletion/destruction is NOT an agent action; refuse it explicitly.
# Requires a destructive VERB and a bulk-data OBJECT so incidental phrasing ("dropped the
# ball", "erase this typo") doesn't trip it. See chat_answer / BUGS_FOUND P0-1.
_DESTRUCTIVE_VERB_RE = re.compile(r"\b(delete|destroy|erase|wipe|purge|truncate)\b", re.I)
_DESTRUCTIVE_OBJ_RE = re.compile(
    r"\b(all|everyone|everything|datas?|records?|users?|people|employees?|accounts?|"
    r"table|tables|database|db)\b",
    re.I,
)
_WRITE_WORDS = (
    "approve", "reject", "delete", "change", "update", "finalize", "publish", "set ",
    # AGENTIC_CHAT verbs — drive an app action (propose-and-confirm); each maps to a
    # registered action (or, if none matches, the read-only refusal still holds).
    "draft", "enrich", "initiate", "create",
    # OVERNIGHT_A verbs — record a KPI actual; give recognition / kudos.
    "record", "recogni", "kudos",
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
    # diagnosis phrasings — "does she need help?", "is X on track / at risk / behind?"
    "need help", "needs help", "on track", "at risk", "behind", "struggling",
    "falling behind", "in trouble", "doing well", "doing okay", "how is", "how are",
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


def _capability_answer(caller):
    """A capability reply tailored to the CALLER's role/scope — not one scripted
    blurb for everyone. It names what they can actually ask about, so a manager
    hears about team insight and an employee hears about their own data."""
    role = getattr(caller, "role", "") or ""
    self_part = ("For you, I can summarise your goals and KPIs, your cycle score and "
                 "pace, and your review and feedback status — and reason about how "
                 "you're tracking (e.g. “do I need help this cycle?”).")
    if role in ("MANAGER", "HRBP", "ADMIN"):
        scope = {"MANAGER": "your team (everyone who reports to you)",
                 "HRBP": "your business unit",
                 "ADMIN": "everyone in the organisation"}[role]
        team_part = (
            f" For {scope}, I can tell you how any individual is doing, diagnose who "
            "needs help, list who's at risk or behind pace, rank who's doing best or "
            "worst, and count how many are off track — try “who's behind on my team?”, "
            "“who's doing best?”, or “does <name> need help?”.")
    else:
        team_part = (" I can only see your own data — not other people's — so I can't "
                     "report on colleagues.")
    return ("I'm your read-only performance assistant (I can't make changes or "
            f"approvals). {self_part}{team_part}")
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
    # ACTIVE goals only = the CURRENT cycle. Listing every cycle repeated titles
    # ("Cycle objectives" ×3) and read like filler; dedupe (preserve order) so the
    # answer is the person's real current objectives.
    titles = Goal.objects.filter(
        employee_id=target.id, status="ACTIVE"
    ).values_list("title", flat=True)
    seen, out = set(), []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ── conversation memory (C2) ─────────────────────────────────────────────────
#: Words that never identify a person — so "how are my goals doing" can't
#: accidentally name-match an employee called e.g. "Doing".
_NAME_STOP_WORDS = frozenset(
    "how what who when where why are is was were the a an my our your their his her its "
    "doing do does did have has had many much status this that with for and or about of "
    "on in at to from team report reports goal goals kpi kpis review reviews feedback "
    "score scores cycle cycles progress performance risk open active pending count number "
    "me i we you they show tell give latest current last week month quarter year today "
    "track On track behind ahead risk please can could would "
    # diagnosis vocabulary — never a person's name ("does she need help?")
    "need needs help support struggling struggle falling trouble okay ok well badly "
    "poorly attention flag flagged pace doing".lower().split()
)

_COUNT_Q_RE = re.compile(r"\bhow many\b|\bcount of\b|\bnumber of\b", re.I)

#: A DIAGNOSIS question about a specific person ("does X need help", "is X on
#: track / at risk / behind / struggling"). Routed to a reasoned, data-grounded
#: answer instead of the plain goal list. ("how is X" status stays on the summary
#: for now — migrated to the reasoned answer in a later increment.)
_DIAGNOSE_RE = re.compile(
    r"\bneeds?\s+help\b|\bneed\s+help\b|\bon\s+track\b|\bat\s+risk\b|\bbehind\b|"
    r"\bstruggl|\bfalling\b|\bin\s+trouble\b|\bhelp\s+(?:them|him|her)\b|\bhow\s+are\s+they\s+doing\b",
    re.I,
)

#: A TEAM-SCAN question ("who's behind / at risk / struggling / needs help",
#: "anyone at risk", "how many of my reports are behind"). Answered from the
#: caller's OWN reporting subtree only (managers/HRBP) — never the whole tenant.
_TEAM_SCAN_RE = re.compile(
    r"\bwho(?:'s| is| are|se)?\b.{0,40}\b(behind|at\s+risk|struggl|need|falling|trouble)\b|"
    r"\banyone\b.{0,30}\b(behind|at\s+risk|struggl|need|trouble)\b|"
    r"\bhow\s+many\b.{0,40}\b(behind|at\s+risk|struggl)\b",
    re.I,
)

#: A COMPARISON question ("who's doing best/worst on my team", "top/lowest
#: performer", "who's strongest/weakest"). Ranked over the caller's OWN reports.
_COMPARE_RE = re.compile(
    r"\bwho(?:'s| is| are)?\b.{0,40}\b(doing\s+best|doing\s+worst|best|worst|top|"
    r"strongest|weakest|highest|lowest|ahead)\b|\btop\s+performer|\bbest\s+performer|"
    r"\bworst\s+performer|\brank\b",
    re.I,
)

#: An AGGREGATION question — a COUNT over the team ("how many of my reports are
#: behind / at risk / on track"), answered as a number + summary, not a full list.
_AGG_RE = re.compile(
    r"\bhow\s+many\b.{0,40}\b(behind|at\s+risk|struggl|on\s+track|report|team)\b",
    re.I,
)

#: An "open/show the <thing we just made>" imperative — DEFINITE reference only
#: ("the/that/this/it"), so "open a check-in" (a new-thing WRITE) is untouched.
_OPEN_REF_RE = re.compile(
    r"^\s*(open|show me|show|go to|take me to)\s+(the|that|this|it\b|her\b|his\b)", re.I
)

#: ref type → the SPA route for "open it" (mirrors execute_action's artifacts).
_REF_DEEPLINK = {
    "review": lambda obj: f"/reviews/{obj.id}",
    "user": lambda obj: f"/people/{obj.id}",
    "feedback_cycle": lambda obj: "/feedback",
    "recognition": lambda obj: "/recognition",
    "goal": lambda obj: "/goals",
    "checkin": lambda obj: "/checkins",
    "roadmap": lambda obj: "/career",
    "succession_plan": lambda obj: "/succession",
}


def _answer_open_reference(caller, session, query):
    """Deterministic navigation for "open the draft / that review / it": resolve
    the most recent matching, access-rechecked session ref and answer with its
    deeplink. Returns None when nothing resolves (caller decides the fallback) —
    this must NEVER fall into a goals summary."""
    if session is None:
        return None
    from apps.ai.sessions import resolve_reference

    rtype, obj = resolve_reference(caller, session, query)
    if obj is None:
        return None
    link_fn = _REF_DEEPLINK.get(rtype)
    if link_fn is None:
        return None
    label = (
        getattr(obj, "display", None)
        or getattr(obj, "title", None)
        or rtype.replace("_", " ")
    )
    return {
        "status": "ok",
        "intent": "navigate",
        "answer": f"Here it is — opening {label}.",
        "data": [],
        "deeplink": link_fn(obj),
        "refs": [{"type": rtype, "id": str(obj.id), "label": str(label)}],
    }


def _classification_prompt(query: str, session) -> str:
    """The classifier prompt: recent conversation as CONTEXT + the current message.
    The user turn for ``query`` is already persisted by the view, so it is dropped
    from the context block. PII scrubbing happens in the gateway as usual."""
    if session is None:
        return query
    from apps.ai import sessions as chat_sessions

    turns = chat_sessions.recent_turns(session, limit=7)
    if turns and turns[-1].role == "user" and turns[-1].text == (query or "")[:8000]:
        turns = turns[:-1]
    lines = [f"{t.role}: {t.text[:200]}" for t in turns if (t.text or "").strip()]
    if not lines:
        return query
    return (
        "Conversation so far (context ONLY — classify the current message):\n"
        + "\n".join(lines[-6:])
        + f"\n\nCurrent message: {query}"
    )


def _named_candidates(query):
    """Every TENANT user whose display name (or email local-part) matches a name
    token in ``query``. Tenant-scoped (never cross-tenant) but NOT data-scope
    filtered — the caller's scope is applied by the call site, so we can tell
    "no such person" apart from "exists but outside your scope" and answer
    honestly. Returns ``(matches, wordset, tokens_of)``."""
    from django.db.models import Q

    from apps.identity.models import User

    words = [
        w for w in re.findall(r"[a-zA-Z]{3,}", (query or "").lower())
        if w not in _NAME_STOP_WORDS
    ][:8]
    if not words:
        return [], set(), {}
    cond = None
    for w in words:
        c = Q(display_name__icontains=w) | Q(email__istartswith=w)
        cond = c if cond is None else (cond | c)
    matches = []
    wordset = set(words)
    tokens_of = {}  # user.id -> set of name tokens (computed once, reused below)
    for u in User.objects.filter(cond)[:20]:  # tenant-scoped manager
        name_tokens = set(re.findall(r"[a-z]{3,}", (u.display_name or "").lower()))
        tokens_of[u.id] = name_tokens
        email_local = u.email.split("@")[0].lower()
        if (name_tokens & wordset) or (email_local in wordset):
            matches.append(u)
    return matches, wordset, tokens_of


def _pick_named(matches, wordset, tokens_of):
    """From a candidate set, pick the ONE person named, or a disambiguation list.
    Returns ``(user|None, ambiguous_names)``. Works on whatever set it is given —
    the call site passes only the IN-SCOPE candidates so a manager who names a
    colleague on their team resolves cleanly instead of being offered tenant-wide
    strangers they can't see."""
    if len(matches) == 1:
        return matches[0], []
    if len(matches) > 1:
        # A multi-word query may name ONE specific person ("leon petrova") whose
        # full name is among the loose token-OR matches. Prefer the unique candidate
        # whose name contains EVERY name-token the caller typed — so "Leon Petrova"
        # wins over the "Leon *" / "* Petrova" family instead of being buried in a
        # disambiguation list. Only the tokens that actually appear in some name
        # count (so trailing words like "doing"/"cycle" don't disqualify anyone).
        name_query_tokens = {
            t for t in wordset if any(t in toks for toks in tokens_of.values())
        }
        if len(name_query_tokens) >= 2:
            full = [u for u in matches if name_query_tokens <= tokens_of[u.id]]
            if len(full) == 1:
                return full[0], []
        return None, _disambiguation_labels(matches)
    return None, []


def _disambiguation_labels(users):
    """Readable choices for a "several people match" reply. When two people share
    the SAME display name (e.g. two "Leon Petrova"), a bare name list collapses to
    one useless entry — so we append the email to disambiguate ONLY the colliding
    names. Deduped by user id, stable order."""
    from collections import Counter

    counts = Counter(u.display for u in users)
    seen, labels = set(), []
    for u in sorted(users, key=lambda x: (x.display or "", x.email or "")):
        if u.id in seen:
            continue
        seen.add(u.id)
        labels.append(f"{u.display} ({u.email})" if counts[u.display] > 1 else u.display)
    return labels


def _resolve_named_person(caller, query):
    """Scope-agnostic name resolution (unit-test entry point): resolve a NAMED
    person from the whole tenant. Production goes through the scope-aware path in
    ``run`` — but the raw name-matching rules are identical and proven here."""
    matches, wordset, tokens_of = _named_candidates(query)
    return _pick_named(matches, wordset, tokens_of)


def _resolve_in_scope(caller, query):
    """Scope-aware person resolution for a performance question.

    Returns ``(target, ambiguous_names, out_of_scope)``:
      * ``target``          — the resolved IN-SCOPE user, or None.
      * ``ambiguous_names`` — >1 in-scope match → labels to disambiguate, else [].
      * ``out_of_scope``    — a **User** matching the TYPED NAME but OUTSIDE the
        caller's scope (so the caller can ground it and name it), or ``""`` when
        several out-of-scope people match, or ``None`` when the name simply isn't
        found. This lets the caller say "you don't have access to X" — and REMEMBER
        that attempt — instead of a misleading "not found" or a self-fallback.

    A multi-token name must FULLY match an in-scope person — so a manager asking
    about "Hugo O'Brien" never silently resolves to a same-surname "Hana O'Brien"
    on their own team. A single first-name token ("yuki") resolves to the one
    person on the caller's team when unique."""
    matches, wordset, tokens_of = _named_candidates(query)
    if not matches:
        return None, [], None
    in_scope = [u for u in matches if actor_can_access(caller, u)]
    # Tokens that are genuinely NAMES — they appear in some tenant user's name,
    # counted tenant-wide so "hugo" still counts even when Hugo is out of scope.
    real_tokens = {t for t in wordset if any(t in toks for toks in tokens_of.values())}

    def _full(cands):
        return [u for u in cands if real_tokens and real_tokens <= tokens_of[u.id]]

    def _oos(cands):
        """Out-of-scope signal: the single matching User (to ground+name), or ""
        when several match (name them generically), never leaking data either way."""
        return cands[0] if len(cands) == 1 else ""

    if len(real_tokens) >= 2:
        picks = _full(in_scope)
        if len(picks) == 1:
            return picks[0], [], None
        if len(picks) > 1:
            return None, _disambiguation_labels(picks), None
        # Nobody in scope matches the FULL name. Out of scope iff the tenant has one.
        tenant_full = _full(matches)
        return None, [], (_oos(tenant_full) if tenant_full else None)

    # A single (or zero) real name-token — loose, first-name style ("yuki").
    if len(in_scope) == 1:
        return in_scope[0], [], None
    if len(in_scope) > 1:
        return None, _disambiguation_labels(in_scope), None
    # None in scope, but the name matched tenant users → it's a scope boundary.
    return None, [], _oos(matches)


def _accessible_report_names(caller, limit=12):
    """Display names of the people ``caller`` may ask about (their reporting
    subtree, excluding themselves) — used to tell a manager who they CAN see when
    they hit a scope boundary. Capped so the reply stays readable."""
    from apps.identity.models import User
    from apps.rbac.scope import reporting_subtree_ids

    ids = reporting_subtree_ids(caller) - {caller.id}
    if not ids:
        return [], 0
    qs = User.objects.filter(id__in=ids).order_by("display_name")
    names = [u.display for u in qs[: limit + 1]]
    total = len(ids)
    return names[:limit], total


def _scope_denied_answer(caller, intent, name=None, ground_user=None):
    """Honest, role-aware refusal when a caller asks about someone OUTSIDE their
    data scope. It is a guardrail, not a bug: an EMPLOYEE sees only themselves; a
    MANAGER sees their own reports; only ADMIN/HR see the whole company. We say so
    plainly, list who the caller CAN ask about, and never leak the out-of-scope
    person's data.

    When ``ground_user`` is given, the refused person is GROUNDED on the session
    (a "user" ref) so a pronoun follow-up ("what about his reviews?") stays on them
    and gets refused again — instead of silently falling back to the caller's own
    data. The ref grants nothing: every read re-checks access."""
    role = getattr(caller, "role", "") or ""
    if role == "EMPLOYEE":
        subject = f"{name}'s" if name else "another person's"
        answer = (
            f"You don't have access to {subject} data — only an admin or HR can "
            "see everyone across the company. I can show your own goals, reviews, "
            "feedback and recognition."
        )
    elif role == "MANAGER":
        subject = f"{name}'s" if name else "that person's"
        names, total = _accessible_report_names(caller)
        if names:
            shown = ", ".join(names)
            more = f", and {total - len(names)} more" if total > len(names) else ""
            can = f" You can ask about the people on your team: {shown}{more}."
        else:
            can = " You can ask about your own goals, reviews and feedback."
        answer = (
            f"You don't have access to {subject} data — only an admin or HR can "
            f"see everyone across the company.{can}"
        )
    else:  # HRBP / ADMIN normally have tenant scope and never reach this branch.
        subject = f"{name}" if name else "That person"
        answer = (
            f"{subject} is outside the part of the organisation you can see, so I "
            "can't share their performance details."
        )
    out = {"status": "ok", "intent": intent, "answer": answer, "data": []}
    if ground_user is not None:
        out["refs"] = [{"type": "user", "id": str(ground_user.id),
                        "label": ground_user.display}]
    return out


def _answer_counts(caller, target, query, intent):
    """Deterministic counts for 'how many reviews/goals/feedback …' — real scoped
    querysets, never a goals-only misroute. Scope-checked like every read."""
    if target is None:
        return {"status": "ok", "intent": intent, "answer": "No matching person in your scope.", "data": []}
    if not actor_can_access(caller, target):
        return _scope_denied_answer(caller, intent, target.display)
    from apps.feedback.models import FeedbackRequest
    from apps.goals.models import Goal
    from apps.reviews.models import Review

    q = (query or "").lower()
    want_reviews = "review" in q
    want_goals = ("goal" in q) or ("kpi" in q) or ("objective" in q)
    want_feedback = "feedback" in q
    if not (want_reviews or want_goals or want_feedback):
        want_reviews = want_goals = want_feedback = True

    parts = []
    if want_reviews:
        qs = Review.objects.filter(employee_id=target.id)
        parts.append(f"{qs.count()} review(s), {qs.exclude(state='FINALIZED').count()} open")
    if want_goals:
        gs = Goal.objects.filter(employee_id=target.id)
        parts.append(f"{gs.filter(status='ACTIVE').count()} active goal(s) of {gs.count()} total")
    if want_feedback:
        pending = FeedbackRequest.objects.filter(giver_id=target.id, status="PENDING").count()
        parts.append(f"{pending} pending feedback request(s)")

    is_self = target.id == caller.id
    who, verb = ("You", "have") if is_self else (target.display, "has")
    return {
        "status": "ok",
        "intent": intent,
        "answer": f"{who} {verb} {'; '.join(parts)}.",
        "data": parts,
        "refs": [{"type": "user", "id": str(target.id), "label": target.display}],
    }


_TEAM_LIST_CAP = 8  # keep a scan reply readable; summarise the rest as "and N more"


def _answer_team_risk(caller, intent="performance", mode="all"):
    """Reasoned scan of the caller's reporting subtree for at-risk / behind people.
    Scoped to the caller's OWN reports (never the tenant). Read-only. ``mode`` is
    'at_risk' (rating), 'behind' (pace) or 'all'."""
    from apps.ai.insight import team_scan

    scan = team_scan(caller, mode=mode)
    if not scan["manages"]:
        return {
            "status": "ok", "intent": intent, "data": [],
            "answer": "You don't have any reports, so there's no team to scan. "
                      "I can tell you how you're doing this cycle instead.",
        }
    label = {"at_risk": "at risk", "behind": "behind pace", "all": "at risk or behind pace"}[mode]
    flagged = scan["flagged"]
    if not flagged:
        return {
            "status": "ok", "intent": intent, "data": [],
            "answer": f"Good news — none of your {scan['total']} team member(s) are "
                      f"{label} this cycle.",
        }
    shown = flagged[:_TEAM_LIST_CAP]
    lines = [
        f"{f['name']} ({f['risk']}{', behind pace' if f['pace_behind'] else ''})"
        for f in shown
    ]
    more = len(flagged) - len(shown)
    tail = f", and {more} more" if more > 0 else ""
    n = len(flagged)
    return {
        "status": "ok", "intent": intent,
        "answer": (f"{n} of your {scan['total']} team member(s) are {label}: "
                   f"{'; '.join(lines)}{tail}. Ask me about any of them for detail."),
        "data": [f["name"] for f in flagged],
    }


def _answer_team_ranking(caller, intent="performance", best=True):
    """Rank the caller's reports by cycle score (best/worst first). Scoped, read-only."""
    from apps.ai.insight import team_ranking

    rk = team_ranking(caller, best=best, limit=5)
    if not rk["manages"]:
        return {
            "status": "ok", "intent": intent, "data": [],
            "answer": "You don't have any reports to compare. I can tell you how "
                      "you're doing this cycle instead.",
        }
    if not rk["ranked"]:
        return {
            "status": "ok", "intent": intent, "data": [],
            "answer": "None of your reports have a scored cycle yet, so I can't rank "
                      "them. Ask me once this cycle is scored.",
        }
    which = "top" if best else "lowest"
    lines = [
        f"{i}. {r['name']} ({r['risk']}{', behind pace' if r['pace_behind'] else ''})"
        for i, r in enumerate(rk["ranked"], 1)
    ]
    note = (f" ({rk['unscored']} report(s) aren't scored yet.)"
            if rk["unscored"] else "")
    return {
        "status": "ok", "intent": intent,
        "answer": f"Your {which} performers this cycle: {'; '.join(lines)}.{note}",
        "data": [r["name"] for r in rk["ranked"]],
    }


def _answer_team_counts(caller, intent="performance"):
    """A COUNT summary over the caller's reports (for "how many are behind?").
    Scoped, read-only."""
    from apps.ai.insight import team_counts

    c = team_counts(caller)
    if not c["manages"]:
        return {
            "status": "ok", "intent": intent, "data": [],
            "answer": "You don't have any reports. I can tell you how you're doing "
                      "this cycle instead.",
        }
    unscored = c["total"] - c["scored"]
    tail = f" ({unscored} not scored yet.)" if unscored else ""
    return {
        "status": "ok", "intent": intent,
        "answer": (f"Of your {c['total']} report(s): {c['on_track']} on track, "
                   f"{c['at_risk']} at risk, {c['behind']} behind pace.{tail} "
                   "Ask 'who's behind?' for the names."),
        "data": [f"on_track={c['on_track']}", f"at_risk={c['at_risk']}", f"behind={c['behind']}"],
    }


def _latest_score(target):
    """The target's latest CycleScore (for grounding the answer). The caller's
    access to ``target`` is already gated by ``_scoped_goal_titles`` upstream, so
    this only runs for an in-scope subject. Tenant-scoped."""
    from apps.goals.models import CycleScore

    return CycleScore.objects.filter(employee_id=target.id).order_by("-computed_at").first()


def chat_answer(caller, query: str, session=None) -> dict:
    """Answer ``query`` for ``caller`` (RBAC-bound). Returns a dict with a ``status``
    the view maps to HTTP: ok | plan | not_configured | budget | blocked | error.

    AGENT_UX_V3 §A — ONE send path: a write-intent message now returns a PLAN
    (``status="plan"``, a :class:`ChatPlan`) the human approves step by step, instead
    of a single proposal. A single intent → a 1-step plan; a multi-step ask → N steps;
    parts that can't be prepared are said so in the plan summary (nothing silently
    dropped). Read intents are UNCHANGED. The plan path needs a ``session`` (owner-
    bound memory); without one (legacy/direct callers) the old single-proposal path
    still applies — the gate itself is identical either way.
    """
    # "Open the draft / that review / it" — a definite-reference navigation ask,
    # resolved deterministically from the session's access-rechecked refs BEFORE
    # any LLM call. A definite reference is ALWAYS navigation (new-thing writes
    # say "open A check-in" and are untouched), so when nothing resolves we say
    # so honestly — never a goals dump, never a spurious plan.
    if _OPEN_REF_RE.search(query or ""):
        opened = _answer_open_reference(caller, session, query)
        if opened is not None:
            return opened
        return {
            "status": "ok", "intent": "general", "data": [],
            "answer": "I don't see a recent record like that in this conversation — "
                      "tell me what to open (e.g. “open Vera's review”), or use the "
                      "Open button on the result card above.",
        }

    # C2: classification sees the CONVERSATION (recent turns as context) so a
    # follow-up ("and her reviews?") keeps its meaning. The context block is
    # explicitly marked context-only; the current message is what's classified.
    result = gateway.run(
        tenant=caller.tenant_id,
        agent_code=AGENT_CODE,
        prompt=_classification_prompt(query, session),
        model="chat",
        schema=SCHEMA,
    )
    if result.status == "NOT_CONFIGURED":
        return {"status": "not_configured"}
    if result.status == "BUDGET_EXCEEDED":
        return {"status": "budget", "errors": result.errors}
    if not result.ok:
        return {"status": "error", "detail": result.status}

    # Deletion/destruction is NOT an agent action at all — there is no delete in the
    # action registry, so a bulk-destructive request can never run. Refuse it EXPLICITLY
    # (verb + a bulk data object, so "he dropped the ball" is unaffected) instead of
    # silently emitting an empty plan, so the boundary is honest and visible. Nothing to
    # gate — there is nothing to execute. (BUGS_FOUND P0-1.)
    if _DESTRUCTIVE_VERB_RE.search(query or "") and _DESTRUCTIVE_OBJ_RE.search(query or ""):
        return {
            "status": "blocked", "intent": "general", "data": [],
            "answer": "I can't delete, erase, or destroy data — there's no such action "
                      "available to me. I can help you review, draft, summarise, or approve "
                      "within what you're allowed to see.",
        }

    intent = result.content.get("intent", "general")
    if intent == "write":
        if session is not None:
            # AGENT_UX_V3 §A — everything is a plan. The planner emits action NAMES
            # only; params/scope resolve server-side; the plan is INERT until a
            # per-step Approve through the existing gate (contract unchanged).
            from apps.ai.planner import build_plan

            out = build_plan(caller, session, query)
            if out["status"] == "planned":
                return {"status": "plan", "intent": "write", "plan": out["plan"]}
            if out["status"] == "not_configured":
                return {"status": "not_configured"}
            if out["status"] == "budget":
                return {"status": "budget", "errors": out.get("errors")}
            return {"status": "error", "detail": out.get("detail")}
        # Legacy path (no session): the single inert PROPOSAL (RW_BUILD_4). Kept so
        # direct callers still work; the write gate is identical.
        from apps.ai.actions import propose_action, write_refusal

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
            "answer": write_refusal(caller, query)
            or "I'm a read-only assistant — I can't make changes or approvals.",
        }
    # TEAM insight ("who's behind / at risk / doing best on my team?", "how many
    # of my reports are behind?") — reasoned over the caller's OWN reporting
    # subtree, gated by VIEW_TEAM_SCORES. Checked ahead of search/performance so
    # it isn't mis-routed to the goal-name search or a single-person lookup.
    _tq = query or ""
    _is_compare = bool(_COMPARE_RE.search(_tq))
    _is_agg = bool(_AGG_RE.search(_tq))
    _is_scan = bool(_TEAM_SCAN_RE.search(_tq))
    if _is_compare or _is_agg or _is_scan:
        from apps.rbac.matrix import Capability, role_has_capability

        if not role_has_capability(caller.role, Capability.VIEW_TEAM_SCORES):
            # An individual contributor manages no one — say so honestly, offer self.
            return {
                "status": "ok", "intent": "performance", "data": [],
                "answer": "You don't have any reports, so there's no team to scan. "
                          "I can tell you how you're doing this cycle instead.",
            }
        if _is_compare:
            worst = bool(re.search(r"worst|weakest|lowest|struggl|behind", _tq, re.I))
            return _answer_team_ranking(caller, best=not worst)
        if _is_agg:
            return _answer_team_counts(caller)
        # A scan: pick the mode from the phrasing.
        low = _tq.lower()
        mode = "at_risk" if ("at risk" in low and "behind" not in low) else (
            "behind" if "behind" in low else "all")
        return _answer_team_risk(caller, mode=mode)
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
        return {"status": "ok", "intent": "capability",
                "answer": _capability_answer(caller), "data": []}
    if intent not in ("performance", "read"):  # "read" = legacy alias for performance
        # General / conversational / out-of-domain ("what day is today?", "I feel
        # lonely"). Decline politely + redirect — NEVER a performance-metrics dump.
        return {"status": "ok", "intent": "general", "answer": _GENERAL_ANSWER, "data": []}

    # PERFORMANCE intent. Resolve a target person: an explicit email → a remembered
    # person from THIS conversation ("she", "her" — session refs, access re-checked)
    # → a person NAMED in the query (unique tenant match). The fetch is ALWAYS
    # scope-checked, so memory/names can never surface out-of-scope data (C2).
    from apps.identity.models import User

    match = _EMAIL_RE.search(query or "")
    target = caller
    if match:
        found = User.objects.filter(email=match.group(0)).first()  # tenant-scoped
        if found is not None and not actor_can_access(caller, found):
            # Exists in the tenant but outside the caller's data scope — say so
            # honestly (who they are, who the caller CAN ask about), never leak,
            # and ground them so a pronoun follow-up stays on them.
            return _scope_denied_answer(caller, intent, found.display, ground_user=found)
        target = found  # may be None (cross-tenant / unknown) → empty answer
    else:
        # An explicitly NAMED person ALWAYS wins over remembered context: after
        # "how is Vera doing?", the follow-up "Ethan Nguyen, how is he doing?" must
        # resolve to Ethan — not stay on Vera via the pronoun. Only a PURELY deictic
        # follow-up ("how is she doing?", with no name typed) falls back to memory.
        #
        # Resolution is SCOPE-AWARE: match names tenant-wide, keep only the people
        # the caller may actually see, and require a full-name match. So a manager
        # asking "how is yuki doing?" resolves to the one Yuki ON THEIR TEAM (not a
        # list of strangers), "Hugo O'Brien" never silently becomes a same-surname
        # teammate, and a name that exists only outside their scope gets an honest
        # "you don't have access" reply.
        named, ambiguous, out_of_scope = _resolve_in_scope(caller, query)
        # A deictic pronoun ("she", "he", "them", "that person") is NOT a name — it
        # points at the remembered person. Only a real name token counts as "typed
        # a name" (which is what should override memory / trigger a not-found).
        _deictic = {"they", "them", "their", "her", "him", "his", "she", "he", "person"}
        _tokens = {w for w in re.findall(r"[a-z]+", (query or "").lower())}
        typed_a_name = bool([
            w for w in re.findall(r"[a-zA-Z]{3,}", (query or "").lower())
            if w not in _NAME_STOP_WORDS and w not in _deictic
        ])
        # A deictic PERSON reference ("he/she/they/his/her…", "that person") points
        # at someone OTHER than the caller — it must bind to the LAST person named
        # this conversation, and never silently fall back to the caller's own data.
        person_deixis = bool(_tokens & {
            "he", "she", "they", "him", "her", "them", "his", "their", "hers", "theirs"}
        ) or bool(re.search(r"\b(that|this|the same)\s+person\b", (query or "").lower()))
        if named is not None:
            target = named
        elif ambiguous:
            return {
                "status": "ok", "intent": intent, "data": [],
                "answer": f"Several people match that name: {', '.join(ambiguous)}. "
                          "Try their full name or their email address.",
            }
        elif isinstance(out_of_scope, User):
            # Named a real person OUTSIDE scope this turn — refuse honestly AND
            # ground them so a pronoun follow-up stays on them (never self).
            return _scope_denied_answer(caller, intent, out_of_scope.display,
                                        ground_user=out_of_scope)
        elif out_of_scope == "":
            # Several out-of-scope people match the name — generic honest refusal.
            return _scope_denied_answer(caller, intent, None)
        elif typed_a_name:
            return {
                "status": "ok", "intent": intent, "data": [],
                "answer": "I couldn't find anyone by that name — "
                          "try their full name or their email address.",
            }
        elif person_deixis:
            # A pronoun/"that person" — bind to the MOST RECENT person referenced
            # (regardless of scope), then access-check THAT one. Crucially we do NOT
            # skip an out-of-scope referent to land on an older accessible one (e.g.
            # the caller themselves) — "his" after asking about someone you can't see
            # must stay refused, not silently switch to your own data.
            prior = None
            if session is not None:
                from apps.ai.sessions import last_referenced_person_any_scope

                prior = last_referenced_person_any_scope(caller, session)
            if prior is None:
                return {
                    "status": "ok", "intent": intent, "data": [],
                    "answer": "I'm not sure who you mean — tell me the person's "
                              "name or their email address.",
                }
            if not actor_can_access(caller, prior):
                return _scope_denied_answer(caller, intent, prior.display,
                                            ground_user=prior)
            target = prior
        # else: no name, no pronoun → answer about the caller (self).

    if target is None:
        return {"status": "ok", "intent": intent, "answer": "No matching person in your scope.", "data": []}

    # Count-questions get REAL counts (reviews/goals/feedback), not a goals dump.
    if _COUNT_Q_RE.search(query or ""):
        return _answer_counts(caller, target, query, intent)

    # A follow-up specifically about reviews/feedback ("what about his reviews?")
    # answers THAT, not the default goals summary.
    _q = (query or "").lower()
    if re.search(r"\b(reviews?|feedback)\b", _q) and not re.search(
        r"\b(goals?|kpis?|objectives?)\b", _q
    ):
        return _answer_counts(caller, target, query, intent)

    # A DIAGNOSIS question ("does she need help?", "is X on track / at risk /
    # behind?") gets a reasoned answer grounded in real cycle status + KPI
    # attainment — not the flat goal list. Scope already re-checked inside.
    if _DIAGNOSE_RE.search(_q):
        from apps.ai.insight import diagnose_person, llm_phrase

        diag = diagnose_person(caller, target)
        if diag is None:
            return _scope_denied_answer(caller, intent, target.display)
        # The LLM rephrases the already-correct, in-scope draft in natural language,
        # grounded ONLY in these facts; falls back to the draft on any error/no-key.
        answer = llm_phrase(caller.tenant_id, query, diag["facts"], diag["answer"])
        return {
            "status": "ok", "intent": intent, "answer": answer,
            "data": [g["title"] for g in diag["facts"]["goals"]],
            "refs": [{"type": "user", "id": str(target.id), "label": target.display}],
        }

    titles = _scoped_goal_titles(caller, target)
    if titles is None:
        # Out of the caller's scope — an honest, role-aware guardrail reply (who
        # they CAN ask about), never a bare "no data" that reads like a bug.
        return _scope_denied_answer(caller, intent, target.display)

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
        pace = " — behind pace" if score.pace_behind else ""
        if getattr(settings, "V1_HIDE_TSCORE", True):
            # v1: plain status, no T-score number (matches the UI).
            answer += f" Latest cycle: {score.get_risk_status_display()}{pace}."
        else:
            answer += (
                f" Latest cycle score: T-score {float(score.t_score):.0f}"
                f" ({score.get_risk_status_display()}){pace}."
            )
    return {
        "status": "ok", "intent": intent, "answer": answer, "data": titles,
        # Ground the answered person on the assistant turn so a follow-up
        # ("what about her reviews?") resolves — access re-checked on use (C2).
        "refs": [{"type": "user", "id": str(target.id), "label": target.display}],
    }


def _fake(prompt, model):
    """Deterministic intent classifier for the FakeLLMProvider (tests + no-key path):
    write → capability → performance → general. Write is checked FIRST (safety), so
    'approve this review' is a write even though it mentions 'review'."""
    lowered = (prompt or "").lower()
    # C2: the prompt may carry a conversation-context block; classify ONLY the
    # current message (mirrors the instruction the real LLM receives).
    if "current message:" in lowered:
        lowered = lowered.rsplit("current message:", 1)[-1]
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
