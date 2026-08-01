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

Ranking is TIERED so an exact identifier wins outright and never disambiguates, even
when many people share a first name (the "Priya Nair" bug — 7 people named "Priya *"
must not drown out the one exact "Priya Nair"):

  0. exact EMAIL (the one truly unique handle)    → always decisive, never ambiguous
  1. exact full name (case-insensitive)           → 1 hit wins; ≥2 real "same name" ask
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

#: An email address written anywhere in the message. Email is the ONE unique handle a
#: person has, so naming it is never ambiguous — and it's how you refer to the second
#: "Priya Nair" once a disambiguation has listed both.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

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


#: A name token: letters (ANY script), plus the apostrophes and hyphens that occur
#: inside real surnames. `[^\W\d_]` is the portable way to say "any Unicode letter" —
#: an `[a-z]` class here silently erased every accented and non-Latin name, so
#: "Zoë Ćirić" and "山田 太郎" resolved to nobody. Names are not ASCII.
_NAME_TOKEN_RE = re.compile(r"[^\W\d_][^\W\d_'’\-]*", re.UNICODE)

#: A middle initial, e.g. "A." — a single letter followed by a full stop.
_INITIAL_RE = re.compile(r"[^\W\d_]\.", re.UNICODE)


def _name_tokens(message: str) -> list[str]:
    """Content tokens (lowercased) from the message that could be part of a name —
    letter-words of length ≥ 2 with the function/command words removed. Order is
    preserved so adjacent tokens can form a full-name bigram. A trailing possessive is
    stripped ("Rhea's" → "rhea") while a real name apostrophe is kept ("O'Brien")."""
    out = []
    for w in _NAME_TOKEN_RE.findall((message or "").lower()):
        w = re.sub(r"[’']s$", "", w)  # drop possessive 's, keep O'Brien intact
        if len(w) >= 2 and w not in _STOP:
            out.append(w)
    return out


def _name_spans(message: str) -> list[str]:
    """Maximal runs of consecutive words that could be a person's name, in the
    message's ORIGINAL text — "give recognition to Aisha B. O'Brien for her great
    work" yields ``["Aisha B. O'Brien"]``.

    This exists because :func:`_name_tokens` drops anything shorter than two letters,
    which quietly deletes MIDDLE INITIALS: "Jamal K. Cohen" tokenized to
    ``["jamal", "cohen"]``, so the exact full name never matched its own record and
    the lookup fell through to fuzzy ranking — where it could, and did, pick a
    different "Jamal … Cohen". Matching the run verbatim keeps the initial, so the
    exact tier can do its job.
    """
    spans, run = [], []
    for word in (message or "").split():
        key = re.sub(r"[^\w'’\-]", "", word.lower())
        # A lone letter with a full stop is an INITIAL, never a stop word. Without this
        # "Sofia A. Menon" splits at "A." (which is in the stop list as the article "a")
        # into "Sofia" and "Menon", and the exact tier then matches a *different*
        # colleague called plain "Sofia Menon".
        is_initial = bool(_INITIAL_RE.fullmatch(word))
        if key and (is_initial or key not in _STOP):
            run.append(word.strip(",;:!?"))
        elif run:
            spans.append(" ".join(run))
            run = []
    if run:
        spans.append(" ".join(run))
    return [s for s in spans if s]


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


def resolve_person_in_population(caller, message, *, population_ids=None, exclude_self=True,
                                 allow_fuzzy=True, require_full_name=False):
    """Resolve the person NAMED in ``message`` within a population. Returns a ``User``,
    :data:`AMBIGUOUS`, or ``None``. Directory-only — reads no performance data.

    ``population_ids=None`` searches the whole active tenant (recognition & other
    tenant-wide actions); a set restricts to the caller's visible scope (data actions,
    which additionally run their own access check). ``exclude_self`` drops the caller
    (recognition can't be self-recognition; a data 'how am I doing' resolves self by a
    different path).

    Two knobs exist because a DIRECTORY action and a DATA question want different
    answers to the same ambiguity, and conflating them is unsafe:

    ``allow_fuzzy`` — typo tolerance. Fine when the outcome is "post a kudos to the
    person you obviously meant". NOT fine on the data path, in either direction: a
    guessed spelling must not silently open someone's performance record, and it must
    not become an oracle either — a mistyped name that "corrects" to a real colleague
    confirms that colleague exists and spells their name for you, even when the caller
    could never see them. Data questions pass ``False`` and let the caller offer an
    explicit, scope-limited "did you mean…?" instead.

    ``require_full_name`` — when the user typed a multi-word name, demand that ALL of
    its words match. Without it a manager asking about "Hugo O'Brien" (whom they can't
    see) resolves to "Hana O'Brien" on their own team, on the strength of the surname
    alone, and gets a confident answer about the wrong person.
    """
    base = _base_queryset(caller, population_ids, exclude_self)

    # ── TIER 0: an EMAIL settles it. Unique per tenant and index-backed, so this is
    # both the cheapest and the least ambiguous lookup — and it's how a user picks
    # between two people who genuinely share a name after we list both. ─────────────
    for addr in _EMAIL_RE.findall(message or ""):
        hit = list(base.filter(email__iexact=addr)[:2])
        if hit:
            return _one_or_ambiguous(hit)

    tokens = _name_tokens(message)
    if not tokens:
        return None

    # ── TIER 1: exact full name (case-insensitive). Adjacent content bigrams cover
    # "First Last"; the joined phrase covers a bare "First Last" follow-up. An exact
    # hit WINS and only asks when two real people share that exact name. ────────────
    # The verbatim name-shaped runs first — they preserve middle initials, accents and
    # punctuation exactly as the person's record holds them. Then the stop-word-filtered
    # bigrams, which still catch a name split across filler ("recognise Priya, our Nair").
    #
    # MOST SPECIFIC PHRASE WINS, and the search stops there. Pooling hits from every
    # phrase makes a precise query less decisive than a vague one: "Aisha B. O'Brien"
    # matches exactly one person, but its filtered bigram "aisha o'brien" also matches a
    # DIFFERENT colleague of that name, and the union of the two is an ambiguity the
    # user never created. Only a phrase matching two people is a real ambiguity.
    phrases = _name_spans(message)
    phrases += [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
    if len(tokens) >= 2:
        phrases.append(" ".join(tokens))  # whole cleaned phrase (3-part names, etc.)
    for phrase in dict.fromkeys(phrases):  # de-dup, keep order
        hits = list(base.filter(display_name__iexact=phrase)[: _MAX_CANDIDATES + 1])
        if hits:
            return _one_or_ambiguous(hits)

    # A multi-word name the user actually typed ("Hugo O'Brien"), if any. Under
    # `require_full_name` every one of its words must appear in a candidate's name,
    # so a surname alone can't carry a match to the wrong person.
    required = []
    if require_full_name:
        for span in _name_spans(message):
            span_tokens = _name_tokens(span)
            if len(span_tokens) >= 2:
                required = span_tokens
                break

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
    if required:
        scored = {
            uid: (count, u) for uid, (count, u) in scored.items()
            if all(re.search(rf"\b{re.escape(t)}", (u.display_name or "").lower()) for t in required)
        }
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
    # then ranked by difflib ratio against the full query. Skipped entirely on the
    # data path (see ``allow_fuzzy``): there, a near-miss must be offered back to the
    # user as a question, never acted on. ───────────────────────────────────────────
    if not allow_fuzzy:
        return None
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
