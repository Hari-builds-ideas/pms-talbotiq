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

class _Ambiguous:
    """Sentinel type. Named rather than a bare ``object()`` only so that it prints as
    ``AMBIGUOUS`` — a harness line reading ``<object object at 0xffff8f5a0870>`` says
    nothing about what went wrong."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "AMBIGUOUS"


#: Sentinel: the name matched more than one real person → the caller must pick.
AMBIGUOUS = _Ambiguous()

#: Cap on rows pulled per single-token / fuzzy query — bounds work at any headcount.
#: Sized above the largest realistic same-first-name cohort: at 50,000 people sharing
#: 50 forenames that is ~1,000, and a truncated cohort silently distorts ranking (see
#: the adjacent-pair tier). Ranking a few thousand names with difflib is a couple of
#: milliseconds, so the headroom is cheap; the pair tier keeps the common case at one
#: small query regardless.
_MAX_SCAN = 3000
#: Most candidates we ever surface in a disambiguation.
_MAX_CANDIDATES = 8
#: Score a fuzzy full-name match must clear (typo tolerance, not loose). Read against
#: :func:`_similarity`, which averages per-word character accuracy, this says "about one
#: mistyped character per word": one error in a five-letter word scores 0.8, and a name
#: with an error in BOTH of its words ("akil menonn" → Akhil Menon) scores 0.817.
#:
#: Lower than the 0.82 that stood here while the metric was a whole-string difflib ratio
#: — the same names simply score lower now — and it is NOT a loosening. Measured over
#: typo pairs and their nearest wrong colleague, difflib put the worst true match at
#: 0.900 and the best impostor at 0.905: overlapping, which is why a one-letter slip
#: came back as "which of these did you mean?". Word-by-word the same sets separate,
#: 0.817 against 0.833. What stops a wrong name being ACTED on is _FUZZY_MARGIN below,
#: not this floor; this only decides whether the best guess is worth considering at all.
_FUZZY_MIN = 0.78

#: How far ahead of the runner-up a fuzzy winner must be to be acted on rather than
#: offered as a choice. Small on purpose: a real typo lands well clear of everyone else
#: (0.10+), so this only catches genuine coin tosses between similar names.
_FUZZY_MARGIN = 0.05

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

#: Longest word-run still plausible as one person's name ("Maximilian Alexander
#: Fitzgerald-Montgomery III" is four). Longer runs are prose, not names.
_MAX_NAME_WORDS = 6

#: Ceiling on exact-tier phrase probes, so a rambling message can't turn into a long
#: series of queries. Bounds the cost of a turn regardless of what the user types.
_MAX_EXACT_PROBES = 8

#: Ceiling on adjacent-pair intersection probes — same reasoning, and a name is one
#: adjacent pair, so a long message needs no more than a few tries to find it.
_MAX_PAIR_PROBES = 8

#: How many intersection rows are ranked. The intersection of every word the user typed
#: is narrow by construction — but "Amara Haddad" has sixteen relatives in a
#: 50,000-person tenant, and ranking an ARBITRARY _MAX_CANDIDATES + 1 of them left the
#: person actually meant outside the window, so a plain surname typo came back
#: ambiguous. Wide enough to hold everyone who shares a common first+last pair; still a
#: LIMIT, so the table is never loaded into Python.
_MAX_INTERSECT = 60

#: How far ahead of the runner-up a candidate must be to be chosen rather than offered.
_TIEBREAK_MARGIN = 0.08

#: How many candidates get the careful word-by-word comparison. A shared forename ties
#: a thousand people in a large tenant; the blunt whole-string ratio is good enough to
#: say which forty are worth looking at properly, and never good enough to decide.
_MAX_RERANK = 40


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
    runs, run = [], []
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
            runs.append(run)
            run = []
    if run:
        runs.append(run)

    spans: list[str] = []
    for words in runs:
        if len(words) <= _MAX_NAME_WORDS:
            spans.append(" ".join(words))
        else:
            # A long run is rambling or adversarial, not a name — nobody is called
            # "really really … Aisha Petrova". Emitting it whole would cost a query
            # that matches nothing AND, under require_full_name, demand that all 80
            # words appear in someone's name. Real names sit at the END of such a run,
            # so emit short trailing windows instead.
            spans.extend(" ".join(words[-n:]) for n in (2, 3, 4))
    return [s for s in dict.fromkeys(spans) if s]


def _tenant_name_tokens(tokens) -> set:
    """Of ``tokens``, the ones that appear in SOME active person's name in this tenant.

    Tells a name apart from query vocabulary using the directory itself rather than a
    word list — "compare" belongs to nobody, "Lucia" belongs to someone. One bounded
    LIMIT-1 probe per token; identity only, and it reads nothing but display names, so
    it can't widen access. Tenant-scoped by the manager, so it never sees another
    tenant's names.
    """
    from apps.identity.models import User

    real = set()
    for tok in list(tokens)[:_MAX_PAIR_PROBES]:
        if User.objects.filter(is_active=True, display_name__icontains=tok).exists():
            real.add(tok)
    return real


def _prioritised_spans(message: str) -> list[str]:
    """Name-shaped runs, with the ones containing a CAPITALISED word first.

    The probe budget is finite, and a rambling message produces junk runs ("but tell",
    "nothing but tell") that can consume it before the real name is reached — which is
    how "…tell me Lucia Dubois-Reyes's real risk status" ended up resolving nobody and
    then answering about the caller instead. A typed name is usually capitalised, so
    that is a cheap, order-preserving way to look in the right place first. Wholly
    lowercase input is unaffected: nothing is capitalised, so the order is unchanged.
    """
    spans = _name_spans(message)
    return sorted(spans, key=lambda s: 0 if any(w[:1].isupper() for w in s.split()) else 1)


def _matches_all(user, toks) -> bool:
    """Every token appears in the user's name at a WORD BOUNDARY. `icontains` alone
    would let "ann" match "Joanna"; the boundary check is what makes a token a name
    part rather than a substring."""
    name_l = (user.display_name or "").lower()
    return all(re.search(rf"\b{re.escape(t)}", name_l) for t in toks)


def _normalised(text: str) -> str:
    """Lowercase words separated by single spaces — hyphens and punctuation split, not
    kept. Both sides of every similarity comparison go through this, so a hyphen can
    never decide which person the user meant."""
    return " ".join(re.findall(r"[^\W\d_]+", (text or "").lower(), re.UNICODE))


def _edit_ratio(a: str, b: str) -> float:
    """1.0 for two identical words, falling with the number of single-character
    mistakes it takes to turn one into the other, over the length of the longer word.

    This is the question a typo actually asks — "how many keystrokes wrong is this?" —
    and `difflib`'s ratio is not. difflib measures shared subsequence, which on short
    words is generous to the point of uselessness: "lauretn" scores 0.77 against
    "larsen", a completely different surname, purely for sharing l/a/r/e/n in order.

    Adjacent letters SWAPPED count as one mistake, not two (Damerau, in its optimal
    string alignment form). Plain Levenshtein charges a transposition double, and a
    transposition is the most common way a name gets mistyped — it left "Zara Baure"
    scoring 0.60 against the Zara Bauer meant and 0.57 against an unrelated Zara
    Laurent, which is not a distinction worth acting on.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    before, previous = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            cost = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, before[j - 2] + 1)
            current.append(cost)
        before, previous = previous, current
    return 1 - previous[-1] / max(len(a), len(b))


