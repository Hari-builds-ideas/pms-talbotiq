"""
The permission-scoped read-tool set the function-calling agent composes (AGENT_V3/A).

The model never writes SQL and never touches the database. It picks from a fixed set of
typed tools; this module runs the scoped ORM query and hands back structured rows. That
is the whole security model, and it rests on two properties:

**Scope is not an argument.** Every handler takes a :class:`ToolContext` built
server-side from the authenticated session. The model may name a ``person_id``, but it
can neither state nor influence *who is asking* — there is no caller field in any schema
for it to fill, and :func:`tool_schemas` is what the model sees. A tool asked about
somebody out of scope returns ``{"denied": true, …}``; it never returns the data and
never raises, because a denial is information the model must relay honestly.

**The backend does every calculation.** Ranking, counting, averaging and cycle deltas are
computed here, in Python, over rows the caller is allowed to see (:func:`rank_team`,
:func:`team_aggregate`, :func:`compute_improvement`). The model receives finished numbers
and phrases them. It is never asked to sort or add, because a model doing arithmetic on
returned rows is exactly how invented figures get into an answer.

Efficiency is a correctness property here, not a nicety: these run against tenants of
5,000+ people, so the team tools resolve every person's latest score in a **fixed number
of queries** rather than one per person, and every result set is bounded.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from apps.rbac.scope import actor_can_access, reporting_subtree_ids

logger = logging.getLogger("pms.ai.tools")

#: A first-person reference passed to :func:`find_people`. Anchored to the WHOLE query,
#: so a colleague genuinely called "Me" or "Self" is still looked up normally.
_SELF_QUERY_RE = re.compile(r"(?:me|myself|i|my ?self|the current user|the signed[- ]in user)",
                            re.I)

#: Hard ceiling on rows any single tool returns. The model pays for every row in context
#: and a manager with 400 reports must not blow the window — the aggregate tools exist
#: precisely so that "how many" never needs the whole list.
MAX_ROWS = 50

#: Ceiling on people a team-wide computation will scan. Above this the honest answer is
#: that the question is too broad for a chat turn, not a 30-second query.
MAX_TEAM_SCAN = 2000


@dataclass(frozen=True)
class ToolContext:
    """The trusted, server-side answer to "who is asking?".

    Built from the authenticated request — never from model output. Frozen so a handler
    cannot mutate the caller mid-turn.
    """

    caller: object

    @property
    def tenant_id(self):
        return self.caller.tenant_id


def _denied(reason="You don't have access to that person's data."):
    """A denial is DATA the model must relay, not an exception to swallow. Returning it
    in-band is what lets the agent say "that's outside what you can see" instead of
    either leaking or dying."""
    return {"denied": True, "reason": reason}


def _no_data(what="that"):
    return {"empty": True, "reason": f"There's no {what} recorded."}


def _person(ctx, person_id):
    """Load a person in the caller's tenant, or None. Tenant scoping comes from the
    default manager, so a cross-tenant id simply does not resolve.

    The id is validated as a UUID first. A model that has not called ``find_people``
    will cheerfully invent one — the live eval produced ``"jamal_whitfield_id"`` — and
    handing that to the ORM raises a ValidationError out of the middle of a tool call.
    An invented id is a fact about the request, so it comes back as "no such person"
    like any other miss.
    """
    from apps.identity.models import User

    if not person_id:
        return None
    try:
        uuid.UUID(str(person_id))
    except (ValueError, AttributeError, TypeError):
        return None
    return User.objects.filter(id=person_id).first()


def _readable(ctx, person_id):
    """(person, None) if the caller may read this person's DATA, else (None, denial).

    Resolving a name is company-wide; reading performance data is not. Every data tool
    goes through here so that check exists in exactly one place.
    """
    person = _person(ctx, person_id)
    if person is None:
        return None, _no_data("person by that id")
    if not actor_can_access(ctx.caller, person):
        return None, _denied()
    return person, None


# ── directory ────────────────────────────────────────────────────────────────────


def find_people(ctx, query: str, limit: int = 5):
    """Resolve a name COMPANY-WIDE via the one canonical resolver.

    Deliberately delegates rather than matching names itself: a second name matcher is
    how the data path and the directory drifted apart before (AGENT_REBUILD/D). Identity
    only — being findable grants nothing.
    """
    from apps.ai.directory import AMBIGUOUS, resolve_person_in_population, suggest_candidates

    # "me" is a person too. Every other tool takes a person_id, so without this the
    # agent has no way to ask about the signed-in user at all — "have I improved since
    # last cycle?" has no name in it to look up. Handled here rather than by giving the
    # model the caller's id in the prompt: an id it never sees is an id it cannot
    # substitute for somebody else's.
    if _SELF_QUERY_RE.fullmatch((query or "").strip()):
        return {"people": [_identity(ctx.caller)], "ambiguous": False}

    hit = resolve_person_in_population(ctx.caller, query or "", exclude_self=False)
    if hit is not None and hit is not AMBIGUOUS:
        return {"people": [_identity(hit)], "ambiguous": False}
    candidates = suggest_candidates(ctx.caller, query or "", exclude_self=False,
                                    limit=min(limit, MAX_ROWS))
    if not candidates:
        return {"people": [], "ambiguous": False,
                "reason": f"Nobody in the company matches {query!r}."}
    # Several real matches: hand back the list WITH emails so the user can settle it.
    return {"people": [_identity(u) for u in candidates], "ambiguous": True}


def _identity(user):
    """Directory-level identity only — never a performance field. This is what
    company-wide visibility means: you can find a colleague, not read their scores."""
    return {
        "person_id": str(user.id),
        "name": user.display,
        "email": user.email,
        "role": user.role,
    }


# ── one person ───────────────────────────────────────────────────────────────────


def get_person_overview(ctx, person_id: str):
    """Headline status for one person: risk band, pace, open reviews."""
    from apps.ai.insight import person_facts

    person, denial = _readable(ctx, person_id)
    if denial:
        return denial
    facts = person_facts(ctx.caller, person)
    if facts is None:
        return _denied()
    if not facts["has_score"]:
        return {"person_id": str(person.id), "name": facts["name"],
                "has_score": False,
                "reason": "No cycle score has been computed for this person yet.",
                "open_reviews": facts["review_open"]}
    return {
        "person_id": str(person.id),
        "name": facts["name"],
        "has_score": True,
        "risk_status": facts["risk_status"],
        "pace_behind": facts["pace_behind"],
        "goal_count": len(facts["goals"]),
        "open_reviews": facts["review_open"],
    }


def get_person_goals(ctx, person_id: str):
    """Active goals with their weights (KPI detail lives in get_person_kpis)."""
    from apps.ai.insight import person_facts

    person, denial = _readable(ctx, person_id)
    if denial:
        return denial
    facts = person_facts(ctx.caller, person)
    if facts is None:
        return _denied()
    goals = [{"title": g["title"], "weight": g["weight"], "kpi_count": len(g["kpis"])}
             for g in facts["goals"][:MAX_ROWS]]
    if not goals:
        return _no_data("active goal")
    return {"person_id": str(person.id), "name": facts["name"], "goals": goals}


def get_person_kpis(ctx, person_id: str):
    """Every KPI with target, unit and the BACKEND-computed attainment percentage.

    Attainment is computed in :mod:`apps.ai.insight`, not by the model — it is a ratio
    with a direction (some KPIs are better when lower), which is precisely the sort of
    arithmetic that comes back subtly wrong when a language model does it.
    """
    from apps.ai.insight import person_facts

    person, denial = _readable(ctx, person_id)
    if denial:
        return denial
    facts = person_facts(ctx.caller, person)
    if facts is None:
        return _denied()
    kpis = []
    for goal in facts["goals"]:
        for kpi in goal["kpis"]:
            kpis.append({
                "goal": goal["title"],
                "name": kpi["name"],
                "target": kpi["target"],
                "unit": kpi["unit"],
                "direction": kpi["direction"],
                "attainment_pct": kpi["attainment_pct"],
            })
            if len(kpis) >= MAX_ROWS:
                break
    if not kpis:
        return _no_data("KPI")
    return {"person_id": str(person.id), "name": facts["name"], "kpis": kpis}


def get_person_reviews(ctx, person_id: str):
    """Review STATE only — never the private body text. What the agent needs to say
    "they have an open review" is the state; the prose is not its business."""
    from apps.reviews.models import Review

    person, denial = _readable(ctx, person_id)
    if denial:
        return denial
    rows = list(Review.objects.filter(employee_id=person.id)
                .select_related("cycle").order_by("-created_at")[:MAX_ROWS])
    if not rows:
        return _no_data("review")
    return {
        "person_id": str(person.id),
        "name": person.display,
        "reviews": [{"state": r.state, "cycle": r.cycle.name if r.cycle_id else None,
                     "is_final": r.state == "FINALIZED"} for r in rows],
        "open_count": sum(1 for r in rows if r.state != "FINALIZED"),
    }


def get_cycle_scores(ctx, person_id: str, limit: int = 6):
    """One person's scores across cycles, newest first — the raw material for
    "did they improve?". The DELTA itself is computed by :func:`compute_improvement`."""
    from apps.goals.models import CycleScore

    person, denial = _readable(ctx, person_id)
    if denial:
        return denial
    rows = list(CycleScore.objects.filter(employee_id=person.id)
                .select_related("cycle").order_by("-computed_at")[:min(limit, MAX_ROWS)])
    if not rows:
        return _no_data("cycle score")
    return {
        "person_id": str(person.id),
        "name": person.display,
        "scores": [{
            "cycle": s.cycle.name if s.cycle_id else None,
            "t_score": round(float(s.t_score), 1),
            "risk_status": s.get_risk_status_display(),
            "pace_behind": bool(s.pace_behind),
        } for s in rows],
    }


def get_feedback_summary(ctx, person_id: str):
    """360 cycle STATE for a person — not the anonymised feedback content, which has its
    own anonymity rules and does not belong in a chat turn."""
    from apps.feedback.models import FeedbackCycle

    person, denial = _readable(ctx, person_id)
    if denial:
        return denial
    rows = list(FeedbackCycle.objects.filter(subject_id=person.id)
                .order_by("-created_at")[:MAX_ROWS])
    if not rows:
        return _no_data("360 feedback cycle")
    return {
        "person_id": str(person.id),
        "name": person.display,
        "cycles": [{"status": c.get_status_display()} for c in rows],
        "open_count": sum(1 for c in rows if c.status != "CLOSED"),
    }


def list_check_ins(ctx, person_id: str = None, limit: int = 8):
    """Recent check-in moods. Defaults to the caller's own, which is the common case
    ("how have I been?") and needs no scope widening."""
    from apps.checkins.models import CheckIn

    target_id = person_id or str(ctx.caller.id)
    person, denial = _readable(ctx, target_id)
    if denial:
        return denial
    rows = list(CheckIn.objects.filter(author_id=person.id)
                .order_by("-week_of")[:min(limit, MAX_ROWS)])
    if not rows:
        return _no_data("check-in")
    return {
        "person_id": str(person.id),
        "name": person.display,
        "check_ins": [{"week_of": c.week_of.isoformat(), "mood": c.mood} for c in rows],
    }


# ── the caller's team ────────────────────────────────────────────────────────────


def _scored_subtree(ctx):
    """(user, latest CycleScore|None) for the caller's reporting subtree, in a FIXED
    number of queries.

    ``insight._subtree_latest_scores`` issues one score query per person, which is fine
    for a five-person fixture and quadratic-feeling at 5,000. Two queries here: the
    people, then every score for those people newest-first, keeping the first seen per
    employee. Bounded by MAX_TEAM_SCAN so one enormous org chart cannot stall a turn.
    """
    from apps.goals.models import CycleScore
    from apps.identity.models import User

    ids = reporting_subtree_ids(ctx.caller) - {ctx.caller.id}
    if not ids:
        return [], False
    truncated = len(ids) > MAX_TEAM_SCAN
    ids = list(ids)[:MAX_TEAM_SCAN]
    people = list(User.objects.filter(id__in=ids))
    latest = {}
    for score in (CycleScore.objects.filter(employee_id__in=ids)
                  .only("employee_id", "t_score", "risk_status", "pace_behind", "computed_at")
                  .order_by("-computed_at")):
        latest.setdefault(score.employee_id, score)
    return [(u, latest.get(u.id)) for u in people], truncated


def get_my_team(ctx):
    """Who the caller manages, with each person's headline status."""
    rows, truncated = _scored_subtree(ctx)
    if not rows:
        return {"manages": False, "reason": "You don't have any reports."}
    members = [{
        "person_id": str(u.id),
        "name": u.display,
        "has_score": s is not None,
        "risk_status": s.get_risk_status_display() if s else None,
        "pace_behind": bool(s.pace_behind) if s else None,
    } for u, s in rows[:MAX_ROWS]]
    return {"manages": True, "team_size": len(rows), "members": members,
            "listed": len(members), "truncated": truncated or len(rows) > MAX_ROWS}


