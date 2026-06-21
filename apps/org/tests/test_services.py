"""
Org-chart services — scope, rollups, vacancy lifecycle, reassignment + cycle
detection, person card / search, JD link, cache invalidation, tenant isolation.

The tree is computed from ``User.manager`` (active users only); Position models
vacancies. Everything is scope-bounded (OWN line / TEAM subtree / TENANT) and the
expensive full-tree build is cached per tenant.
"""
import pytest

from apps.org import positions, reassign, services
from apps.org.exceptions import (
    IllegalPositionTransition,
    InvalidOrgInput,
    PositionAlreadyFilled,
    ReportingCycle,
)
from apps.org.models import Position
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import JobDescriptionFactory, UserFactory

pytestmark = pytest.mark.django_db


def _emails(tree):
    return {n["email"] for n in tree["nodes"]}


def _node(tree, email):
    return next(n for n in tree["nodes"] if n["email"] == email)


# ── scope ──────────────────────────────────────────────────────────────────


def test_hrbp_sees_full_tenant_tree(org):
    with tenant_context(org.tenant):
        tree = services.build_org_tree(org.hrbp)
    emails = _emails(tree)
    assert {"admin@acme.test", "hrbp@acme.test", "manager@acme.test",
            "report@acme.test", "peer@acme.test"} <= emails
    # admin and hrbp are roots (manager=null).
    root_emails = {_node(tree, e)["email"] for e in emails
                   if _node(tree, e)["id"] in tree["roots"]}
    assert {"admin@acme.test", "hrbp@acme.test"} <= root_emails


def test_tree_nodes_carry_display(org):
    """Every node exposes ``display`` (display_name when set, else email) so the
    org chart renders names — never a bare email/uuid. The client ``OrgNode``
    type requires this field; a node without it blanks the chart."""
    with tenant_context(org.tenant):
        org.manager.display_name = "Grace Hopper"
        org.manager.save(update_fields=["display_name", "updated_at"])
        services.invalidate_org_cache(org.tenant)  # drop any warm tree
        tree = services.build_org_tree(org.hrbp)
    assert all(n.get("display") for n in tree["nodes"])  # present on every node
    assert _node(tree, "manager@acme.test")["display"] == "Grace Hopper"  # name wins
    assert _node(tree, "report@acme.test")["display"] == "report@acme.test"  # email fallback


