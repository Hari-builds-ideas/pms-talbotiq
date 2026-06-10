"""
HTTP tests for the Live Org Chart API, hitting the REAL ``/api/org/...`` routes
(production urlconf — no ``@pytest.mark.urls``).

Themes:
  * the §2 scope tier over HTTP: TENANT (HRBP sees the whole tree + rollups),
    TEAM (manager sees their subtree, not the peer line), OWN (an employee sees
    only their line up to the root);
  * person-card / search scoping: an out-of-scope (or cross-tenant) target is a
    404 (never a 403 that leaks existence);
  * export;
  * the position lifecycle over HTTP: create (OPEN) → shows in vacancies → fill
    (FILLED) → drops out of vacancies → fill again (409) → close (CLOSED);
  * the status-code contract: 409 POSITION_ALREADY_FILLED, 422 INVALID_ORG_INPUT
    (a DRAFT JD link), 422 REPORTING_CYCLE (self / transitive);
  * the RBAC matrix over HTTP: MANAGE_POSITIONS / REASSIGN_REPORTING_LINE are
    HRBP+, so an employee and a manager are denied;
  * cache invalidation over HTTP: a reassignment is reflected by the next tree
    read;
  * cross-tenant isolation (404) and the unauthenticated 401.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import JobDescriptionFactory, UserFactory

pytestmark = pytest.mark.django_db

ORG = "/api/org/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _by_id(nodes):
    """Index a tree's node list by id for headcount/vacancy assertions."""
    return {n["id"]: n for n in nodes}


def _emails(nodes):
    return {n["email"] for n in nodes}


# ── scope over HTTP: TENANT / TEAM / OWN ───────────────────────────────────────


def test_hrbp_tree_is_tenant_wide_with_rollups(org):
    hrbp = _client_for(org.hrbp)
    resp = hrbp.get(f"{ORG}tree")
    assert resp.status_code == 200
    nodes = resp.json()["nodes"]

    # TENANT scope: all five users present.
    assert _emails(nodes) == {
        "admin@acme.test",
        "hrbp@acme.test",
        "manager@acme.test",
        "report@acme.test",
        "peer@acme.test",
    }

    by_id = _by_id(nodes)
    # hrbp's subtree: hrbp + manager + report + peer = 4.
    assert by_id[str(org.hrbp.id)]["headcount"] == 4
    # manager's subtree: manager + report = 2.
    assert by_id[str(org.manager.id)]["headcount"] == 2
    # admin is a separate root — just themselves.
    assert by_id[str(org.admin.id)]["headcount"] == 1


def test_employee_tree_is_own_line_only(org):
    emp = _client_for(org.report)
    nodes = emp.get(f"{ORG}tree").json()["nodes"]
    # OWN: own node + ancestor chain to the root (report → manager → hrbp).
    assert _emails(nodes) == {
        "report@acme.test",
        "manager@acme.test",
        "hrbp@acme.test",
    }
    assert "peer@acme.test" not in _emails(nodes)
    assert "admin@acme.test" not in _emails(nodes)


def test_manager_tree_is_subtree_plus_ancestors(org):
    mgr = _client_for(org.manager)
    nodes = mgr.get(f"{ORG}tree").json()["nodes"]
    # TEAM: self + subtree (report) + ancestor chain (hrbp) — never the peer.
    assert _emails(nodes) == {
        "manager@acme.test",
        "report@acme.test",
        "hrbp@acme.test",
    }
    assert "peer@acme.test" not in _emails(nodes)


# ── person-card scoping + cross-tenant ──────────────────────────────────────────


def test_person_card_in_scope_and_out_of_scope(org):
    hrbp = _client_for(org.hrbp)
    card = hrbp.get(f"{ORG}people/{org.manager.id}")
    assert card.status_code == 200
    body = card.json()
    assert body["email"] == "manager@acme.test"
    assert body["manager"]["email"] == "hrbp@acme.test"
    assert body["direct_reports"] == 1  # the report

    # report (OWN) cannot see peer (a different line) → 404, not 403.
    emp = _client_for(org.report)
    assert emp.get(f"{ORG}people/{org.peer.id}").status_code == 404