#: Metrics the ranking tool understands. Named rather than free-form so the model cannot
#: ask for an expression we would then have to evaluate — that would be text-to-SQL by
#: another route.
RANK_METRICS = ("score", "attainment", "pace", "improvement")

_AGGREGATES = ("count_at_risk", "count_behind_pace", "count_on_track",
               "average_score", "team_size")


def rank_team(ctx, metric: str = "score", order: str = "desc", limit: int = 5,
              from_cycle: str = None, to_cycle: str = None):
    """Rank the caller's team by a named metric. **The backend sorts.**

    The model asks for "worst three by score" and receives them already ordered with the
    numbers attached. It is never handed a pile of rows to sort, because that is both
    error-prone and unverifiable after the fact.
    """
    if metric not in RANK_METRICS:
        return {"error": f"Unknown metric {metric!r}. Use one of: {', '.join(RANK_METRICS)}."}
    if metric == "improvement":
        return compute_improvement(ctx, from_cycle=from_cycle, to_cycle=to_cycle,
                                   limit=limit, order=order)

    rows, truncated = _scored_subtree(ctx)
    if not rows:
        return {"manages": False, "reason": "You don't have any reports."}
    scored = [(u, s) for u, s in rows if s is not None]
    if not scored:
        return _no_data("scored person on your team")

    if metric == "score":
        keyed = [(float(s.t_score), u, s) for u, s in scored]
    elif metric == "attainment":
        keyed = [(_mean_attainment(ctx, u), u, s) for u, s in scored]
        keyed = [(v, u, s) for v, u, s in keyed if v is not None]
        if not keyed:
            return _no_data("KPI attainment for your team")
    else:  # pace — behind-pace people first when ascending
        keyed = [(0.0 if s.pace_behind else 1.0, u, s) for u, s in scored]

    keyed.sort(key=lambda k: k[0], reverse=(order != "asc"))
    return {
        "manages": True, "metric": metric, "order": order,
        "team_size": len(rows), "truncated": truncated,
        "ranked": [{
            "person_id": str(u.id),
            "name": u.display,
            "value": round(v, 1),
            "risk_status": s.get_risk_status_display(),
            "pace_behind": bool(s.pace_behind),
        } for v, u, s in keyed[:min(limit, MAX_ROWS)]],
    }


