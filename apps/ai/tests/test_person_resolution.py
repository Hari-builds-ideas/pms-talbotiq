"""
Person resolution (AGENT_REBUILD/A) — ONE company-wide, DB-backed resolver, and the
architectural line it must never cross.

The contract:
  * **Directory** (name → identity) is COMPANY-WIDE. You can legitimately recognise or
    request feedback from a colleague on another team, so "not in your reporting line"
    must not mean "not found".
  * **Data** (goals, KPIs, reviews, scores) stays PERMISSION-SCOPED and is re-checked
    every turn. Resolving someone's name grants nothing — the test below proves an
    employee can name a colleague for a directory action and *still* be refused their
    performance data.
  * Matching is tiered: email, then exact full name (which NEVER disambiguates), then
    token overlap, then bounded fuzzy for typos. Only genuine duplicates ask.
  * It scales: the query COUNT is constant in headcount, and no query loads the table
    into Python. A tenant of 5,000 costs the same number of round-trips as one of 5.
  * Nothing depends on a specific seed person — every name here is created by the test.
"""
import pytest
from django.test import override_settings

from apps.ai.actions import _resolve_person, _resolve_recipient_in_tenant
from apps.ai.agents.chat import chat_answer
from apps.ai.directory import AMBIGUOUS, resolve_person_in_population, suggest_candidates
from apps.ai.models import ChatSession
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _name(user, display):
    user.display_name = display
    user.save(update_fields=["display_name"])
    return user


# ── the matching tiers ───────────────────────────────────────────────────────────


def test_exact_full_name_resolves_for_someone_outside_the_callers_team(org):
    """The headline requirement: a manager naming a colleague they don't manage."""
    with tenant_context(org.tenant):
        outsider = _name(org.peer, "Ingrid Garcia")  # reports to the HRBP, not to us
        got = _resolve_recipient_in_tenant(org.manager, "give recognition to Ingrid Garcia")
        assert got is not None and got is not AMBIGUOUS and got.id == outsider.id


def test_email_resolves_and_is_never_ambiguous(org):
    """Email is the one unique handle — it must settle even a genuine name clash."""
    with tenant_context(org.tenant):
        _name(org.peer, "Priya Nair")
        twin = UserFactory(
            tenant=org.tenant, role="EMPLOYEE", display_name="Priya Nair",
            email="priya.nair2@acme.test", manager=org.hrbp,
        )
        got = resolve_person_in_population(org.manager, "recognise priya.nair2@acme.test")
        assert got is not None and got is not AMBIGUOUS and got.id == twin.id


def test_a_shared_first_name_does_not_drown_out_an_exact_full_name(org):
    """Many "Priya *" must not turn an exact "Priya Nair" into a question."""
    with tenant_context(org.tenant):
        target = _name(org.peer, "Priya Nair")
        for surname in ("Silva", "Novak", "Khan", "Lindqvist", "Mbeki", "Costa"):
            UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name=f"Priya {surname}",
                        email=f"priya.{surname.lower()}@acme.test")
        got = resolve_person_in_population(org.manager, "give recognition to Priya Nair")
        assert got is not None and got is not AMBIGUOUS and got.id == target.id


def test_a_unique_first_name_alone_resolves(org):
    with tenant_context(org.tenant):
        target = _name(org.peer, "Mateo Santos")
        got = resolve_person_in_population(org.manager, "give recognition to Mateo")
        assert got is not None and got is not AMBIGUOUS and got.id == target.id


def test_a_typo_still_finds_the_right_person(org):
    """"Priya Niar" is a transposition, not a different person."""
    with tenant_context(org.tenant):
        target = _name(org.peer, "Priya Nair")
        got = resolve_person_in_population(org.manager, "give recognition to Priya Niar")
        assert got is not None and got is not AMBIGUOUS and got.id == target.id


