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

import logging
import re

from django.conf import settings

from apps.ai.gateway import gateway
from apps.ai.providers import register_fake_output
from apps.rbac.scope import actor_can_access

logger = logging.getLogger("pms.ai.chat")

AGENT_CODE = "chat"
SCHEMA = {"intent": str}

#: Marks a deterministic reply that is a NON-answer: the general redirect, a name that
#: didn't resolve, an unmapped search, an empty scope. Those — and only those — are the
#: turns handed to the function-calling agent (AGENT_V3/C). Every real answer, refusal,
#: disambiguation and plan is left exactly as it was, so nothing already working can
#: regress. The marker is stripped in :func:`chat_answer` and never reaches the API.
_UNANSWERED = "_unanswered"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Destructive intent — deletion/destruction is NOT an agent action; refuse it explicitly.
# Requires a destructive VERB and a bulk-data OBJECT so incidental phrasing ("dropped the
# ball", "erase this typo") doesn't trip it. See chat_answer / BUGS_FOUND P0-1.
_DESTRUCTIVE_VERB_RE = re.compile(r"\b(delete|destroy|erase|wipe|purge|truncate)\b", re.I)
_DESTRUCTIVE_OBJ_RE = re.compile(
    r"\b(all|everyone|everything|datas?|records?|users?|people|employees?|accounts?|"
    r"table|tables|database|db|"
    # single PMS records: an explicit "delete X's review/goal/…" is unambiguously a
    # delete request (paired with a destructive verb), so answer it honestly ("I can't
    # delete") instead of a vague "couldn't set up a step".
    r"reviews?|goals?|feedback|kpis?|check-?ins?|recognitions?|roadmaps?|"
    r"one-?on-?ones?|1-?on-?1s?)\b",
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
    # comparison phrasings — "compare X and Y", "X vs Y"
    "compare", "compared", " vs ", "versus",
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
        # Two supported searches, and this was neither — so it is a team question with
        # no pre-coded path, which is the agent's job (AGENT_V3/C). Marked; if the agent
        # calls no tool, this honest deflection is still what goes out.
        return {
            "status": "ok", "intent": "search", "data": [], _UNANSWERED: True,
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
    "own mine myself owns other another else one ones "
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

#: A FIRST-PERSON, self-referential message ("what are MY goals", "how am I
#: doing", "my own KPIs", "am I on track"). Per AGENT_INTEL_V2 §2 Example A the
#: subject is the CURRENT USER — never a name lookup, even when a domain word
#: like "own" slips past the name-stop list. Deictic third-person pronouns
#: ("he/she/they") are handled separately and take precedence.
_SELF_REF_RE = re.compile(r"\b(my|mine|myself|i|me|i'm)\b", re.I)

#: POSSESSIVE self-reference only ("my"/"mine"/"my own") — for detecting a genuine
#: "my goals AND X's" mixed query. Excludes bare "me"/"i" so "show me X's goals"
#: (where "me" is the indirect object, not a claim on the caller's own data) is NOT
#: mistaken for a self-reference.
#:
#: "my <person>" is also excluded. "my manager is off sick, is X at risk?" claims
#: nothing about the caller's OWN performance — but a bare "my" made it a mixed
#: self+other query, so the reply opened with the caller's own risk and pace when they
#: had asked about somebody else entirely.
_SELF_MINE_RE = re.compile(
    r"\b(?:my|mine|my\s+own)\b(?!\s+(?:manager|managers|boss|lead|leads|team|teams|"
    r"report|reports|colleague|colleagues|peer|peers|director|hrbp|skip|mentor)\b)",
    re.I,
)

#: An EXPLICIT request for the raw goal LIST ("show/list my goals", "what are my
#: goals"). Only these get the flat title list; everything else about a person
#: ("how is X?", bare status) gets the reasoned, phrased answer.
_LIST_GOALS_RE = re.compile(
    r"\b(show|list|see|what(?:'s| is| are)?|which)\b[\w\s'’]{0,24}\bgoals?\b",
    re.I,
)

#: A "which of them" follow-up after ≥2 people were just discussed/compared
#: ("who needs more support?", "who's worse?", "which one should I focus on?").
#: Resolved against the entities just referenced (AGENT_INTEL_V2 §2 Example C).
#: Team-wide phrasings ("…on my team", "…of my reports") are excluded so the
#: team-scan path still owns those.
_GROUP_SUPPORT_RE = re.compile(
    r"\bwho\b.{0,30}\b(needs?|more\s+support|more\s+help|attention|worse|weaker|"
    r"struggl|behind|at\s+risk|focus|concern|prioriti)\w*|"
    r"\bwhich\s+(one|of\s+them|of\s+the\s+two)\b",
    re.I,
)
_GROUP_TEAMWORD_RE = re.compile(r"\b(team|reports?|everyone|all\s+of)\b", re.I)

#: A question whose SUBJECT is the caller's team — several people, not one, and not the
#: caller. "compare my two weakest performers", "summarise my team's biggest risks".
#:
#: This exists because "my" otherwise reads as self-reference: the question fell through
#: to the single-person path, resolved to the caller, and came back describing their own
#: goals. Those questions now go to the function-calling agent (AGENT_V3/C). Checked
#: LAST, so the three pre-coded team shapes above keep their deterministic answers.
_TEAM_SUBJECT_RE = re.compile(
    r"\bmy\s+(?:\w+\s+){0,2}(?:team|reports?|directs?|people|performers?|employees?|staff)\b|"
    r"\b(?:the|my)\s+(?:top|best|worst|weakest|strongest)\s+(?:\w+\s+){0,2}"
    r"(?:performers?|reports?|people|employees?)\b|"
    r"\beveryone\s+(?:on|in)\s+my\b|\ball\s+(?:of\s+)?my\s+(?:reports?|team)\b",
    re.I,
)

#: "the first / second / other one" — a pick from the most recent disambiguation.
_ORDINAL_ONE_RE = re.compile(
    r"\bthe\s+(first|1st|second|2nd|third|3rd|other|last)\b(?:\s+one)?|"
    r"\b(first|second|third)\s+one\b",
    re.I,
)
_ORDINAL_INDEX = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
                  "other": 1}  # "last" handled specially

#: "the first/second person (we discussed)", "go back to the first one" — a pick by
#: CONVERSATION ORDER (distinct people in first-mention order), for topic-switch
#: refer-back ("how is Akhil?" … "how is Mei?" … "and the first person again?").
_ORDINAL_PERSON_RE = re.compile(
    r"\bthe\s+(first|1st|second|2nd|third|3rd|last)\s+person\b|"
    r"\bgo\s+back\s+to\s+the\s+(first|1st|second|2nd|third|3rd|last)\b",
    re.I,
)

#: "his/her/their OTHER goal", "the first/second/last goal" — a GOAL-level ordinal
#: reference. Isolates ONE of the resolved person's goals (spec §0 Example B) instead
#: of listing them all. Possessive/article + ordinal-or-"other" + "goal".
_GOAL_ORDINAL_RE = re.compile(
    r"\b(?:his|her|their|its|the|my|your)\s+"
    r"(other|first|second|third|fourth|last|1st|2nd|3rd|4th)\s+goal\b",
    re.I,
)
_GOAL_ORDINAL_NORM = {"1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth"}

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


def _dedup_sorted_users(users):
    """Candidate users deduped by id, in a stable (display, email) order — the
    canonical offered order shared by the labels AND the grounded refs, so "the
    first one" later means the first label."""
    seen, out = set(), []
    for u in sorted(users, key=lambda x: (x.display or "", x.email or "")):
        if u.id not in seen:
            seen.add(u.id)
            out.append(u)
    return out


def _disambiguation_labels(users):
    """Readable choices for a "several people match" reply. When two people share
    the SAME display name (e.g. two "Leon Petrova"), a bare name list collapses to
    one useless entry — so we append the email to disambiguate ONLY the colliding
    names. Deduped, in the canonical offered order."""
    from collections import Counter

    us = _dedup_sorted_users(users)
    counts = Counter(u.display for u in us)
    return [f"{u.display} ({u.email})" if counts[u.display] > 1 else u.display for u in us]


def _resolve_named_person(caller, query):
    """Scope-agnostic name resolution: the person NAMED in ``query``, anywhere in the
    tenant, as ``(user|None, ambiguous_labels)``.

    Delegates to the canonical directory resolver on the same strict settings the data
    path uses, so the rules exercised here are the rules production runs — this used to
    call a separate matcher, which meant its tests were guarding code nothing else
    used."""
    from apps.ai.directory import AMBIGUOUS, resolve_person_in_population, suggest_candidates

    strict = {"exclude_self": False, "allow_fuzzy": False, "require_full_name": True}
    hit = resolve_person_in_population(caller, query, **strict)
    if hit is AMBIGUOUS:
        return None, _disambiguation_labels(suggest_candidates(caller, query, exclude_self=False))
    return (hit, []) if hit is not None else (None, [])


def _is_answerable_data_question(caller, query: str) -> bool:
    """True when ``query`` is a real performance question we could answer, regardless
    of how the classifier labelled it (AGENT_REBUILD/C §3).

    Two independent signals, both deterministic:
      * it uses performance vocabulary ("goals", "at risk", "on track", "compare"…);
      * it is a QUESTION that names somebody the tenant directory knows.

    The second is deliberately gated on question form. A stray word that happens to
    prefix a colleague's name shouldn't turn "what day is today?" into a report on
    someone — asking about a person requires actually asking. Returning True only
    routes the message to the performance path; that path still resolves the person
    itself and still applies the full scope gate, so this can widen no access.
    """
    # ONE definition of "this is a question", shared with the conversation router.
    # A second copy here is exactly how the two name matchers drifted apart.
    from apps.ai.conversation import _QUESTION_RE

    text = (query or "").strip()
    if not text:
        return False
    low = text.lower()
    if any(w in low for w in _PERF_WORDS):
        return True
    if not (text.endswith("?") or _QUESTION_RE.match(text)):
        return False
    named, ambiguous, out_of_scope = _resolve_in_scope(caller, text)
    return named is not None or bool(ambiguous) or out_of_scope is not None


def _resolve_in_scope(caller, query):
    """Scope-aware person resolution for a performance question.

    Returns ``(target, ambiguous, out_of_scope)``:
      * ``target``          — the resolved IN-SCOPE user, or None.
      * ``ambiguous``       — >1 in-scope match → the candidate **User** list to
        disambiguate (labels + refs built by the caller), else ``[]``.
      * ``out_of_scope``    — a **User** matching the TYPED NAME but OUTSIDE the
        caller's scope (so the caller can ground it and name it), or ``""`` when
        several out-of-scope people match, or ``None`` when the name simply isn't
        found. This lets the caller say "you don't have access to X" — and REMEMBER
        that attempt — instead of a misleading "not found" or a self-fallback.

    A multi-token name must FULLY match an in-scope person — so a manager asking
    about "Hugo O'Brien" never silently resolves to a same-surname "Hana O'Brien"
    on their own team. A single first-name token ("yuki") resolves to the one
    person on the caller's team when unique.

    AGENT_REBUILD/A — the matching itself is delegated to the ONE canonical directory
    resolver (:mod:`apps.ai.directory`), run twice: over the caller's VISIBLE
    population to find the answer, and (only if that misses) over the whole tenant to
    tell "you can't see them" apart from "they don't exist". The second pass reads
    IDENTITY ONLY — it never touches performance data, and the caller still refuses
    the question; it just refuses honestly.

    This used to be a second, independent name matcher, and the two drifted apart in
    ways only visible at scale: it tokenized with an ASCII-only pattern (so accented
    and non-Latin names matched nothing) and discarded tokens under three characters
    (so middle initials and short names were dropped). One definition of "does this
    text name this person" is the only way those stay in agreement.
    """
    from apps.ai.actions import _visible_user_ids
    from apps.ai.directory import AMBIGUOUS, resolve_person_in_population, suggest_candidates

    # Strict mode on both passes: no fuzzy correction (the caller offers an explicit,
    # scope-limited "did you mean…?" instead) and a typed full name must match in full.
    strict = {"exclude_self": False, "allow_fuzzy": False, "require_full_name": True}

    visible = _visible_user_ids(caller)
    if visible:
        hit = resolve_person_in_population(caller, query, population_ids=visible, **strict)
        if hit is AMBIGUOUS:
            options = suggest_candidates(caller, query, population_ids=visible, exclude_self=False)
            if options:
                return None, _dedup_sorted_users(options), None
        elif hit is not None:
            return hit, [], None

    # Nobody in scope. Identity-only lookup across the tenant so the refusal can be
    # specific ("you don't have access to X") rather than a misleading "not found".
    elsewhere = resolve_person_in_population(caller, query, population_ids=None, **strict)
    if elsewhere is AMBIGUOUS:
        return None, [], ""      # several out-of-scope matches → generic refusal
    if elsewhere is not None:
        return None, [], elsewhere
    return None, [], None


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


def _answer_team_risk(caller, intent="performance", mode="all", exclude=None):
    """Reasoned scan of the caller's reporting subtree for at-risk / behind people.
    Scoped to the caller's OWN reports (never the tenant). Read-only. ``mode`` is
    'at_risk' (rating), 'behind' (pace) or 'all'. ``exclude`` is an optional User to
    drop from the list — used for "the OTHER engineer who's behind / who ELSE?" so
    the person just discussed isn't repeated."""
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
    excluded_here = bool(exclude) and any(f.get("id") == exclude.id for f in flagged)
    if excluded_here:
        flagged = [f for f in flagged if f.get("id") != exclude.id]
    if not flagged:
        base = (f"Good news — none of your {scan['total']} team member(s) are "
                f"{label} this cycle.")
        if excluded_here:
            base = (f"Aside from {exclude.display}, none of your other team member(s) "
                    f"are {label} this cycle.")
        return {"status": "ok", "intent": intent, "data": [], "answer": base}
    shown = flagged[:_TEAM_LIST_CAP]
    lines = [
        f"{f['name']} ({f['risk']}{', behind pace' if f['pace_behind'] else ''})"
        for f in shown
    ]
    more = len(flagged) - len(shown)
    tail = f", and {more} more" if more > 0 else ""
    n = len(flagged)
    lead = (f"Aside from {exclude.display}, {n} other of your {scan['total']} team "
            f"member(s) {'is' if n == 1 else 'are'} {label}: "
            if excluded_here else
            f"{n} of your {scan['total']} team member(s) are {label}: ")
    return {
        "status": "ok", "intent": intent,
        "answer": f"{lead}{'; '.join(lines)}{tail}. Ask me about any of them for detail.",
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


_COMPARE_SPLIT_RE = re.compile(r"\b(?:and|vs\.?|versus|compared\s+to|with|to)\b|,", re.I)

#: A comparison SUBJECT that is the current user ("compare me with X", "how do I
#: compare to X", "compare my goals with X"). Possessive/pronoun first person.
_SELF_SUBJECT_RE = re.compile(r"\b(me|myself|my|mine|i)\b", re.I)

#: A comparison SUBJECT given as a 3rd-person pronoun ("compare him with me") — it
#: corefers to the last-discussed person (resolved via the session, access re-checked).
_DEIXIS_SUBJECT_RE = re.compile(
    r"\b(he|him|his|she|her|hers|they|them|their|theirs)\b|"
    r"\b(?:that|this|the\s+same)\s+person\b", re.I)


def _resolve_multiple(caller, query, session=None):
    """People in a comparison ("how are Akhil and Mei doing?", "compare X and Y",
    "compare him with me"). Splits on and/vs/with/to/comma, resolves each segment IN
    SCOPE independently. A first-person segment ("me"/"my"/"I") resolves to the CURRENT
    USER (always in their own scope); a 3rd-person pronoun ("him"/"her") corefers to the
    last-discussed person via the session (access re-checked). Returns
    ``(in_scope_targets, out_of_scope_names)`` — the second list lets the caller answer
    the in-scope people AND honestly name the ones it can't see (never their data). Empty
    unless a comparison connector is present."""
    if not re.search(r"\band\b|\bvs\b|\bversus\b|\bcompare|,", (query or ""), re.I):
        return [], []
    # Resolving "me"/"my"/"him" as a comparison SUBJECT only makes sense for a genuine
    # COMPARISON ("compare me with X", "how do I compare to X"). A plain "and" conjunction
    # ("what are my goals? and show me X's") is a mixed self+other request handled by the
    # single-person path (answer self + refuse the other) — leave it untouched here.
    is_comparison = bool(re.search(r"\bcompare|\bcompared\b|\bvs\.?\b|\bversus\b", query or "", re.I))
    targets, seen, oos_names = [], set(), []

    def _add_target(u):
        if u is not None and u.id not in seen:
            seen.add(u.id)
            targets.append(u)

    def _add_oos(name):
        if name and name not in oos_names:
            oos_names.append(name)

    for part in _COMPARE_SPLIT_RE.split(query or ""):
        if not part.strip():
            continue
        named, _amb, oos = _resolve_in_scope(caller, part)
        if named is not None:
            _add_target(named)
        elif hasattr(oos, "display"):
            _add_oos(oos.display)  # a real person, outside the caller's scope
        elif is_comparison and _SELF_SUBJECT_RE.search(part):
            _add_target(caller)  # "me"/"my"/"I" → the caller (always in own scope)
        elif is_comparison and session is not None and _DEIXIS_SUBJECT_RE.search(part):
            # "him"/"her"/"that person" → the last-discussed person, access RE-checked:
            # in scope → a subject; out of scope → named honestly, never their data.
            from apps.ai.sessions import last_referenced_person_any_scope

            prior = last_referenced_person_any_scope(caller, session)
            if prior is not None:
                _add_target(prior) if actor_can_access(caller, prior) else _add_oos(prior.display)
    return targets, oos_names


def _weakest_pct(facts) -> float | None:
    """Lowest measurable KPI attainment across a person's goals (None if none)."""
    worst = None
    for g in facts.get("goals", []):
        for k in g.get("kpis", []):
            pct = k.get("attainment_pct")
            if pct is None:
                continue
            if worst is None or pct < worst:
                worst = pct
    return worst


def _concern_score(facts) -> float:
    """A grounded 'needs attention' magnitude — higher = more concern. Built ONLY
    from real, in-scope facts (risk rating, pace, weakest KPI shortfall)."""
    s = 0.0
    if facts.get("risk_code") and facts["risk_code"] != "ON_TRACK":
        s += 100.0
    if facts.get("pace_behind"):
        s += 50.0
    weak = _weakest_pct(facts)
    if weak is not None:
        s += max(0.0, 100.0 - weak)
    return s


def _concern_reason(facts) -> str:
    bits = []
    if facts.get("risk_code") and facts["risk_code"] != "ON_TRACK":
        bits.append(f"rated {(facts.get('risk_status') or facts['risk_code']).lower()}")
    if facts.get("pace_behind"):
        bits.append("behind pace")
    weak = _weakest_pct(facts)
    if weak is not None and weak < 80:
        bits.append(f"weakest KPI at {weak:.0f}% of target")
    return (" — " + ", ".join(bits)) if bits else ""


def _and_join(names) -> str:
    names = list(names)
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def _answer_group_support(caller, people, query, intent="performance"):
    """"who needs more support / which one is worse?" over the people JUST discussed
    (§2 Example C). Each is diagnosed through the scoped path (access re-checked),
    then ranked by a grounded concern score — never a fresh name lookup, never the
    whole team. Read-only; no fabrication."""
    from apps.ai.insight import diagnose_person, llm_phrase

    scored = []
    for p in people[:4]:
        diag = diagnose_person(caller, p)  # scope re-checked inside person_facts
        if diag is not None:
            scored.append((_concern_score(diag["facts"]), p, diag))
    if not scored:
        return {"status": "ok", "intent": intent, "data": [],
                "answer": "I couldn't pull those people up in your scope."}
    scored.sort(key=lambda t: t[0], reverse=True)
    names = [p.display for _, p, _ in scored]
    top_score, top_p, top_diag = scored[0]
    others = [p.display for _, p, _ in scored[1:]]
    if top_score <= 0:
        draft = (f"Between {_and_join(names)}, none stands out as needing extra support "
                 "right now — they're on track and keeping pace.")
    else:
        tail = (f" {_and_join(others)} {'looks' if len(others) == 1 else 'look'} steadier "
                "by comparison." if others else "")
        draft = (f"{top_p.display} needs the most attention right now"
                 f"{_concern_reason(top_diag['facts'])}.{tail}")
    facts = {"people": [d["facts"] for _, _, d in scored]}
    answer = llm_phrase(caller.tenant_id, query, facts, draft)
    return {
        "status": "ok", "intent": intent, "answer": answer, "data": names,
        "refs": [{"type": "user", "id": str(p.id), "label": p.display}
                 for _, p, _ in scored],
    }


def _answer_two_people(caller, query, targets, intent="performance", oos_names=()):
    """A per-person reasoned reply for a comparison. Each in-scope person is diagnosed
    independently (already scoped via ``_resolve_multiple``); read-only, grounded, no
    fabrication. Any ``oos_names`` are named honestly as out-of-access — never their
    data. The optional LLM phrasing gets ONLY the in-scope people's facts."""
    from apps.ai.insight import diagnose_person, llm_phrase

    # A COUNT comparison ("how many goals/reviews do X and Y have?") gets precise
    # per-person counts, not a diagnosis — and is NOT LLM-phrased (numbers stay exact).
    is_count = bool(_COUNT_Q_RE.search(query or ""))
    drafts, facts, names = [], [], []
    for t in targets[:3]:
        if is_count:
            drafts.append(_answer_counts(caller, t, query, intent)["answer"])
            names.append(t.display)
            continue
        diag = diagnose_person(caller, t)
        if diag is None:  # defensive — resolver already scoped
            continue
        drafts.append(diag["answer"])
        facts.append(diag["facts"])
        names.append(t.display)
    if not drafts and not oos_names:
        return {"status": "ok", "intent": intent, "data": [], _UNANSWERED: True,
                "answer": "I couldn't pull those people up in your scope."}
    if is_count:
        answer = " ".join(drafts)
    else:
        answer = llm_phrase(caller.tenant_id, query, {"people": facts}, " ".join(drafts)) if drafts else ""
    if oos_names:
        who = " and ".join(oos_names[:3])
        note = (f"I can't share {who}'s performance — they're outside your access."
                if not answer else
                f" I can't share {who}'s though — they're outside your access.")
        answer = (answer + note).strip()
    return {
        "status": "ok", "intent": intent, "answer": answer, "data": names,
        "refs": [{"type": "user", "id": str(t.id), "label": t.display} for t in targets[:3]],
    }


def _latest_score(target):
    """The target's latest CycleScore (for grounding the answer). The caller's
    access to ``target`` is already gated by ``_scoped_goal_titles`` upstream, so
    this only runs for an in-scope subject. Tenant-scoped."""
    from apps.goals.models import CycleScore

    return CycleScore.objects.filter(employee_id=target.id).order_by("-computed_at").first()


def chat_answer(caller, query: str, session=None) -> dict:
    """Answer ``query`` for ``caller`` — the pre-coded paths first, then the agent.

    AGENT_V3/C. :func:`_deterministic_answer` below is the whole assistant as it was:
    the conversation state machine, the approval-gated write plans, scoped person and
    team reads. It keeps priority, because it is proven and because a state machine that
    sometimes yields to a model is not a state machine.

    What it *cannot* do is answer a question nobody pre-coded — "who improved most since
    last cycle", "who's ready for promotion". Those fall out of it as a non-answer today:
    the capability blurb, or a name lookup for words that were never a name. So exactly
    those turns go to the function-calling agent, which composes the scoped read tools.

    The agent's reply is used **only when it is tool-grounded**. A turn where the model
    called no tool has no scoped data behind it — whatever it wrote is its own prose, and
    prose is what this system exists to not show people. That one rule is also why small
    talk still gets the deterministic redirect: there is nothing for the tools to fetch.
    """
    out = _deterministic_answer(caller, query, session=session)
    if not out.pop(_UNANSWERED, False):
        return out
    return _agent_answer(caller, query, session) or out


def _agent_answer(caller, query: str, session) -> dict | None:
    """Hand an unanswered question to the scoped function-calling agent.

    Returns ``None`` whenever there is nothing trustworthy to say — no tool was called,
    the provider failed, the budget is gone — and the caller then falls back to the
    deterministic reply. Failure here must never be worse than not having tried.
    """
    from apps.ai.agent_loop import run_agent

    try:
        run = run_agent(caller, query, history=_history_for_agent(session, query))
    except Exception:  # a tool bug must not take the whole chat turn down
        logger.exception("chat: the agent fallback raised")
        return None
    if not run.ok or not run.used_a_tool or not run.answer.strip():
        return None
    refs = _agent_refs(run)
    return {
        "status": "ok",
        "intent": "performance",
        "answer": run.answer.strip(),
        "data": [r["label"] for r in refs],
        # The evidence for the answer. `tools` is the composition, and rides out to the
        # client. `evidence` is every tool RESULT, and does not: the HTTP layer drops it
        # (`ChatView`). It exists so the eval harness can check the hard property — that
        # every number in the answer had a tool result to come from — against the real
        # product path rather than against a second, parallel run of the agent that
        # might not have done the same thing.
        "tools": run.tool_names,
        "evidence": run.tool_calls,
        "refs": refs,
    }


def _history_for_agent(session, query: str, limit=6):
    """Recent turns as ``{role, text}``, minus the question being asked right now."""
    if session is None:
        return []
    from apps.ai.sessions import recent_turns

    turns = list(recent_turns(session, limit + 1))
    if turns and turns[-1].role == "user" and (turns[-1].text or "").strip() == (query or "").strip():
        turns = turns[:-1]
    return [{"role": t.role, "text": t.text} for t in turns[-limit:]]


#: Tool-result keys that hold lists of people. Grounding whoever the answer was about
#: keeps the existing reference resolution working across the agent ("and her reviews?").
_PEOPLE_KEYS = ("ranked", "members", "people")


def _agent_refs(run, limit=5):
    """The people this answer was about, as session refs.

    Access is re-checked wherever a ref is later *used* (``sessions._reaccess``), so a
    ref grants nothing — it only keeps a pronoun pointing at the right person, including
    when that person is one the caller was refused.
    """
    refs, seen = [], set()

    def add(row):
        pid, name = row.get("person_id"), row.get("name")
        if not pid or not name or pid in seen:
            return
        seen.add(pid)
        refs.append({"type": "user", "id": str(pid), "label": name})

    for call in run.tool_calls:
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        add(result)
        for key in _PEOPLE_KEYS:
            for row in (result.get(key) or [])[:limit]:
                if isinstance(row, dict):
                    add(row)
    return refs[:limit]


def _deterministic_answer(caller, query: str, session=None) -> dict:
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
    # AGENT_REBUILD/B — the conversation STATE MACHINE runs FIRST, before any LLM
    # call. Answering a pending question, cancelling, repeating the last action, and
    # plainly imperative commands are facts we already hold (session state + the
    # action registry), so they must not depend on how the model happens to classify
    # a bare "5". Letting the classifier decide those was the cause of the stuck
    # follow-up loop and of commands landing in the wrong task. It returns None for
    # everything else — open questions still go to the model, unchanged.
    from apps.ai.conversation import route_turn

    routed = route_turn(caller, query, session=session) if session is not None else None
    if routed is not None:
        return routed

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
    # "the first / second / other one" — a pick from the most recent disambiguation.
    # Checked pre-branch so the short follow-up works however it classifies; only
    # fires when an offered set actually exists (access re-checked in the session
    # helper), so a stray "the first goal" without a prior disambiguation is untouched.
    #
    # An EXPLICIT person / "go back to" reference ("the first PERSON", "go back to the
    # first") is a CONVERSATION-ORDER refer-back, not a pick from the just-shown list —
    # so yield to the order resolver below when `_operson` matches. (`_ORDINAL_PERSON_RE`
    # matches only "…first/second/last person" and "go back to the first/…", never bare
    # "the first one" / "the other one", so the offered-set path is otherwise untouched.)
    _operson = _ORDINAL_PERSON_RE.search(query or "")
    _ord = _ORDINAL_ONE_RE.search(query or "")
    if _ord and not _operson and session is not None:
        from apps.ai.sessions import last_offered_people

        offered = last_offered_people(caller, session)
        if offered:
            word = next((g for g in _ord.groups() if g), "first").lower()
            idx = len(offered) - 1 if word == "last" else _ORDINAL_INDEX.get(word, 0)
            picked = offered[min(max(idx, 0), len(offered) - 1)]
            from apps.ai.insight import diagnose_person, llm_phrase

            diag = diagnose_person(caller, picked)
            if diag is not None:
                answer = llm_phrase(caller.tenant_id, query, diag["facts"], diag["answer"])
                return {
                    "status": "ok", "intent": "performance", "answer": answer,
                    "data": [g["title"] for g in diag["facts"]["goals"]],
                    "refs": [{"type": "user", "id": str(picked.id), "label": picked.display}],
                }

    # "the first/second person (we discussed)" / "go back to the first one" — a pick
    # by CONVERSATION ORDER, for topic-switch refer-back ("how is Akhil?" … "how is
    # Mei?" … "and the first person again?"). Distinct people in first-mention order;
    # access re-checked in the session helper. Checked AFTER the offered-set ordinal
    # above, so a disambiguation "the first one" still wins when a set was just shown.
    if _operson and session is not None:
        from apps.ai.sessions import people_in_order

        ordered = people_in_order(caller, session)
        if ordered:
            word = next((g for g in _operson.groups() if g), "first").lower()
            idx = len(ordered) - 1 if word == "last" else _ORDINAL_INDEX.get(word, 0)
            picked = ordered[min(max(idx, 0), len(ordered) - 1)]
            from apps.ai.insight import diagnose_person, llm_phrase

            diag = diagnose_person(caller, picked)
            if diag is not None:
                answer = llm_phrase(caller.tenant_id, query, diag["facts"], diag["answer"])
                return {
                    "status": "ok", "intent": "performance", "answer": answer,
                    "data": [g["title"] for g in diag["facts"]["goals"]],
                    "refs": [{"type": "user", "id": str(picked.id), "label": picked.display}],
                }

    # "who needs more support / which one is worse?" after ≥2 people were just
    # discussed or compared → reason over THAT set (§2 Example C), not a fresh name
    # lookup and not the whole team. Only fires when a recent multi-person set
    # exists (access re-checked in the session helper) and the phrasing isn't
    # team-wide ("…on my team" stays with the team-scan path below).
    if (session is not None and _GROUP_SUPPORT_RE.search(query or "")
            and not _GROUP_TEAMWORD_RE.search(query or "")):
        from apps.ai.sessions import last_offered_people

        discussed = last_offered_people(caller, session)
        if len(discussed) >= 2:
            return _answer_group_support(caller, discussed, query)

    # TEAM insight ("who's behind / at risk / doing best on my team?", "how many
    # of my reports are behind?") — reasoned over the caller's OWN reporting
    # subtree, gated by VIEW_TEAM_SCORES. Checked ahead of search/performance so
    # it isn't mis-routed to the goal-name search or a single-person lookup.
    _tq = query or ""
    _is_compare = bool(_COMPARE_RE.search(_tq))
    _is_agg = bool(_AGG_RE.search(_tq))
    _is_scan = bool(_TEAM_SCAN_RE.search(_tq))
    # Yields to `search`: "who on my team is missing goals?" is a supported, scope-bound
    # NL search, and it also says "my team". The search branch below owns it — and when
    # the search comes back unmapped, THAT reply is marked for the agent instead.
    _is_team_open = bool(_TEAM_SUBJECT_RE.search(_tq)) and intent != "search"
    if _is_compare or _is_agg or _is_scan or _is_team_open:
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
        if _is_scan:
            # A scan: pick the mode from the phrasing.
            low = _tq.lower()
            mode = "at_risk" if ("at risk" in low and "behind" not in low) else (
                "behind" if "behind" in low else "all")
            # "the OTHER engineer who's behind" / "who ELSE is behind?" → drop the
            # person just discussed so it reads as "aside from them, …".
            exclude = None
            if session is not None and re.search(r"\b(other|else|another)\b", low):
                from apps.ai.sessions import last_referenced_person_any_scope

                exclude = last_referenced_person_any_scope(caller, session)
            return _answer_team_risk(caller, mode=mode, exclude=exclude)
        # A question about the caller's TEAM in a shape none of the three above match
        # ("compare my two weakest performers"). It must not fall through to the
        # single-person path below, where the "my" reads as self-reference and the
        # reply comes back about the CALLER's own goals — a confidently wrong answer
        # is worse than a missing one. Marked, so the agent composes it instead.
        return {
            "status": "ok", "intent": "performance", "data": [], _UNANSWERED: True,
            "answer": "I couldn't work that one out across your team — try “who's "
                      "behind?”, “who's doing best?”, or name the person.",
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
        demoted_search = True
    else:
        demoted_search = False
    if intent == "capability":
        return {"status": "ok", "intent": "capability",
                "answer": _capability_answer(caller), "data": []}
    if intent not in ("performance", "read"):  # "read" = legacy alias for performance
        # AGENT_REBUILD/C §3 — the capability blurb is for "what can you do?" and for
        # a genuinely unparseable message. It must NEVER be the answer to a real
        # question. The classifier sometimes labels an answerable performance question
        # `general`, and the user then gets a leaflet instead of their data. So before
        # deflecting, check DETERMINISTICALLY whether this is answerable; if it is,
        # send it down the performance path, which applies the same scope gate and
        # gives the same honest refusal it always would.
        if not demoted_search and _is_answerable_data_question(caller, query):
            intent = "performance"
        else:
            # General / conversational / out-of-domain ("what day is today?", "I feel
            # lonely"). Decline politely + redirect — NEVER a performance-metrics dump.
            #
            # AGENT_V3/C — but this is also where an open-ended question we never coded
            # a path for lands ("who improved most since last cycle?"). Marked, so the
            # function-calling agent gets a turn at it; if the agent calls no tool —
            # which is what small talk produces — this redirect is still the answer.
            return {"status": "ok", "intent": "general", "answer": _GENERAL_ANSWER,
                    "data": [], _UNANSWERED: True}

    # PERFORMANCE intent. Resolve a target person: an explicit email → a remembered
    # person from THIS conversation ("she", "her" — session refs, access re-checked)
    # → a person NAMED in the query (unique tenant match). The fetch is ALWAYS
    # scope-checked, so memory/names can never surface out-of-scope data (C2).
    from apps.identity.models import User

    # TWO-OR-MORE named people ("how are Akhil and Mei doing?", "compare X and Y") →
    # a per-person reasoned reply, each resolved + scope-checked INDEPENDENTLY. Only
    # fires when ≥2 DISTINCT in-scope people resolve, so "goals and KPIs" is untouched
    # and an out-of-scope name simply isn't included (never a leak).
    _multi, _oos_names = _resolve_multiple(caller, query, session)
    if len(_multi) >= 2 or (_multi and _oos_names):
        return _answer_two_people(caller, query, _multi, intent, oos_names=_oos_names)

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
        # §2 Example A: a purely first-person message ("what are my goals", "how
        # am I doing", "my own KPIs") is about the CURRENT USER — resolve to self,
        # never a name lookup. This must win over the fragile `typed_a_name`
        # heuristic (a stray domain word like "own" must not force a not-found).
        is_self_ref = bool(_SELF_REF_RE.search(query or ""))
        if named is not None:
            target = named
        elif ambiguous:  # a list of candidate User objects (offered order)
            labels = _disambiguation_labels(ambiguous)
            return {
                "status": "ok", "intent": intent, "data": labels,
                "answer": f"Several people match that name: {', '.join(labels)}. "
                          "Tell me which one — you can say “the first one” or use "
                          "their email.",
                # Ground the offered people so a follow-up ("the first/other one")
                # can resolve them — access is STILL re-checked on use.
                "refs": [{"type": "user", "id": str(u.id), "label": u.display}
                         for u in _dedup_sorted_users(ambiguous)],
            }
        elif isinstance(out_of_scope, User):
            # MIXED self+other ("what are my goals? and also show me X's"): when the
            # caller ALSO referred to their OWN data (possessive "my/mine"), answer the
            # self part AND refuse the out-of-scope person in one reply — never drop the
            # allowed half, never leak the other. (INTEL_V2 §7 mixed-scope.) Possessive-
            # only so "show me X's goals" ("me" as object) isn't taken as self-reference.
            if _SELF_MINE_RE.search(query or "") and not person_deixis:
                from apps.ai.insight import diagnose_person, llm_phrase

                self_diag = diagnose_person(caller, caller)
                if self_diag is not None:
                    self_ans = llm_phrase(caller.tenant_id, query,
                                          self_diag["facts"], self_diag["answer"])
                    refusal = _scope_denied_answer(
                        caller, intent, out_of_scope.display,
                        ground_user=out_of_scope)["answer"]
                    return {
                        "status": "ok", "intent": intent,
                        "answer": f"{self_ans}\n\nAs for {out_of_scope.display}: {refusal}",
                        "data": [g["title"] for g in self_diag["facts"]["goals"]],
                        # Ground the REFUSED person so a pronoun follow-up stays on them
                        # (and is refused again) — the ref grants nothing.
                        "refs": [{"type": "user", "id": str(out_of_scope.id),
                                  "label": out_of_scope.display}],
                    }
            # Named a real person OUTSIDE scope this turn — refuse honestly AND
            # ground them so a pronoun follow-up stays on them (never self).
            return _scope_denied_answer(caller, intent, out_of_scope.display,
                                        ground_user=out_of_scope)
        elif out_of_scope == "":
            # Several out-of-scope people match the name — generic honest refusal.
            return _scope_denied_answer(caller, intent, None)
        elif is_self_ref and not person_deixis:
            # First-person, no other person named and no 3rd-person pronoun →
            # the caller themselves (fixes "what are my own goals?" dead-ending
            # in a name lookup). A "show/list my goals" still flat-lists below.
            target = caller
        elif typed_a_name and not person_deixis:
            # A real 3rd-person pronoun ("his other goal") means COREFERENCE — it
            # must win over a stray non-name token ("other"), so only treat this as
            # a typed name when NO pronoun is present. Before giving up, try a
            # TYPO-tolerant suggestion within the caller's scope ("Akil Menon" →
            # "Did you mean Akhil Menon?"). Suggestions are
            # scope-limited, so this never reveals a name they couldn't already see.
            from apps.ai.insight import fuzzy_name_suggestions

            name_text = " ".join(
                w for w in re.findall(r"[a-zA-Z]{3,}", (query or "").lower())
                if w not in _NAME_STOP_WORDS and w not in _deictic
            )
            suggestions = fuzzy_name_suggestions(caller, name_text)
            if suggestions:
                opts = " or ".join(suggestions) if len(suggestions) <= 2 else (
                    ", ".join(suggestions[:-1]) + f", or {suggestions[-1]}")
                return {
                    "status": "ok", "intent": intent, "data": suggestions,
                    "answer": f"I couldn't find that exact name — did you mean {opts}?",
                }
            # Say WHICH name failed. "I couldn't find anyone by that name" leaves the
            # user guessing whether we misread them or they misremembered the person;
            # echoing their own words back settles it, and echoing the CALLER'S input
            # reveals nothing they didn't already type.
            #
            # Two deliberate limits. Only echo 1–3 tokens: more than that isn't one
            # name (a two-person comparison leaves four tokens), and reciting the
            # whole query back reads as nonsense. And never say "…in your company" —
            # this branch only knows the name didn't resolve *here*, so asserting the
            # person doesn't exist would be a claim we haven't checked.
            typed_words = name_text.split()
            typed = " ".join(w.capitalize() for w in typed_words) if 1 <= len(typed_words) <= 3 else ""
            #
            # Marked for the agent (AGENT_V3/C): "who's ready for promotion?" has no
            # name in it, but the heuristic above reads "ready promotion" as one and
            # dead-ends here. If the agent can compose an answer it should; if the user
            # really did mistype a name, find_people comes back empty and the honest
            # message below still stands.
            return {
                "status": "ok", "intent": intent, "data": [], _UNANSWERED: True,
                "answer": (f"I couldn't find anyone named {typed} — " if typed
                           else "I couldn't find anyone by that name — ")
                          + "try their full name or their email address.",
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
        return {"status": "ok", "intent": intent, "data": [], _UNANSWERED: True,
                "answer": "No matching person in your scope."}

    # "his/her/their OTHER goal" / "the first/second/last goal" — isolate ONE goal of
    # the resolved person (spec §0 Example B), never a list of all. "other" = the goals
    # other than the one the status diagnosis highlights (the weakest-KPI focus goal).
    # Scope re-checked inside diagnose_goal (person_facts); the person is grounded so a
    # further follow-up still holds.
    _goalord = _GOAL_ORDINAL_RE.search(query or "")
    if _goalord:
        from apps.ai.insight import diagnose_goal, llm_phrase

        which = _goalord.group(1).lower()
        which = _GOAL_ORDINAL_NORM.get(which, which)
        dg = diagnose_goal(caller, target, which=which)
        if dg is None:
            return _scope_denied_answer(caller, intent, target.display)
        answer = llm_phrase(caller.tenant_id, query, dg["facts"], dg["answer"])
        return {
            "status": "ok", "intent": intent, "answer": answer,
            "data": [g["title"] for g in dg["facts"]["goals"]],
            "refs": [{"type": "user", "id": str(target.id), "label": target.display}],
        }

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

    # STATUS + DIAGNOSIS — "how is X?", "does she need help?", "is X on track / at
    # risk / behind?" — get a REASONED answer grounded in real cycle status + KPI
    # attainment, phrased in natural language. Only an explicit "show/list my goals"
    # falls through to the raw title list below. Scope re-checked inside.
    if not _LIST_GOALS_RE.search(_q):
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