def _mean_attainment(ctx, user):
    """Mean KPI attainment for one person, or None when they have no measured KPI."""
    from apps.ai.insight import person_facts

    facts = person_facts(ctx.caller, user)
    if facts is None:
        return None
    values = [k["attainment_pct"] for g in facts["goals"] for k in g["kpis"]
              if k["attainment_pct"] is not None]
    return sum(values) / len(values) if values else None


def team_aggregate(ctx, metric: str = "count_at_risk"):
    """Exact counts and averages over the caller's team, computed here.

    "How many of my reports are behind pace" must be a number the database supports, not
    a model's tally of a list it was shown. The distinction only becomes visible at size,
    which is when it also starts being wrong.
    """
    if metric not in _AGGREGATES:
        return {"error": f"Unknown metric {metric!r}. Use one of: {', '.join(_AGGREGATES)}."}
    rows, truncated = _scored_subtree(ctx)
    if not rows:
        return {"manages": False, "reason": "You don't have any reports."}
    scored = [s for _, s in rows if s is not None]
    if metric == "team_size":
        value = len(rows)
    elif not scored:
        return _no_data("scored person on your team")
    elif metric == "count_at_risk":
        value = sum(1 for s in scored if s.risk_status != "ON_TRACK")
    elif metric == "count_behind_pace":
        value = sum(1 for s in scored if s.pace_behind)
    elif metric == "count_on_track":
        value = sum(1 for s in scored if s.risk_status == "ON_TRACK" and not s.pace_behind)
    else:  # average_score
        value = round(sum(float(s.t_score) for s in scored) / len(scored), 1)
    return {"manages": True, "metric": metric, "value": value,
            "team_size": len(rows), "scored": len(scored), "truncated": truncated}