def test_two_real_people_with_the_same_name_disambiguate_with_emails(org):
    """A REAL duplicate is the only case that should ever ask — and it must show the
    emails, because the name alone can't tell them apart."""
    with tenant_context(org.tenant):
        _name(org.peer, "Priya Nair")
        UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Priya Nair",
                    email="priya.nair2@acme.test", manager=org.hrbp)
        assert resolve_person_in_population(org.manager, "recognise Priya Nair") is AMBIGUOUS

        options = suggest_candidates(org.manager, "recognise Priya Nair")
        assert len(options) >= 2
        emails = {u.email for u in options}
        assert len(emails) >= 2, "the candidates must be distinguishable — by email"


def test_an_unknown_name_is_an_honest_not_found(org):
    with tenant_context(org.tenant):
        _name(org.peer, "Ingrid Garcia")
        assert resolve_person_in_population(org.manager, "recognise Zebediah Quartermain") is None


def test_a_name_from_another_tenant_never_resolves(org):
    """Tenant isolation is not weakened by a company-wide directory."""
    other = TenantFactory(slug="globex", name="Globex")
    UserFactory(tenant=other, role="EMPLOYEE", display_name="Ingrid Garcia",
                email="ingrid@globex.test")
    with tenant_context(org.tenant):
        assert resolve_person_in_population(org.manager, "recognise Ingrid Garcia") is None


# ── names that aren't tidy ASCII first+last (found by the 5,000-person harness) ──


@pytest.mark.parametrize("display,asked", [
    ("José Álvarez", "give recognition to José Álvarez"),
    ("Zoë Ćirić", "give recognition to Zoë Ćirić"),
    ("山田 太郎", "give recognition to 山田 太郎"),
    ("Ana-Lucía O'Brien-Fitzgerald", "give recognition to Ana-Lucía O'Brien-Fitzgerald"),
    ("Maximilian Alexander Fitzgerald-Montgomery III",
     "give recognition to Maximilian Alexander Fitzgerald-Montgomery III"),
])
def test_names_outside_plain_ascii_resolve(org, display, asked):
    """Accents, non-Latin scripts, hyphens, apostrophes and very long names are just
    names. The tokenizer used an [a-z] class, so every one of these matched NOTHING —
    those people were simply unreachable by the assistant."""
    with tenant_context(org.tenant):
        target = _name(org.peer, display)
        got = resolve_person_in_population(org.manager, asked)
        assert got is not None and got is not AMBIGUOUS and got.id == target.id


def test_a_middle_initial_does_not_derail_an_exact_match(org):
    """"Sofia A. Menon" must resolve to herself, not to a colleague called plain
    "Sofia Menon". The initial was dropped as a stop word ("a"), so the exact tier
    never saw the real name and a *different* person won on the remaining tokens."""
    with tenant_context(org.tenant):
        target = _name(org.peer, "Sofia A. Menon")
        UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Sofia Menon",
                    email="sofia.menon@acme.test", manager=org.hrbp)
        got = resolve_person_in_population(org.manager, "give recognition to Sofia A. Menon")
        assert got is not None and got is not AMBIGUOUS and got.id == target.id


def test_a_precise_name_is_not_made_ambiguous_by_its_own_looser_form(org):
    """Pooling matches across every candidate phrase let the loose form of a query
    outvote the precise one: "Sofia A. Menon" matches one person, its filtered bigram
    "sofia menon" matches another, and the union looked like an ambiguity the user
    never created. The most specific phrase must win outright."""
    with tenant_context(org.tenant):
        _name(org.peer, "Sofia A. Menon")
        UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Sofia Menon",
                    email="sofia.menon@acme.test", manager=org.hrbp)
        assert resolve_person_in_population(org.manager, "recognise Sofia A. Menon") is not AMBIGUOUS


# ── directory vs data: the same ambiguity gets two different answers, on purpose ──


