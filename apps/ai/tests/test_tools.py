"""
The scoped read-tool set (AGENT_V3/A) — the contract the function-calling agent rests on.

Two properties are load-bearing and everything here exists to pin them down:

  * **Scope is not negotiable and not model-supplied.** Every data tool re-checks access
    on every call from the trusted context. An out-of-scope person yields a structured
    denial, never the data — and never an exception, because a denial is something the
    model has to be able to relay.
  * **The backend does the arithmetic.** Counts, averages, rankings and cycle deltas are
    asserted against hand-computed fixture values, so a wrong number fails here rather
    than being phrased confidently by a model.

Plus the properties that only bite at size: a fixed query count regardless of team size,
and bounded result sets.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ai.tools import (
    MAX_ROWS,
    ToolContext,
    compute_improvement,
    find_people,
    get_cycle_scores,
    get_my_team,
    get_person_kpis,
    get_person_overview,
    get_person_reviews,
    list_check_ins,
    rank_team,
    run_tool,
    team_aggregate,
    tool_schemas,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    KpiMeasurementFactory,
    ReviewFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _score(org, user, cycle, t_score, *, risk="ON_TRACK", behind=False, ago_days=0):
    from apps.goals.models import CycleScore

    return CycleScore.objects.create(
        tenant=org.tenant, employee=user, cycle=cycle,
        raw_score=Decimal(t_score), z_score=Decimal("0"), t_score=Decimal(t_score),
        cohort_size=10, risk_status=risk, pace_behind=behind,
        computed_at=timezone.now() - timedelta(days=ago_days),
    )


def _ctx(user):
    return ToolContext(caller=user)


# ── scope: the property the whole design rests on ────────────────────────────────


def test_every_data_tool_denies_an_out_of_scope_person(org):
    """A manager may FIND anyone in the company but may read only their own line.

    Asserted across every data tool at once: adding a tool that forgets the check is the
    obvious way this breaks, and a per-tool test would be silent about the new one.
    """
    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        _score(org, org.peer, cycle, "80")  # peer reports to the HRBP, not the manager
        ctx = _ctx(org.manager)
        pid = str(org.peer.id)

        for name in ("get_person_overview", "get_person_goals", "get_person_kpis",
                     "get_person_reviews", "get_cycle_scores", "get_feedback_summary",
                     "list_check_ins", "compute_improvement"):
            out = run_tool(ctx, name, {"person_id": pid})
            assert out.get("denied") is True, f"{name} leaked: {out}"
            assert "t_score" not in str(out) and "80" not in str(out)


def test_finding_someone_is_allowed_where_reading_them_is_not(org):
    """The directory/data split, in one test: the same person, findable and unreadable."""
    with tenant_context(org.tenant):
        org.peer.display_name = "Ingrid Garcia"
        org.peer.save(update_fields=["display_name"])
        ctx = _ctx(org.manager)

        found = find_people(ctx, "Ingrid Garcia")
        assert found["people"] and found["people"][0]["person_id"] == str(org.peer.id)
        assert "risk_status" not in found["people"][0]  # identity only

        assert get_person_overview(ctx, str(org.peer.id)).get("denied") is True


def test_a_tool_cannot_reach_another_tenant(org):
    """Tenant isolation comes from the scoped manager: a foreign id simply isn't there."""
    other = TenantFactory(slug="globex", name="Globex")
    with tenant_context(other):
        outsider = UserFactory(tenant=other, role="EMPLOYEE", display_name="Someone Else")
    with tenant_context(org.tenant):
        out = get_person_overview(_ctx(org.admin), str(outsider.id))
        assert out.get("denied") is not False and "Someone Else" not in str(out)


def test_the_model_is_never_offered_a_caller_argument(org):
    """Scope safety is structural: there is no vocabulary for "ask as somebody else".

    If a caller/tenant/role argument ever appears in a schema, the model can fill it, and
    the trusted-context guarantee is gone. Cheaper to assert than to notice later.
    """
    for schema in tool_schemas():
        params = schema["function"]["parameters"]["properties"]
        assert not ({"caller", "caller_id", "tenant", "tenant_id", "role", "as_user"}
                    & set(params)), schema["function"]["name"]