def compute_improvement(ctx, person_id: str = None, from_cycle: str = None,
                        to_cycle: str = None, limit: int = 5, order: str = "desc"):
    """Cycle-over-cycle deltas, computed in the backend, for one person or the team.

    "Who improved most since last cycle" is a subtraction over pairs of scores followed
    by a sort. Both happen here. Without named cycles the two most recent scores per
    person are used, which is what "since last cycle" means in practice.
    """
    from apps.goals.models import CycleScore

    if person_id:
        person, denial = _readable(ctx, person_id)
        if denial:
            return denial
        delta = _delta_for(person.id, from_cycle, to_cycle)
        if delta is None:
            return _no_data("pair of cycle scores to compare for this person")
        return {"person_id": str(person.id), "name": person.display, **delta}

    rows, truncated = _scored_subtree(ctx)
    if not rows:
        return {"manages": False, "reason": "You don't have any reports."}
    ids = [u.id for u, _ in rows]

    # Every score for the whole team in ONE query, then paired per person in Python.
    by_person: dict = {}
    for score in (CycleScore.objects.filter(employee_id__in=ids)
                  .select_related("cycle").order_by("-computed_at")):
        by_person.setdefault(score.employee_id, []).append(score)

    names = {u.id: u.display for u, _ in rows}
    improved = []
    for pid, scores in by_person.items():
        delta = _pair_delta(scores, from_cycle, to_cycle)
        if delta is not None:
            improved.append({"person_id": str(pid), "name": names.get(pid), **delta})
    if not improved:
        return _no_data("person with two comparable cycle scores on your team")
    improved.sort(key=lambda d: d["delta"], reverse=(order != "asc"))
    return {"manages": True, "metric": "improvement", "order": order,
            "compared": len(improved), "team_size": len(rows), "truncated": truncated,
            "ranked": improved[:min(limit, MAX_ROWS)]}