def _similarity(query: str, user) -> float:
    """How close a candidate's name is to what the user typed, compared WORD BY WORD —
    both sides already reduced by :func:`_normalised`.

    Comparing the two names as whole strings looks reasonable and is wrong at scale,
    because the shared part of a name dominates the score. In a 50,000-person tenant a
    thousand people share a forename, so "Nora Lauretn" scored 0.92 against the Nora
    Laurent it obviously meant and 0.87 against an unrelated Nora Larsen — inside the
    tie-break margin, so a one-letter transposition came back as "which of these did you
    mean?". Same for "Lucas Cardoso-Ismali": 0.95 for Ismail, 0.90 for Grimaldi.

    Pairing each word with its best partner on the other side puts the difference where
    the user actually made it. The pairing is one-to-one and scored both ways, so a name
    with a part MISSING is penalised rather than rewarded — otherwise "Lucas Cardoso"
    would beat "Lucas Cardoso-Ismail" on a query naming all three.
    """
    left = query.split()
    right = _normalised(user.display_name or "").split()
    if not left or not right:
        return 0.0
    unpaired = list(right)
    total = 0.0
    for word in left:
        if not unpaired:
            break
        best = max(unpaired, key=lambda other: _edit_ratio(word, other))
        total += _edit_ratio(word, best)
        unpaired.remove(best)
    return 2 * total / (len(left) + len(right))