def test_tree_wire_shape_list_nodes_and_from_to_edges(org):
    """Lock the wire shape the web client normalizes against: ``nodes`` is a LIST
    of node dicts (each with ``id``), ``edges`` a list of ``{from,to}`` dicts
    (manager→report), ``roots`` a list of id strings. The client builds its
    id→node map + child map from exactly this — a drift here re-breaks the chart
    ("not iterable")."""
    with tenant_context(org.tenant):
        tree = services.build_org_tree(org.hrbp)
    assert isinstance(tree["nodes"], list)
    assert all(isinstance(n, dict) and "id" in n for n in tree["nodes"])
    assert isinstance(tree["edges"], list)
    assert all(set(e) == {"from", "to"} for e in tree["edges"])
    assert isinstance(tree["roots"], list)
    ids = {n["id"] for n in tree["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in tree["edges"])  # edges visible-only
    assert all(r in ids for r in tree["roots"])  # roots are node ids


def test_employee_sees_only_their_reporting_line(org):
    with tenant_context(org.tenant):
        tree = services.build_org_tree(org.report)
    # own node + ancestor chain (manager -> hrbp); NOT peer, NOT admin.
    assert _emails(tree) == {"report@acme.test", "manager@acme.test", "hrbp@acme.test"}


def test_manager_sees_subtree_plus_ancestors_not_peers(org):
    with tenant_context(org.tenant):
        tree = services.build_org_tree(org.manager)
    # self + subtree (report) + ancestor (hrbp); peer reports to hrbp, not manager.
    assert _emails(tree) == {"manager@acme.test", "report@acme.test", "hrbp@acme.test"}
    assert "peer@acme.test" not in _emails(tree)


def test_no_cross_tenant_node_ever_appears(org, other_tenant):
    UserFactory(tenant=other_tenant, role="HRBP", email="outsider@other.test")
    with tenant_context(org.tenant):
        tree = services.build_org_tree(org.hrbp)
    assert all(not n["email"].endswith("@other.test") for n in tree["nodes"])


# ── rollups ────────────────────────────────────────────────────────────────


def test_headcount_is_transitive_active_reports(org):
    with tenant_context(org.tenant):
        tree = services.build_org_tree(org.hrbp)
    # hrbp -> manager -> report ; hrbp -> peer  => hrbp subtree = 4 (incl self).
    assert _node(tree, "hrbp@acme.test")["headcount"] == 4
    assert _node(tree, "manager@acme.test")["headcount"] == 2  # manager + report
    assert _node(tree, "report@acme.test")["headcount"] == 1
    assert _node(tree, "admin@acme.test")["headcount"] == 1


def test_deactivated_user_excluded_from_tree_and_rollups(org):
    with tenant_context(org.tenant):
        org.report.is_active = False
        org.report.save(update_fields=["is_active", "updated_at"])
        services.invalidate_org_cache(org.tenant)
        tree = services.build_org_tree(org.hrbp)
    assert "report@acme.test" not in _emails(tree)
    assert _node(tree, "manager@acme.test")["headcount"] == 1  # report gone
    assert _node(tree, "hrbp@acme.test")["headcount"] == 3


def test_vacancy_rollup_counts_open_positions_in_subtree(org):
    with tenant_context(org.tenant):
        positions.create_position(org.hrbp, title="SRE", reports_to=org.manager)
        positions.create_position(org.hrbp, title="SRE II", reports_to=org.manager)
        tree = services.build_org_tree(org.hrbp)
    # two OPEN positions under manager -> roll up to manager and hrbp.
    assert _node(tree, "manager@acme.test")["vacancies"] == 2
    assert _node(tree, "hrbp@acme.test")["vacancies"] == 2
    assert _node(tree, "peer@acme.test")["vacancies"] == 0


# ── vacancy lifecycle ────────────────────────────────────────────────────────


def test_vacancy_lifecycle_create_fill_close(org):
    with tenant_context(org.tenant):
        pos = positions.create_position(org.hrbp, title="Backend Eng", reports_to=org.manager)
        assert pos.status == "OPEN"
        vac = services.list_vacancies(org.hrbp)
        assert any(v["id"] == str(pos.id) for v in vac)

        # fill -> FILLED, vacancy clears.
        positions.fill_position(org.hrbp, pos, org.peer)
        pos.refresh_from_db()
        assert pos.status == "FILLED" and pos.filled_by_id == org.peer.id
        assert pos.filled_at is not None
        assert all(v["id"] != str(pos.id) for v in services.list_vacancies(org.hrbp))

        # filling a FILLED position -> 409 POSITION_ALREADY_FILLED.
        with pytest.raises(PositionAlreadyFilled):
            positions.fill_position(org.hrbp, pos, org.report)

        # close -> removed from vacancies (already not a vacancy; closing a FILLED).
        positions.close_position(org.hrbp, pos)
        pos.refresh_from_db()
        assert pos.status == "CLOSED"


def test_close_open_vacancy_removes_it(org):
    with tenant_context(org.tenant):
        pos = positions.create_position(org.hrbp, title="Temp", reports_to=org.manager)
        positions.close_position(org.hrbp, pos)
        assert services.list_vacancies(org.hrbp) == [] or all(
            v["id"] != str(pos.id) for v in services.list_vacancies(org.hrbp)
        )
        # closing a CLOSED position -> 409.
        with pytest.raises(IllegalPositionTransition):
            positions.close_position(org.hrbp, pos)


# ── reassignment + cycles ────────────────────────────────────────────────────


def test_reassign_updates_tree_and_rollups(org):
    with tenant_context(org.tenant):
        services.build_org_tree(org.hrbp)  # warm
        reassign.reassign_reporting_line(org.hrbp, org.report, org.peer)
        org.report.refresh_from_db()
        assert org.report.manager_id == org.peer.id
        tree = services.build_org_tree(org.hrbp)
    # report now sits under peer; manager's subtree shrank, peer's grew.
    assert _node(tree, "manager@acme.test")["headcount"] == 1
    assert _node(tree, "peer@acme.test")["headcount"] == 2


def test_reassign_to_self_is_cycle_422(org):
    with tenant_context(org.tenant):
        with pytest.raises(ReportingCycle):
            reassign.reassign_reporting_line(org.hrbp, org.manager, org.manager)


def test_reassign_transitive_cycle_grandparent_under_grandchild_422(org):
    # hrbp -> manager -> report. Moving hrbp under report would loop.
    with tenant_context(org.tenant):
        with pytest.raises(ReportingCycle):
            reassign.reassign_reporting_line(org.hrbp, org.hrbp, org.report)


def test_reassign_to_inactive_manager_422(org):
    with tenant_context(org.tenant):
        org.peer.is_active = False
        org.peer.save(update_fields=["is_active", "updated_at"])
        with pytest.raises(InvalidOrgInput):
            reassign.reassign_reporting_line(org.hrbp, org.report, org.peer)


def test_reassign_cross_tenant_manager_422(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="MANAGER", email="out@other.test")
    with tenant_context(org.tenant):
        with pytest.raises(InvalidOrgInput):
            reassign.reassign_reporting_line(org.hrbp, org.report, outsider)


# ── person card / search ─────────────────────────────────────────────────────


def test_person_card_out_of_scope_is_404(org):
    from rest_framework.exceptions import NotFound

    with tenant_context(org.tenant):
        with pytest.raises(NotFound):
            services.person_card(org.report, org.peer.id)  # peer not in report's line


def test_person_card_in_scope_returns_detail(org):
    with tenant_context(org.tenant):
        card = services.person_card(org.hrbp, org.manager.id)
    assert card["email"] == "manager@acme.test"
    assert card["manager"]["email"] == "hrbp@acme.test"
    assert card["direct_reports"] == 1  # report


def test_person_card_includes_filled_position_title(org):
    with tenant_context(org.tenant):
        pos = positions.create_position(org.hrbp, title="Principal SRE", reports_to=org.hrbp)
        positions.fill_position(org.hrbp, pos, org.manager)
        card = services.person_card(org.hrbp, org.manager.id)
    assert card["title"] == "Principal SRE"
    assert card["filled_positions"][0]["title"] == "Principal SRE"


def test_search_is_scope_bounded(org):
    with tenant_context(org.tenant):
        hrbp_hits = {p["email"] for p in services.search_people(org.hrbp, "acme.test")}
        report_hits = {p["email"] for p in services.search_people(org.report, "acme.test")}
    assert "peer@acme.test" in hrbp_hits
    # the employee's search is bounded to their own line.
    assert report_hits == {"report@acme.test", "manager@acme.test", "hrbp@acme.test"}


# ── JD link ──────────────────────────────────────────────────────────────────


def test_link_published_jd(org):
    jd = JobDescriptionFactory(created_by=org.hrbp, status="PUBLISHED")
    with tenant_context(org.tenant):
        pos = positions.create_position(org.hrbp, title="Eng", reports_to=org.manager)
        positions.link_jd(org.hrbp, pos, jd)
        pos.refresh_from_db()
    assert pos.published_jd_id == jd.id


def test_link_draft_jd_is_422(org):
    jd = JobDescriptionFactory(created_by=org.hrbp, status="DRAFT")
    with tenant_context(org.tenant):
        pos = positions.create_position(org.hrbp, title="Eng", reports_to=org.manager)
        with pytest.raises(InvalidOrgInput):
            positions.link_jd(org.hrbp, pos, jd)


def test_link_cross_tenant_jd_is_422(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="HRBP", email="out2@other.test")
    foreign_jd = JobDescriptionFactory(created_by=outsider, status="PUBLISHED")
    with tenant_context(org.tenant):
        pos = positions.create_position(org.hrbp, title="Eng", reports_to=org.manager)
        with pytest.raises(InvalidOrgInput):
            positions.link_jd(org.hrbp, pos, foreign_jd)


# ── cache ────────────────────────────────────────────────────────────────────


def test_tree_is_cached_second_read_hits_no_db(org, django_assert_num_queries):
    with tenant_context(org.tenant):
        services.build_org_tree(org.hrbp)  # warm the cache (issues queries)
        with django_assert_num_queries(0):
            services.build_org_tree(org.hrbp)  # served purely from cache


def test_create_position_invalidates_cached_tree_vacancy_rollup(org):
    # Warm the tree FIRST (vacancy rollup 0), then create an OPEN position: the
    # next tree read must reflect it (create_position invalidates the cache).
    with tenant_context(org.tenant):
        warm = services.build_org_tree(org.hrbp)
        assert _node(warm, "manager@acme.test")["vacancies"] == 0
        positions.create_position(org.hrbp, title="SRE", reports_to=org.manager)
        after = services.build_org_tree(org.hrbp)
    assert _node(after, "manager@acme.test")["vacancies"] == 1
    assert _node(after, "hrbp@acme.test")["vacancies"] == 1


def test_write_invalidates_cache_next_read_reflects_change(org):
    with tenant_context(org.tenant):
        before = services.build_org_tree(org.hrbp)
        assert _node(before, "peer@acme.test")["headcount"] == 1
        reassign.reassign_reporting_line(org.hrbp, org.report, org.peer)
        after = services.build_org_tree(org.hrbp)
    assert _node(after, "peer@acme.test")["headcount"] == 2  # cache was invalidated


# ── isolation ────────────────────────────────────────────────────────────────


def test_position_is_tenant_scoped(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="HRBP", email="out3@other.test")
    with tenant_context(other_tenant):
        positions.create_position(outsider, title="Foreign", reports_to=outsider)
    with tenant_context(org.tenant):
        assert Position.objects.count() == 0  # other tenant's position invisible