# ── the backend does the maths ───────────────────────────────────────────────────


@pytest.fixture
def team(org):
    """A five-person team with hand-chosen numbers, under a manager of its OWN.

    Deliberately not `org.manager`, who already has a report: every count below would
    then be "the spec, plus whatever the shared fixture happens to contain", and an
    assertion you have to adjust for background noise is one you stop trusting.
    """
    with tenant_context(org.tenant):
        boss = UserFactory(tenant=org.tenant, role="MANAGER", manager=org.hrbp,
                           display_name="Team Lead", email="lead@acme.test")
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        people = []
        # (t_score, risk, behind)
        spec = [("70", "ON_TRACK", False), ("60", "ON_TRACK", True),
                ("50", "AT_RISK", True), ("40", "CRITICAL", False),
                ("30", "AT_RISK", True)]
        for i, (t, risk, behind) in enumerate(spec):
            u = UserFactory(tenant=org.tenant, role="EMPLOYEE", manager=boss,
                            display_name=f"Member {i}", email=f"m{i}@acme.test")
            _score(org, u, cycle, t, risk=risk, behind=behind)
            people.append(u)
        return people, cycle, boss


def test_aggregates_match_a_hand_checked_fixture(org, team):
    """3 at risk, 3 behind pace, 1 clean, mean of 70/60/50/40/30 = 50."""
    people, _, boss = team
    with tenant_context(org.tenant):
        ctx = _ctx(boss)
        assert team_aggregate(ctx, "count_at_risk")["value"] == 3
        assert team_aggregate(ctx, "count_behind_pace")["value"] == 3
        assert team_aggregate(ctx, "count_on_track")["value"] == 1
        assert team_aggregate(ctx, "average_score")["value"] == 50.0
        assert team_aggregate(ctx, "team_size")["value"] == len(people)


def test_an_unknown_metric_is_refused_rather_than_guessed(org, team):
    """The model asking for something we don't compute must get an error it can relay —
    not a silent fallback to some other metric, which would be a confidently wrong
    answer to a question nobody asked."""
    with tenant_context(org.tenant):
        out = team_aggregate(_ctx(team[2]), "median_vibes")
        assert "error" in out and "median_vibes" in out["error"]


def test_ranking_is_ordered_by_the_backend_with_its_numbers(org, team):
    with tenant_context(org.tenant):
        ctx = _ctx(team[2])
        best = rank_team(ctx, metric="score", order="desc", limit=2)
        assert [r["value"] for r in best["ranked"]] == [70.0, 60.0]
        worst = rank_team(ctx, metric="score", order="asc", limit=2)
        assert [r["value"] for r in worst["ranked"]] == [30.0, 40.0]
        assert worst["ranked"][0]["name"] == "Member 4"


def test_improvement_is_a_backend_delta_not_a_model_subtraction(org, team):
    """The headline open-ended question — "who improved most since last cycle" — is a
    subtraction over score pairs plus a sort, and both happen in Python."""
    people, _current, boss = team
    with tenant_context(org.tenant):
        previous = CycleFactory(tenant=org.tenant, status="CLOSED", name="H1")
        # Member 0: 40 → 70 (+30). Member 1: 65 → 60 (−5). Others: one score only.
        _score(org, people[0], previous, "40", ago_days=90)
        _score(org, people[1], previous, "65", ago_days=90)

        out = compute_improvement(_ctx(boss))
        assert out["ranked"][0]["name"] == "Member 0"
        assert out["ranked"][0]["delta"] == 30.0
        assert out["ranked"][0]["direction"] == "improved"
        assert out["compared"] == 2  # only people with a PAIR are comparable
        assert out["ranked"][-1]["delta"] == -5.0
        assert out["ranked"][-1]["direction"] == "declined"


def test_one_score_is_never_reported_as_improvement(org, team):
    """A person with a single score has not improved. Comparing a score against nothing
    is the exact shape of a fabricated trend, so it must return no-data instead."""
    people, _cycle, boss = team
    with tenant_context(org.tenant):
        out = compute_improvement(_ctx(boss), person_id=str(people[2].id))
        assert out.get("empty") is True and "delta" not in out


