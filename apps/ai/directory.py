"""
Directory resolution (name → person) — DELIBERATELY SEPARATE from data access.

This module answers one question: *which person did the user name?* It searches a
POPULATION of users and returns the person, :data:`AMBIGUOUS`, or ``None``. It never
reads, returns, or grants access to anyone's performance data — resolving a name is
not permission to see their goals/reviews/scores. Callers choose the population:

  * DIRECTORY-only actions (recognition, feedback-cycle invites, 1:1s) search the
    WHOLE TENANT — you may legitimately recognise a colleague on another team — so
    they pass ``population_ids=None`` (all active users in the caller's tenant, which
    the tenant-scoped manager already bounds: a cross-tenant name never resolves).
  * DATA actions ("how is X", draft a review, approve a goal) pass the caller's
    VISIBLE id set as ``population_ids`` AND still run the existing access check
    before any data is read. Directory resolution here only narrows *who was named*.

Ranking is TIERED so an exact full-name match wins outright and never disambiguates,
even when many people share a first name (the "Priya Nair" bug — 7 people named
"Priya *" must not drown out the one exact "Priya Nair"):

  1. exact full name (case-insensitive)          → 1 hit wins; ≥2 real "same name" ask
  2. all query name-tokens present in the name    → "priya nair" ⊆ "Priya Nair"
  3. one distinctive token (first OR last name)   → "mateo" → Mateo Santos
  4. fuzzy full-name (typo tolerance, bounded)    → "akil menonn" → Akhil Menon

The FIRST tier that yields hits decides. A tier with exactly one hit resolves; a tier
with several genuine hits returns :data:`AMBIGUOUS` (the chat then lists them with
emails). Queries are indexed (exact/prefix on ``display_name``) and every scan is
CAPPED — we never load the whole table, so this holds at 1000+ people. No hardcoded
names, no seed-specific cases: everything comes from the database.
"""
from __future__ import annotations

import difflib
import re

#: Sentinel: the name matched more than one real person → the caller must pick.
AMBIGUOUS = object()

#: Cap on rows pulled per partial/fuzzy query — bounds work at any headcount.
_MAX_SCAN = 400
#: Most candidates we ever surface in a disambiguation.
_MAX_CANDIDATES = 8
#: difflib ratio a fuzzy full-name match must clear (typo tolerance, not loose).
_FUZZY_MIN = 0.82

#: Function/command words that are never part of a person's name. Kept deliberately
#: small — only words that appear in the assistant's own action phrasing or as pure
#: grammar — so real names are never stripped. Matching is data-driven, not by list.
_STOP = {
    "a", "an", "the", "to", "for", "of", "on", "in", "with", "and", "or", "please",
    "give", "recognise", "recognize", "recognition", "kudos", "shoutout", "thank",
    "thanks", "draft", "write", "review", "reviews", "schedule", "start", "open",
    "initiate", "begin", "create", "make", "approve", "enrich", "record", "respond",
    "goal", "goals", "kpi", "kpis", "feedback", "360", "roadmap", "succession", "jd",
    "checkin", "check", "check-in", "one", "1", "colleague", "person", "people",
    "someone", "somebody", "name", "who", "whom", "her", "his", "their", "them",
    "him", "he", "she", "they", "my", "me", "i", "we", "us", "our", "you", "your",
    "how", "is", "are", "was", "doing", "does", "do", "what", "about", "this", "that",
    "cycle", "team", "work", "excellent", "great", "good", "amazing", "help", "need",
    "needs", "right", "now", "today", "again", "so", "very", "really", "would", "like",
}


def _name_tokens(message: str) -> list[str]:
    """Content tokens (lowercased) from the message that could be part of a name —
    alphabetic words of length ≥ 2 with the function/command words removed. Order is
    preserved so adjacent tokens can form a full-name bigram. A trailing possessive is
    stripped ("Rhea's" → "rhea") while a real name apostrophe is kept ("O'Brien")."""
    out = []
    for w in re.findall(r"[a-z][a-z'\-]+", (message or "").lower()):
        w = re.sub(r"[’']s$", "", w)  # drop possessive 's, keep O'Brien intact
        if len(w) >= 2 and w not in _STOP:
            out.append(w)
    return out


def _one_or_ambiguous(users):
    """Collapse a set of candidate users to a single resolution: one → that user;
    several → :data:`AMBIGUOUS`; none → ``None``. De-dupes by id (a user can surface
    from more than one query)."""
    uniq = {u.id: u for u in users}
    vals = list(uniq.values())
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    return AMBIGUOUS


def _base_queryset(caller, population_ids, exclude_self):
    from apps.identity.models import User

    qs = User.objects.filter(is_active=True)
    if population_ids is not None:
        qs = qs.filter(id__in=population_ids)
    if exclude_self:
        qs = qs.exclude(id=caller.id)
    return qs