def _delta_for(person_id, from_cycle, to_cycle):
    from apps.goals.models import CycleScore

    scores = list(CycleScore.objects.filter(employee_id=person_id)
                  .select_related("cycle").order_by("-computed_at")[:MAX_ROWS])
    return _pair_delta(scores, from_cycle, to_cycle)


def _pair_delta(scores, from_cycle, to_cycle):
    """The (earlier, later) pair to compare, and the delta between them.

    Named cycles win when given; otherwise the two most recent. Returns None when there
    is no pair — a person with a single score has not "improved", and saying they did by
    comparing a score with nothing is exactly the fabrication this is built to avoid.
    """
    if len(scores) < 2:
        return None
    later = earlier = None
    if to_cycle or from_cycle:
        for s in scores:
            name = s.cycle.name if s.cycle_id else None
            if to_cycle and name == to_cycle and later is None:
                later = s
            if from_cycle and name == from_cycle and earlier is None:
                earlier = s
        if later is None or earlier is None:
            return None
    else:
        later, earlier = scores[0], scores[1]
    delta = round(float(later.t_score) - float(earlier.t_score), 1)
    return {
        "from_cycle": earlier.cycle.name if earlier.cycle_id else None,
        "to_cycle": later.cycle.name if later.cycle_id else None,
        "from_score": round(float(earlier.t_score), 1),
        "to_score": round(float(later.t_score), 1),
        "delta": delta,
        "direction": "improved" if delta > 0 else ("declined" if delta < 0 else "unchanged"),
    }


# ── the registry the agent loop and the model both read ──────────────────────────


def _schema(name, description, properties=None, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": list(required),
            },
        },
    }


_PERSON_ARG = {"person_id": {"type": "string",
                             "description": "id from find_people — never a name"}}