def test_attainment_comes_from_the_backend_not_the_raw_rows(org):
    """A KPI at 45 against a target of 90 is 50% — and the tool says so, rather than
    handing the model two numbers and hoping."""
    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        goal = GoalFactory(employee=org.report, cycle=cycle, status="ACTIVE",
                           title="Ship the platform")
        kpi = KpiFactory(goal=goal, name="Features delivered", target_value=Decimal("90"))
        KpiMeasurementFactory(kpi=kpi, value=Decimal("45"))

        out = get_person_kpis(_ctx(org.manager), str(org.report.id))
        assert out["kpis"][0]["attainment_pct"] == pytest.approx(50.0, abs=0.5)
        assert out["kpis"][0]["target"] == 90.0


# ── honest emptiness ─────────────────────────────────────────────────────────────


def test_no_data_is_said_plainly_rather_than_left_ambiguous(org):
    """An empty result must be UNAMBIGUOUSLY empty. A bare {} invites the model to fill
    the silence; an explicit marker gives it something true to say."""
    with tenant_context(org.tenant):
        ctx = _ctx(org.manager)
        assert get_cycle_scores(ctx, str(org.report.id)).get("empty") is True
        assert get_person_reviews(ctx, str(org.report.id)).get("empty") is True
        assert list_check_ins(ctx, str(org.report.id)).get("empty") is True


def test_someone_with_no_reports_is_told_so(org):
    with tenant_context(org.tenant):
        out = get_my_team(_ctx(org.report))
        assert out["manages"] is False and "reason" in out


def test_an_unknown_tool_or_bad_argument_is_structured_not_an_exception(org):
    """The loop must always have something to hand back to the model."""
    with tenant_context(org.tenant):
        ctx = _ctx(org.manager)
        assert "error" in run_tool(ctx, "get_everyones_salary", {})
        assert "error" in run_tool(ctx, "get_person_overview", {"nonsense": 1})


# ── scale ────────────────────────────────────────────────────────────────────────


def _make_team(org, size, cycle, tag="a"):
    people = []
    for i in range(size):
        u = UserFactory(tenant=org.tenant, role="EMPLOYEE", manager=org.manager,
                        display_name=f"Scale Person {tag}{i}", email=f"sp{tag}{i}@acme.test")
        _score(org, u, cycle, "50")
        people.append(u)
    return people


def test_team_tools_cost_the_same_number_of_queries_at_any_team_size(org):
    """The property that makes 5,000 people behave like 5.

    ``insight._subtree_latest_scores`` issues one score query PER PERSON; that is fine on
    a fixture and ruinous on a real org, so the team tools resolve scores in bulk. Asserted
    as "constant", not as an exact count — pinning the number turns an optimisation into a
    failure.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        _make_team(org, 3, cycle, "small")
        with CaptureQueriesContext(connection) as small:
            team_aggregate(_ctx(org.manager), "count_at_risk")

        _make_team(org, 60, cycle, "big")
        with CaptureQueriesContext(connection) as large:
            team_aggregate(_ctx(org.manager), "count_at_risk")

    assert len(large.captured_queries) == len(small.captured_queries), (
        f"query count grew with team size: {len(small.captured_queries)} → "
        f"{len(large.captured_queries)} — an N+1 crept in"
    )


def test_results_are_bounded_however_big_the_team(org):
    """Context is finite: a 200-person team must not become a 200-row tool result."""
    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        made = _make_team(org, MAX_ROWS + 20, cycle)
        out = get_my_team(_ctx(org.manager))
        assert out["team_size"] >= len(made)          # the true size is still reported
        assert len(out["members"]) <= MAX_ROWS        # but the payload is capped
        assert out["truncated"] is True               # and says so, rather than lying


def test_reviews_expose_state_but_never_the_written_text(org):
    """Scope is not only about people — it is about fields. The agent needs to know a
    review is open; it has no business relaying its contents into a chat reply."""
    with tenant_context(org.tenant):
        cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
        ReviewFactory(employee=org.report, cycle=cycle, state="DRAFT",
                      draft_body="CONFIDENTIAL: he is being managed out")
        out = get_person_reviews(_ctx(org.manager), str(org.report.id))
        assert out["open_count"] == 1
        assert "CONFIDENTIAL" not in str(out) and "managed out" not in str(out)
