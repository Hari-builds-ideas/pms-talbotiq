"""
HTTP tests for the Admin Hub API, hitting the REAL ``/api/admin/...`` routes
(production urlconf, no ``@pytest.mark.urls``).

Themes:
  * the full Admin lifecycle over HTTP: create user → list → set role →
    deactivate → reactivate → reassign reporting line → tenant config GET/PUT;
  * a reporting CYCLE → 422 (the reused Module-7 cycle check);
  * EVERY endpoint is Admin-only (HRBP / manager / employee → 403);
  * cross-tenant: an Admin acting on a user id from another tenant → 404 (the
    tenant-scoped manager hides it);
  * input validation: duplicate email → 422, unknown role → 422;
  * the unauthenticated 401.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db

USERS = "/api/admin/users"
USER_STATS = "/api/admin/users/stats"
TENANT_CONFIG = "/api/admin/tenant-config"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


# ── create / list / role / (de)activate ───────────────────────────────────────


def test_create_user_then_list(org):
    admin = _client_for(org.admin)
    resp = admin.post(
        USERS,
        {"email": "newhire@acme.test", "role": "EMPLOYEE", "manager": str(org.manager.id)},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    created = resp.json()
    assert created["email"] == "newhire@acme.test"
    assert created["role"] == "EMPLOYEE"
    assert created["manager"] == str(org.manager.id)

    listed = admin.get(USERS)
    assert listed.status_code == 200, listed.content
    emails = {u["email"] for u in listed.json()}
    assert "newhire@acme.test" in emails


def test_set_role_deactivate_reactivate(org):
    admin = _client_for(org.admin)
    rid = str(org.report.id)

    resp = admin.post(f"{USERS}/{rid}/role", {"role": "MANAGER"}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["role"] == "MANAGER"

    resp = admin.post(f"{USERS}/{rid}/deactivate", {}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_active"] is False

    resp = admin.post(f"{USERS}/{rid}/reactivate", {}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_active"] is True


# ── reporting line (+ cycle) ───────────────────────────────────────────────────


def test_reporting_line_move_then_cycle_is_422(org):
    admin = _client_for(org.admin)

    # Move org.peer (under hrbp) to report to org.manager — no cycle → 200.
    resp = admin.post(
        f"{USERS}/{org.peer.id}/reporting-line",
        {"manager": str(org.manager.id)},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["manager"] == str(org.manager.id)

    # Reassign org.manager under org.report (manager's own report) — a CYCLE → 422.
    resp = admin.post(
        f"{USERS}/{org.manager.id}/reporting-line",
        {"manager": str(org.report.id)},
        format="json",
    )
    assert resp.status_code == 422, resp.content


# ── tenant config ──────────────────────────────────────────────────────────────


def test_tenant_config_get_then_put_reflects(org):
    admin = _client_for(org.admin)

    resp = admin.get(TENANT_CONFIG)
    assert resp.status_code == 200, resp.content
    assert resp.json()["settings"] == {}

    resp = admin.put(
        TENANT_CONFIG, {"settings": {"locale": "en-GB", "weekStart": "MON"}}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["settings"]["locale"] == "en-GB"

    resp = admin.get(TENANT_CONFIG)
    assert resp.json()["settings"] == {"locale": "en-GB", "weekStart": "MON"}


# ── user stats (DB-aggregated; the dashboard's bounded substitute for the list) ─


def test_user_stats_counts_match_and_track_deactivation(org):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    admin = _client_for(org.admin)

    # org fixture: admin, hrbp, manager, report, peer — all active.
    resp = admin.get(USER_STATS)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["total"] == 5
    assert body["active"] == 5
    assert body["inactive"] == 0
    assert body["active_by_role"] == {"ADMIN": 1, "HRBP": 1, "MANAGER": 1, "EMPLOYEE": 2}

    # Deactivating a user moves them out of active + into inactive.
    assert admin.post(f"{USERS}/{org.peer.id}/deactivate", {}, format="json").status_code == 200
    body = admin.get(USER_STATS).json()
    assert body["active"] == 4
    assert body["inactive"] == 1
    assert body["active_by_role"]["EMPLOYEE"] == 1

    # The whole rollup is a single GROUP BY — not an O(users) download.
    with CaptureQueriesContext(connection) as ctx:
        admin.get(USER_STATS)
    aggregate_qs = [q for q in ctx.captured_queries if "GROUP BY" in q["sql"].upper()]
    assert len(aggregate_qs) == 1


# ── Admin-only: every endpoint 403 for a non-Admin ─────────────────────────────


@pytest.mark.parametrize("role", ["HRBP", "MANAGER", "EMPLOYEE"])
def test_every_admin_endpoint_is_403_for_non_admin(org, role):
    actor = {"HRBP": org.hrbp, "MANAGER": org.manager, "EMPLOYEE": org.report}[role]
    client = _client_for(actor)
    rid = str(org.report.id)

    assert client.get(USERS).status_code == 403
    assert client.get(USER_STATS).status_code == 403
    assert (
        client.post(USERS, {"email": "x@acme.test", "role": "EMPLOYEE"}, format="json").status_code
        == 403
    )
    assert client.post(f"{USERS}/{rid}/role", {"role": "MANAGER"}, format="json").status_code == 403
    assert client.post(f"{USERS}/{rid}/deactivate", {}, format="json").status_code == 403
    assert client.post(f"{USERS}/{rid}/reactivate", {}, format="json").status_code == 403
    assert (
        client.post(
            f"{USERS}/{rid}/reporting-line", {"manager": str(org.manager.id)}, format="json"
        ).status_code
        == 403
    )
    assert client.get(TENANT_CONFIG).status_code == 403
    assert client.put(TENANT_CONFIG, {"settings": {}}, format="json").status_code == 403


# ── cross-tenant → 404 ─────────────────────────────────────────────────────────


def test_cross_tenant_target_is_404(org, other_tenant):
    admin = _client_for(org.admin)
    outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE")
    # The admin's tenant-scoped manager cannot see the outsider → 404.
    assert (
        admin.post(f"{USERS}/{outsider.id}/role", {"role": "MANAGER"}, format="json").status_code
        == 404
    )
    assert admin.post(f"{USERS}/{outsider.id}/deactivate", {}, format="json").status_code == 404


# ── input validation → 422 ─────────────────────────────────────────────────────


def test_duplicate_email_is_422(org):
    admin = _client_for(org.admin)
    body = {"email": "dupe@acme.test", "role": "EMPLOYEE"}
    assert admin.post(USERS, body, format="json").status_code == 201
    assert admin.post(USERS, body, format="json").status_code == 422


def test_unknown_role_is_422(org):
    admin = _client_for(org.admin)
    resp = admin.post(USERS, {"email": "wiz@acme.test", "role": "WIZARD"}, format="json")
    assert resp.status_code == 422


# ── unauthenticated → 401 ──────────────────────────────────────────────────────


def test_unauthenticated_is_401(org):
    assert APIClient().get(USERS).status_code == 401