#: name → (handler, schema). ONE registry, so the schemas the model sees and the
#: handlers we run can never disagree about what exists.
TOOLS = {
    "find_people": (find_people, _schema(
        "find_people",
        "Resolve a person's name to their id, company-wide. Use this FIRST whenever the "
        "user names somebody. Pass \"me\" to get the signed-in user's own id, which is "
        "what questions like \"have I improved?\" need. Finding a person does not grant "
        "access to their data.",
        {"query": {"type": "string", "description": "the name or email as the user wrote it"}},
        ["query"])),
    "get_person_overview": (get_person_overview, _schema(
        "get_person_overview",
        "Headline status for one person: risk band, whether they are behind pace, and "
        "how many reviews are open.", _PERSON_ARG, ["person_id"])),
    "get_person_goals": (get_person_goals, _schema(
        "get_person_goals", "One person's active goals and their weights.",
        _PERSON_ARG, ["person_id"])),
    "get_person_kpis": (get_person_kpis, _schema(
        "get_person_kpis",
        "One person's KPIs with target, unit and the computed attainment percentage.",
        _PERSON_ARG, ["person_id"])),
    "get_person_reviews": (get_person_reviews, _schema(
        "get_person_reviews", "The state of one person's reviews (never the review text).",
        _PERSON_ARG, ["person_id"])),
    "get_cycle_scores": (get_cycle_scores, _schema(
        "get_cycle_scores",
        "One person's scores across cycles, newest first. To compare two cycles use "
        "compute_improvement instead of subtracting these yourself.",
        {**_PERSON_ARG, "limit": {"type": "integer", "description": "how many cycles"}},
        ["person_id"])),
    "get_feedback_summary": (get_feedback_summary, _schema(
        "get_feedback_summary", "The state of one person's 360 feedback cycles.",
        _PERSON_ARG, ["person_id"])),
    "list_check_ins": (list_check_ins, _schema(
        "list_check_ins",
        "Recent weekly check-in moods. Omit person_id for the caller's own.",
        {**_PERSON_ARG, "limit": {"type": "integer"}})),
    "get_my_team": (get_my_team, _schema(
        "get_my_team",
        "Everyone the caller manages, with each person's headline status. Use this to "
        "find out who 'my team' or 'my reports' refers to.")),
    "rank_team": (rank_team, _schema(
        "rank_team",
        "Rank the caller's team by a metric. The BACKEND sorts and returns the numbers — "
        "use this instead of ordering rows yourself.",
        {"metric": {"type": "string", "enum": list(RANK_METRICS)},
         "order": {"type": "string", "enum": ["asc", "desc"],
                   "description": "desc = best first; asc = worst first"},
         "limit": {"type": "integer"}},
        ["metric"])),
    "team_aggregate": (team_aggregate, _schema(
        "team_aggregate",
        "An exact count or average over the caller's team, computed by the backend. Use "
        "this for any 'how many' or 'average' question — never count rows yourself.",
        {"metric": {"type": "string", "enum": list(_AGGREGATES)}},
        ["metric"])),
    "compute_improvement": (compute_improvement, _schema(
        "compute_improvement",
        "Cycle-over-cycle score deltas computed by the backend, for one person "
        "(person_id) or ranked across the whole team (omit person_id). Use this for any "
        "'improved', 'got better', 'declined' or 'trending' question.",
        {**_PERSON_ARG,
         "from_cycle": {"type": "string", "description": "optional cycle name"},
         "to_cycle": {"type": "string", "description": "optional cycle name"},
         "order": {"type": "string", "enum": ["asc", "desc"]},
         "limit": {"type": "integer"}})),
}


def tool_schemas():
    """The function-calling schemas, exactly as the model sees them.

    Note what is absent: no caller, tenant, or role argument anywhere. The model cannot
    express "as somebody else" because the vocabulary does not contain it.
    """
    return [schema for _, schema in TOOLS.values()]


def run_tool(ctx, name, arguments):
    """Execute one tool call. Never raises: an unknown tool, a bad argument or a failing
    query all come back as structured results, because the agent loop has to hand
    *something* back to the model and a traceback is not an answer."""
    entry = TOOLS.get(name)
    if entry is None:
        return {"error": f"No such tool {name!r}."}
    handler, _ = entry
    kwargs = {k: v for k, v in (arguments or {}).items() if k != "ctx"}
    try:
        return handler(ctx, **kwargs)
    except TypeError as exc:  # the model invented or omitted an argument
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        # A malformed value the ORM rejects, a query that fails — the loop still has to
        # hand the model something, and a traceback is not an answer. Logged loudly,
        # because a tool that keeps erroring is a bug even when the turn survives it.
        logger.exception("tool %s failed", name)
        return {"error": f"{name} could not be completed: {type(exc).__name__}"}