def test_a_typo_resolves_a_directory_action_but_not_a_data_question(org):
    """Typo tolerance is a convenience for "post a kudos to the person you obviously
    meant". On the data path it must NOT act: a guessed spelling that silently opens
    someone's record is bad, and one that "corrects" to a real colleague is worse —
    it confirms that colleague exists and spells their name for you."""
    with tenant_context(org.tenant):
        target = _name(org.peer, "Bartholomew Ashworth")
        # Both parts mistyped, so ONLY the fuzzy tier can reach them — which is what
        # makes this an isolated test of the flag rather than of token overlap.
        mistyped = "give recognition to Bartholmew Ashwortk"

        directory = resolve_person_in_population(org.manager, mistyped)
        assert directory is not None and directory is not AMBIGUOUS and directory.id == target.id

        data = resolve_person_in_population(org.manager, mistyped, allow_fuzzy=False)
        assert data is None, "a data lookup must not silently accept a typo"


def test_a_typo_cannot_confirm_that_an_out_of_scope_person_exists(org):
    """The leak this rule prevents, end to end: an EMPLOYEE guessing at a colleague's
    name must not learn that the colleague exists, nor how their name is spelled."""
    with tenant_context(org.tenant):
        _name(org.report, "Bartholomew Ashworth")  # invisible to `peer`
        session = ChatSession.objects.create(tenant_id=org.peer.tenant_id, owner=org.peer)
        out = chat_answer(org.peer, "how is Bartholmew Ashworth doing?", session=session)
        answer = out.get("answer") or ""
        assert "Bartholomew" not in answer, f"the typo confirmed the real name: {answer!r}"


def test_a_typed_full_name_must_match_in_full_on_the_data_path(org):
    """A manager asking about "Hugo O'Brien" (not theirs) must not be answered about
    "Hana O'Brien" (theirs) on the strength of a shared surname."""
    with tenant_context(org.tenant):
        _name(org.report, "Hana O'Brien")  # in the manager's team
        outsider = UserFactory(tenant=org.tenant, role="EMPLOYEE", manager=org.hrbp,
                               display_name="Hugo O'Brien", email="hugo@acme.test")
        visible = {org.manager.id, org.report.id}

        loose = resolve_person_in_population(
            org.manager, "how is Hugo O'Brien doing?", population_ids=visible, exclude_self=False)
        assert loose is not None, "the surname alone matches Hana — that's the trap"

        strict = resolve_person_in_population(
            org.manager, "how is Hugo O'Brien doing?", population_ids=visible,
            exclude_self=False, allow_fuzzy=False, require_full_name=True)
        assert strict is None, "a full name must match in full"

        # …and tenant-wide it's the real Hugo, so the refusal can name him honestly.
        anywhere = resolve_person_in_population(
            org.manager, "how is Hugo O'Brien doing?", exclude_self=False,
            allow_fuzzy=False, require_full_name=True)
        assert anywhere is not None and anywhere.id == outsider.id


# ── the architectural line: finding someone is not permission to read about them ──


def test_directory_resolves_company_wide_but_data_stays_scoped(org):
    """The key separation. An EMPLOYEE can name a colleague for a directory action,
    yet the same name must NOT unlock that colleague's performance data."""
    with tenant_context(org.tenant):
        colleague = _name(org.report, "Ingrid Garcia")  # not visible to `peer`

        # DIRECTORY — company-wide: the employee can recognise them.
        found = _resolve_recipient_in_tenant(org.peer, "give recognition to Ingrid Garcia")
        assert found is not None and found is not AMBIGUOUS and found.id == colleague.id

        # DATA — still scoped: the same name resolves to nothing for a data action.
        assert _resolve_person(org.peer, "how is Ingrid Garcia doing?") is None


