"""
RW_BUILD_3 — Weekly Check-ins. The load-bearing tests are SCOPE (a manager sees +
responds to only their reports' check-ins; cross-manager / peer → 404) and TENANT
isolation. Plus: one check-in per (author, week), priorities replace on re-submit,
manager response is one-per-check-in, and the goal-progress pull is READ-ONLY.

Org under tenant t:  hrbp ──► mgrA ──► empA ;  hrbp ──► mgrB ──► empB
"""
import datetime

import pytest
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.checkins.models import CheckIn, ManagerResponse
from apps.checkins.services import (
    checkin_goal_progress,
    get_readable_checkin,
    my_checkins,
    respond_to_checkin,
    team_checkins,
    upsert_checkin,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    GoalFactory,
    KpiFactory,
    KpiMeasurementFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

WEEK = datetime.date(2026, 6, 22)  # a Monday


@pytest.fixture
def org(db):
    from types import SimpleNamespace

    t = TenantFactory(slug="acme", name="Acme")
    with tenant_context(t):
        hrbp = UserFactory(tenant=t, role="HRBP", email="hrbp@acme.test")
        mgrA = UserFactory(tenant=t, role="MANAGER", email="mgra@acme.test", manager=hrbp)
        mgrB = UserFactory(tenant=t, role="MANAGER", email="mgrb@acme.test", manager=hrbp)
        empA = UserFactory(tenant=t, role="EMPLOYEE", email="empa@acme.test", manager=mgrA)
        empB = UserFactory(tenant=t, role="EMPLOYEE", email="empb@acme.test", manager=mgrB)
    return SimpleNamespace(t=t, hrbp=hrbp, mgrA=mgrA, mgrB=mgrB, empA=empA, empB=empB)


def test_one_checkin_per_author_per_week(org):
    with tenant_context(org.t):
        upsert_checkin(org.empA, week_of=WEEK, mood=3, wins="shipped")
        upsert_checkin(org.empA, week_of=WEEK, mood=5, wins="shipped more")  # same week → update
        rows = CheckIn.objects.filter(author_id=org.empA.id)
        assert rows.count() == 1
        assert rows.first().mood == 5


def test_mood_must_be_1_to_5(org):
    with tenant_context(org.t):
        for bad in (0, 6, "x", None):
            with pytest.raises(ValidationError):
                upsert_checkin(org.empA, week_of=WEEK, mood=bad)


def test_priorities_replace_on_resubmit(org):
    with tenant_context(org.t):
        ci = upsert_checkin(
            org.empA, week_of=WEEK, mood=3,
            priorities=[{"text": "A", "status": "ACTIVE"}, {"text": "B", "status": "DONE"}],
        )
        assert ci.priorities.count() == 2
        ci = upsert_checkin(org.empA, week_of=WEEK, mood=3, priorities=[{"text": "C", "status": "CARRY_FORWARD"}])
        texts = sorted(p.text for p in ci.priorities.all())
        assert texts == ["C"]  # replaced, not appended


def test_manager_sees_only_their_reports(org):
    with tenant_context(org.t):
        ciA = upsert_checkin(org.empA, week_of=WEEK, mood=4)
        upsert_checkin(org.empB, week_of=WEEK, mood=2)
        a_ids = {c.id for c in team_checkins(org.mgrA)}
        b_ids = {c.id for c in team_checkins(org.mgrB)}
        assert ciA.id in a_ids and len(a_ids) == 1   # mgrA sees empA only
        assert ciA.id not in b_ids                    # mgrB never sees empA's


def test_cross_manager_and_peer_detail_is_404(org):
    with tenant_context(org.t):
        ciA = upsert_checkin(org.empA, week_of=WEEK, mood=4)
        assert get_readable_checkin(org.mgrA, ciA.id).id == ciA.id   # own manager OK
        assert get_readable_checkin(org.empA, ciA.id).id == ciA.id   # author OK
        with pytest.raises(NotFound):
            get_readable_checkin(org.mgrB, ciA.id)   # other manager
        with pytest.raises(NotFound):
            get_readable_checkin(org.empB, ciA.id)   # a peer


def test_manager_response_rules(org):
    with tenant_context(org.t):
        ciA = upsert_checkin(org.empA, week_of=WEEK, mood=4)
        # mgrA responds to their report → one response, upsert on re-respond.
        respond_to_checkin(org.mgrA, ciA.id, comment="nice", follow_up=True)
        respond_to_checkin(org.mgrA, ciA.id, comment="updated", add_to_one_on_one=True)
        assert ManagerResponse.objects.filter(check_in=ciA).count() == 1
        resp = ManagerResponse.objects.get(check_in=ciA)
        assert resp.comment == "updated" and resp.add_to_one_on_one is True
        # mgrB (out of scope) → 404, never reveals.
        with pytest.raises(NotFound):
            respond_to_checkin(org.mgrB, ciA.id, comment="nope")
        # Can't respond to your own check-in.
        ciMgr = upsert_checkin(org.mgrA, week_of=WEEK, mood=3)
        with pytest.raises(PermissionDenied):
            respond_to_checkin(org.mgrA, ciMgr.id, comment="self")


def test_tenant_isolation(org):
    other = TenantFactory(slug="globex", name="Globex")
    with tenant_context(other):
        outsider_mgr = UserFactory(tenant=other, role="MANAGER", email="m@globex.test")
    with tenant_context(org.t):
        ciA = upsert_checkin(org.empA, week_of=WEEK, mood=4)
    with tenant_context(other):
        assert list(team_checkins(outsider_mgr)) == []      # no acme rows
        with pytest.raises(NotFound):
            get_readable_checkin(outsider_mgr, ciA.id)       # acme card invisible


def test_goal_progress_is_readonly_pull(org):
    with tenant_context(org.t):
        cycle = CycleFactory(tenant=org.t, status="ACTIVE")
        goal = GoalFactory(employee=org.empA, cycle=cycle, title="Ship the thing", status="ACTIVE")
        kpi = KpiFactory(goal=goal, target_value="100.0000")
        KpiMeasurementFactory(kpi=kpi, value="80.0000")
        before = CheckIn.objects.count()
        progress = checkin_goal_progress(org.empA)
        after = CheckIn.objects.count()
    assert after == before  # pure read — created nothing
    assert any(p["goal"] == "Ship the thing" and p["attainment_pct"] == 80 for p in progress)


def test_my_checkins_returns_own_only(org):
    with tenant_context(org.t):
        upsert_checkin(org.empA, week_of=WEEK, mood=4)
        upsert_checkin(org.empB, week_of=WEEK, mood=2)
        mine = list(my_checkins(org.empA))
        assert len(mine) == 1 and mine[0].author_id == org.empA.id