def resolve_person_in_population(caller, message, *, population_ids=None, exclude_self=True):
    """Resolve the person NAMED in ``message`` within a population. Returns a ``User``,
    :data:`AMBIGUOUS`, or ``None``. Directory-only — reads no performance data.

    ``population_ids=None`` searches the whole active tenant (recognition & other
    tenant-wide actions); a set restricts to the caller's visible scope (data actions,
    which additionally run their own access check). ``exclude_self`` drops the caller
    (recognition can't be self-recognition; a data 'how am I doing' resolves self by a
    different path)."""
    tokens = _name_tokens(message)
    if not tokens:
        return None
    base = _base_queryset(caller, population_ids, exclude_self)

    # ── TIER 1: exact full name (case-insensitive). Adjacent content bigrams cover
    # "First Last"; the joined phrase covers a bare "First Last" follow-up. An exact
    # hit WINS and only asks when two real people share that exact name. ────────────
    exact = {}
    bigrams = [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
    if len(tokens) >= 2:
        bigrams.append(" ".join(tokens))  # whole cleaned phrase (3-part names, etc.)
    for phrase in bigrams:
        for u in base.filter(display_name__iexact=phrase)[: _MAX_CANDIDATES + 1]:
            exact[u.id] = u
    if exact:
        return _one_or_ambiguous(exact.values())

    # ── TIER 2 & 3: token-overlap ranking. Each distinctive token runs ONE indexed
    # icontains (capped); a user scores per name-token they match on a word boundary.
    # The highest-scoring users win — so "priya nair" (both tokens) beats a lone
    # "priya", and a single "mateo" still resolves. ─────────────────────────────────
    scored: dict = {}
    for tok in dict.fromkeys(tokens):  # de-dup, keep order
        if len(tok) < 3:
            continue
        for u in base.filter(display_name__icontains=tok)[:_MAX_SCAN]:
            name_l = (u.display_name or "").lower()
            if re.search(rf"\b{re.escape(tok)}", name_l):
                count, _ = scored.get(u.id, (0, u))
                scored[u.id] = (count + 1, u)
    query = " ".join(tokens)
    if scored:
        best = max(count for count, _ in scored.values())
        top = [u for count, u in scored.values() if count == best]
        if len(top) == 1:
            return top[0]
        # Several tied on token-count. If the user NAMED a full person (≥2 tokens),
        # break the tie by fuzzy similarity to the whole query and accept ONLY a clear
        # winner — so "mateo santoss" picks Mateo Santos over Mateo Okafor, but a bare
        # "priya" (one token, 7 real Priyas) stays genuinely AMBIGUOUS.
        if len(tokens) >= 2:
            rated = sorted(
                ((difflib.SequenceMatcher(None, query, (u.display_name or "").lower()).ratio(), u) for u in top),
                key=lambda t: t[0],
                reverse=True,
            )
            if rated[0][0] >= 0.72 and rated[0][0] - rated[1][0] >= 0.08:
                return rated[0][1]
        return _one_or_ambiguous(top[: _MAX_CANDIDATES + 1])

    # ── TIER 4: fuzzy full name (typo tolerance), bounded. Names CONTAINING a
    # 3-letter prefix of a query token are pulled (capped) — icontains, not
    # istartswith, so a typo in a *last* name ("menonn" → "Menon") is still reached —
    # then ranked by difflib ratio against the full query. ──────────────────────────
    pool: dict = {}
    for tok in dict.fromkeys(tokens):
        if len(tok) < 3:
            continue
        for u in base.filter(display_name__icontains=tok[:3])[:_MAX_SCAN]:
            pool[u.id] = u
    best_ratio, winners = 0.0, []
    for u in pool.values():
        ratio = difflib.SequenceMatcher(None, query, (u.display_name or "").lower()).ratio()
        if ratio > best_ratio + 1e-9:
            best_ratio, winners = ratio, [u]
        elif abs(ratio - best_ratio) <= 1e-9:
            winners.append(u)
    if best_ratio >= _FUZZY_MIN:
        return _one_or_ambiguous(winners[: _MAX_CANDIDATES + 1])
    return None


def suggest_candidates(caller, message, *, population_ids=None, exclude_self=True, limit=_MAX_CANDIDATES):
    """A capped, ranked list of people the message might mean — for a disambiguation
    prompt (names + emails). Same population rules as
    :func:`resolve_person_in_population`; reads no performance data."""
    tokens = _name_tokens(message)
    if not tokens:
        return []
    base = _base_queryset(caller, population_ids, exclude_self)
    scored: dict = {}
    for tok in dict.fromkeys(tokens):
        if len(tok) < 3:
            continue
        for u in base.filter(display_name__icontains=tok)[:_MAX_SCAN]:
            name_l = (u.display_name or "").lower()
            if re.search(rf"\b{re.escape(tok)}", name_l):
                count, _ = scored.get(u.id, (0, u))
                scored[u.id] = (count + 1, u)
    ranked = sorted(scored.values(), key=lambda cu: (-cu[0], (cu[1].display_name or "").lower()))
    return [u for _, u in ranked[:limit]]