@override_settings(**FAKE)
def test_naming_a_colleague_does_not_reveal_their_performance(org):
    """End to end through the chat: the recognition works, the data question is
    refused, and the refusal leaks no performance detail."""
    with tenant_context(org.tenant):
        _name(org.report, "Ingrid Garcia")
        session = ChatSession.objects.create(tenant_id=org.peer.tenant_id, owner=org.peer)

        posted = chat_answer(org.peer, "give recognition to Ingrid Garcia", session=session)
        assert posted["status"] == "plan"

        asked = chat_answer(org.peer, "how is Ingrid Garcia doing?", session=session)
        answer = (asked.get("answer") or "").lower()
        assert asked["status"] in ("ok", "blocked")
        for leak in ("at risk", "on track", "behind pace", "attainment", "%"):
            assert leak not in answer, f"refusal leaked performance detail: {answer!r}"


# ── scale: constant query count, no full-table load ──────────────────────────────


def _resolution_query_count(org, headcount, tag="a") -> int:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    target = _name(org.peer, "Ingrid Garcia")
    # `tag` keeps emails unique when one test populates the tenant twice.
    for i in range(headcount):
        UserFactory(tenant=org.tenant, role="EMPLOYEE",
                    display_name=f"Person {tag.upper()}number{i}", email=f"{tag}{i}@acme.test")
    with CaptureQueriesContext(connection) as captured:
        got = resolve_person_in_population(org.manager, "give recognition to Ingrid Garcia")
    assert got is not None and got.id == target.id
    return len(captured.captured_queries)


@pytest.mark.parametrize("headcount", [5, 500])
def test_resolution_cost_does_not_grow_with_headcount(org, headcount):
    """Resolution must cost the same round-trips at any company size — the whole point
    of doing it in the database. Asserting a RANGE rather than an exact number: the
    contract is "constant and small", and pinning the exact count turns every
    legitimate optimisation into a test failure (it dropped from 2 to 1 when the exact
    tier learned to match the verbatim name span)."""
    with tenant_context(org.tenant):
        assert 1 <= _resolution_query_count(org, headcount) <= 4


def test_resolution_costs_the_same_at_5_and_500_people(org):
    """The comparison that actually proves constancy: the SAME lookup, two tenant
    sizes, identical cost. A per-person query would show up here as a difference."""
    with tenant_context(org.tenant):
        small = _resolution_query_count(org, 5, tag="s")
        large = _resolution_query_count(org, 500, tag="l")  # now a 505-person tenant
    assert small == large, f"cost grew with headcount: {small} → {large}"


def test_every_resolution_query_is_limited_so_the_table_is_never_loaded(org):
    """The invariant that makes this hold at 50,000 people: ranking happens over a
    BOUNDED slice, never the whole match set. A token shared by 120 people must still
    produce only LIMITed queries — if one ever comes back unbounded, this fails."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with tenant_context(org.tenant):
        for i in range(120):
            UserFactory(tenant=org.tenant, role="EMPLOYEE",
                        display_name=f"Common Person{i}", email=f"c{i}@acme.test")

        with CaptureQueriesContext(connection) as captured:
            got = resolve_person_in_population(org.manager, "recognise Common")

        assert got is AMBIGUOUS, "120 genuine matches is a real ambiguity, not a guess"
        selects = [q["sql"] for q in captured.captured_queries if q["sql"].lstrip().upper().startswith("SELECT")]
        assert selects, "expected the lookup to hit the database"
        assert all("LIMIT" in sql.upper() for sql in selects), (
            "an unbounded SELECT would load the whole tenant into Python:\n"
            + "\n".join(s for s in selects if "LIMIT" not in s.upper())
        )


def test_a_disambiguation_list_stays_short_however_many_match(org):
    """120 matches must not become a 120-item question. The list is capped so the
    prompt stays usable — the user narrows it with a full name or an email."""
    with tenant_context(org.tenant):
        for i in range(120):
            UserFactory(tenant=org.tenant, role="EMPLOYEE",
                        display_name=f"Common Person{i}", email=f"c{i}@acme.test")
        options = suggest_candidates(org.manager, "recognise Common")
        assert 0 < len(options) <= 8