def test_person_card_cross_tenant_is_404(org, other_tenant):
    outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE")
    hrbp = _client_for(org.hrbp)
    assert hrbp.get(f"{ORG}people/{outsider.id}").status_code == 404


# ── search ──────────────────────────────────────────────────────────────────


def test_search_scopes_results(org):
    # HRBP (TENANT) finds the peer; report (OWN) is bounded to their own line.
    hrbp = _client_for(org.hrbp)
    hits = hrbp.get(f"{ORG}search?q=acme.test").json()
    assert "peer@acme.test" in {h["email"] for h in hits}

    emp = _client_for(org.report)
    emp_hits = emp.get(f"{ORG}search?q=acme.test").json()
    emails = {h["email"] for h in emp_hits}
    assert "peer@acme.test" not in emails
    assert emails <= {"report@acme.test", "manager@acme.test", "hrbp@acme.test"}


# ── export ────────────────────────────────────────────────────────────────────


def test_export_returns_tree(org):
    hrbp = _client_for(org.hrbp)
    resp = hrbp.get(f"{ORG}export")
    assert resp.status_code == 200
    assert "tree" in resp.json()


# ── position lifecycle over HTTP ────────────────────────────────────────────────


def test_position_create_fill_close_lifecycle(org):
    hrbp = _client_for(org.hrbp)

    # Create an OPEN position reporting to the manager.
    created = hrbp.post(
        f"{ORG}positions",
        {"title": "Backend Engineer", "reports_to": str(org.manager.id)},
        format="json",
    )
    assert created.status_code == 201
    position = created.json()
    assert position["status"] == "OPEN"
    assert position["title"] == "Backend Engineer"
    pos_id = position["id"]

    # It shows in vacancies.
    vac = hrbp.get(f"{ORG}vacancies").json()
    assert pos_id in {v["id"] for v in vac}

    # Fill it with the peer → FILLED.
    filled = hrbp.post(
        f"{ORG}positions/{pos_id}/fill",
        {"filled_by": str(org.peer.id)},
        format="json",
    )
    assert filled.status_code == 200
    assert filled.json()["status"] == "FILLED"
    assert filled.json()["filled_by"] == str(org.peer.id)

    # No longer a vacancy.
    vac_after = hrbp.get(f"{ORG}vacancies").json()
    assert pos_id not in {v["id"] for v in vac_after}

    # Filling again → 409 POSITION_ALREADY_FILLED.
    again = hrbp.post(
        f"{ORG}positions/{pos_id}/fill",
        {"filled_by": str(org.peer.id)},
        format="json",
    )
    assert again.status_code == 409
    assert again.json()["code"] == "POSITION_ALREADY_FILLED"

    # Close it → CLOSED.
    closed = hrbp.post(f"{ORG}positions/{pos_id}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"


def test_position_detail_round_trips(org):
    hrbp = _client_for(org.hrbp)
    pos_id = hrbp.post(
        f"{ORG}positions",
        {"title": "Data Scientist", "reports_to": str(org.manager.id)},
        format="json",
    ).json()["id"]
    detail = hrbp.get(f"{ORG}positions/{pos_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Data Scientist"


# ── RBAC: MANAGE_POSITIONS / REASSIGN_REPORTING_LINE are HRBP+ ─────────────────


def test_employee_cannot_create_position(org):
    emp = _client_for(org.report)  # EMPLOYEE lacks MANAGE_POSITIONS
    resp = emp.post(
        f"{ORG}positions",
        {"title": "X", "reports_to": str(org.manager.id)},
        format="json",
    )
    assert resp.status_code == 403


def test_manager_cannot_create_position(org):
    mgr = _client_for(org.manager)  # MANAGE_POSITIONS is HRBP+
    resp = mgr.post(
        f"{ORG}positions",
        {"title": "X", "reports_to": str(org.manager.id)},
        format="json",
    )
    assert resp.status_code == 403


def test_employee_cannot_reassign(org):
    emp = _client_for(org.report)  # EMPLOYEE lacks REASSIGN_REPORTING_LINE
    resp = emp.post(
        f"{ORG}reassign",
        {"user": str(org.report.id), "new_manager": str(org.peer.id)},
        format="json",
    )
    assert resp.status_code == 403


# ── link-jd: PUBLISHED ok / DRAFT 422 ─────────────────────────────────────────


def test_link_jd_published_ok_and_draft_422(org):
    hrbp = _client_for(org.hrbp)
    pos_id = hrbp.post(
        f"{ORG}positions",
        {"title": "Platform Engineer", "reports_to": str(org.manager.id)},
        format="json",
    ).json()["id"]

    published = JobDescriptionFactory(created_by=org.hrbp, status="PUBLISHED")
    linked = hrbp.post(
        f"{ORG}positions/{pos_id}/link-jd",
        {"jd": str(published.id)},
        format="json",
    )
    assert linked.status_code == 200
    assert linked.json()["published_jd"] == str(published.id)

    draft = JobDescriptionFactory(created_by=org.hrbp, status="DRAFT")
    bad = hrbp.post(
        f"{ORG}positions/{pos_id}/link-jd",
        {"jd": str(draft.id)},
        format="json",
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "INVALID_ORG_INPUT"


# ── reassignment over HTTP + cache invalidation ────────────────────────────────


def test_reassign_reflected_in_tree(org):
    hrbp = _client_for(org.hrbp)

    # Move report from manager → peer.
    resp = hrbp.post(
        f"{ORG}reassign",
        {"user": str(org.report.id), "new_manager": str(org.peer.id)},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["manager"] == str(org.peer.id)

    # The next tree read reflects it (cache invalidated over HTTP): report now
    # sits under peer, whose subtree headcount is 2 (peer + report).
    nodes = _by_id(hrbp.get(f"{ORG}tree").json()["nodes"])
    assert str(org.report.id) in nodes[str(org.peer.id)]["direct_report_ids"]
    assert nodes[str(org.peer.id)]["headcount"] == 2


def test_self_reassign_is_422_cycle(org):
    hrbp = _client_for(org.hrbp)
    resp = hrbp.post(
        f"{ORG}reassign",
        {"user": str(org.manager.id), "new_manager": str(org.manager.id)},
        format="json",
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "REPORTING_CYCLE"


def test_transitive_reassign_cycle_is_422(org):
    # Moving hrbp (a grandparent) under report (a grandchild) is a cycle.
    hrbp = _client_for(org.hrbp)
    resp = hrbp.post(
        f"{ORG}reassign",
        {"user": str(org.hrbp.id), "new_manager": str(org.report.id)},
        format="json",
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "REPORTING_CYCLE"


# ── cross-tenant isolation ─────────────────────────────────────────────────────


def test_cross_tenant_position_is_404(org, other_tenant):
    # A position in the other tenant is invisible to an org actor.
    outsider = UserFactory(tenant=other_tenant, role="HRBP")
    other_client = _client_for(outsider)
    # The org actor creates a position; the outsider cannot read it.
    hrbp = _client_for(org.hrbp)
    pos_id = hrbp.post(
        f"{ORG}positions",
        {"title": "In-tenant", "reports_to": str(org.manager.id)},
        format="json",
    ).json()["id"]

    assert other_client.get(f"{ORG}positions/{pos_id}").status_code == 404
    # And the outsider cannot see an org person via the person-card.
    assert other_client.get(f"{ORG}people/{org.manager.id}").status_code == 404


# ── auth ───────────────────────────────────────────────────────────────────────


def test_unauthenticated_tree_is_401(org):
    resp = APIClient().get(f"{ORG}tree")
    assert resp.status_code == 401