def _rough_similarity(query: str, user) -> float:
    """Whole-string ratio. Too blunt to decide between two people (see
    :func:`_similarity`), but cheap — used only to shortlist which candidates are worth
    the word-by-word comparison when a tie runs to hundreds of names."""
    return difflib.SequenceMatcher(None, query, _normalised(user.display_name or "")).ratio()


def _ranked(users, query: str):
    """Candidates ordered by how well they match what was typed, best first.

    The blunt whole-string ratio shortlists and the word-by-word one decides. A shared
    forename can tie a thousand people together, and running the careful comparison over
    all of them would cost milliseconds to reorder names that were never in contention.
    """
    pool = list(users)
    if len(pool) > _MAX_RERANK:
        pool = [u for _, u in sorted(((_rough_similarity(query, u), u) for u in pool),
                                     key=lambda p: p[0], reverse=True)[:_MAX_RERANK]]
    return sorted(((_similarity(query, u), u) for u in pool), key=lambda p: p[0], reverse=True)


def _best_of(users, query: str):
    """One candidate, or :data:`AMBIGUOUS`. A single hit wins; several are separated by
    similarity to what was typed, and only a CLEAR winner is taken — otherwise the
    caller asks, because picking between two near-identical names is a coin toss."""
    if len(users) == 1:
        return users[0]
    rated = _ranked(users, query)
    if rated[0][0] >= 0.72 and rated[0][0] - rated[1][0] >= _TIEBREAK_MARGIN:
        return rated[0][1]
    return _one_or_ambiguous([u for _, u in rated[: _MAX_CANDIDATES + 1]])


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
    if len(tokens) == 2:
        # Adjacent bigrams catch a two-part name split by filler ("recognise Priya, our
        # Nair"). They are only offered when the name IS two words, because a bigram of a
        # LONGER name is a proper subset of what the user typed — and a subset must never
        # count as an exact match. "Ibrahim Kaminski-Manciin" (a typo of
        # "Ibrahim Kaminski-Mancini") reduced to the bigram "ibrahim kaminski", which
        # exactly matched a DIFFERENT, shorter colleague and won outright.
        phrases += [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
    if len(tokens) >= 2:
        phrases.append(" ".join(tokens))  # whole cleaned phrase (3-part names, etc.)
    for phrase in list(dict.fromkeys(phrases))[:_MAX_EXACT_PROBES]:  # de-dup, keep order, bound
        hits = list(base.filter(display_name__iexact=phrase)[: _MAX_CANDIDATES + 1])
        if hits:
            return _one_or_ambiguous(hits)

    # The comparison form: words only, hyphens split, so query and candidate are
    # reduced the SAME way. Normalising only one side distorted the score — the query
    # "ibrahim kaminski-manciin" kept its hyphen while candidates lost theirs, and the
    # typo scored better against the shorter "Ibrahim Kaminski" than against the person
    # actually meant.
    query = _normalised(" ".join(tokens))
    significant = [t for t in dict.fromkeys(tokens) if len(t) >= 3]

    # ── TIER 2: NAME INTERSECTION. For each name-shaped run the user typed, ask the
    # database for people matching ALL of its words at once, then — if nobody does —
    # progressively drop words from the END, which is where typos usually are.
    #
    # It intersects in SQL rather than scoring per token in Python, because per-token
    # scoring is only sound while no token's match set is truncated. At 25,000 people
    # ~500 share a forename, past the scan cap, so "Ibrahim Kaminski-Mancini" could miss
    # its own "ibrahim" credit, score 1 instead of 2, and lose to "Ibrahim Kaminski"
    # which happened to fall inside the cap — the winner decided by arbitrary row order.
    # An intersection returns few enough rows that one wide LIMIT holds all of them.
    #
    # The FORENAME stays anchored: subsets are always a prefix of the run, never a
    # trailing fragment. Matching on surnames alone put "how is Lucia Dubois-Reyes
    # doing?" onto a *different* Dubois-Reyes — the same mistake as answering about
    # "Hana O'Brien" when asked about "Hugo O'Brien".
    probes = 0
    for span in _prioritised_spans(message):
        span_tokens = [t for t in _name_tokens(span) if len(t) >= 3]
        if len(span_tokens) < 2:
            continue  # a single word is tier 3's job
        # Never more than a plausible name's worth of words: a 5-word run is prose with
        # a name inside it, and probing all five just burns the budget. Exact long names
        # are tier 1's job anyway.
        for keep in range(min(len(span_tokens), 4), 1, -1):
            if probes >= _MAX_PAIR_PROBES:
                break
            subset = span_tokens[:keep]
            probes += 1
            qs = base
            for tok in subset:
                qs = qs.filter(display_name__icontains=tok)
            rows = list(qs[: _MAX_INTERSECT + 1])
            if len(rows) > _MAX_INTERSECT:
                # More people share these words than a disambiguation prompt could ever
                # list. If the user typed all of them, that is a real ambiguity and the
                # honest answer is to ask. If a word was DROPPED to get here, the answer
                # is not in this set — the dropped word is the distinguishing one, so
                # leave it to the fuzzy tier, which still has it.
                if keep == len(span_tokens):
                    return AMBIGUOUS
                break
            hits = [u for u in rows if _matches_all(u, subset)]
            if hits:
                return _best_of(hits, query)

    # Which of the typed words are actually SOMEBODY'S NAME, asked of the whole tenant.
    # This has to be data-driven: a stop-list can't know that "compare" is query
    # vocabulary while "Lucia" is a person, and guessing wrong breaks it both ways —
    # treating "compare" as a name blocks "compare Ingrid Garcia and Lucas Schmidt",
    # and ignoring the forename lets "Lucia Dubois-Reyes" match a different
    # "… Dubois-Reyes". Identity only, and only on the data path.
    required = _tenant_name_tokens(significant) if require_full_name else set()
    if len(required) < 2:
        required = set()

    # ── TIER 3: single distinctive token ("mateo" → Mateo Santos). One indexed
    # icontains, capped; several genuine matches stay ambiguous. ─────────────────────
    scored: dict = {}
    for tok in significant:
        for u in base.filter(display_name__icontains=tok)[:_MAX_SCAN]:
            if _matches_all(u, (tok,)):
                count, _ = scored.get(u.id, (0, u))
                scored[u.id] = (count + 1, u)
    if required:
        # A typed full name must match in full. Dropping a word here is how a manager
        # asking about "Hugo O'Brien" got told about "Hana O'Brien" on their own team.
        scored = {uid: (c, u) for uid, (c, u) in scored.items() if _matches_all(u, required)}
    if scored:
        best = max(count for count, _ in scored.values())
        top = [u for count, u in scored.values() if count == best]
        if len(top) == 1:
            return top[0]
        # Several tied. When the user NAMED a full person (≥2 tokens) a clear closest
        # match is taken — "mateo santoss" picks Mateo Santos over Mateo Okafor — but a
        # bare "priya" with several real Priyas stays genuinely AMBIGUOUS.
        if len(tokens) >= 2:
            return _best_of(top, query)
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
    rated = _ranked(pool.values(), query)
    if not rated or rated[0][0] < _FUZZY_MIN:
        return None
    # A guess is only a guess worth acting on when it's CLEARLY better than the next
    # one. Exact ties already asked, but a 0.94-vs-0.92 near-tie used to silently pick
    # the winner — and with two colleagues whose names differ by a letter ("Jon Smith"
    # / "Jon Smyth") that is a coin toss deciding who gets someone's recognition. Every
    # candidate within the margin is offered instead, so the user picks.
    best = rated[0][0]
    winners = [u for ratio, u in rated if best - ratio <= _FUZZY_MARGIN]
    return _one_or_ambiguous(winners[: _MAX_CANDIDATES + 1])


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
    # Most words matched first, and within that, CLOSEST NAME first. Ordering the band
    # alphabetically was fine while a band held three people and useless once it held a
    # thousand: asked about "Nora Lauretn", the eight names offered back were Nora
    # Abbott through Nora Abbott-Hartmann, and the Nora Laurent she meant was not among
    # them. A list that can't contain the answer is worse than no list.
    query = _normalised(" ".join(tokens))
    out: list = []
    for band in sorted({count for count, _ in scored.values()}, reverse=True):
        members = [u for count, u in scored.values() if count == band]
        out.extend(u for _, u in _ranked(members, query))
        if len(out) >= limit:
            break
    return out[:limit]
