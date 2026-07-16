"""PROD_B — bulk employee onboarding/import.

Admins/HRBPs can onboard large tenants from CSV/JSON without weakening tenant
isolation: rows are upserted inside the actor's tenant, reporting lines resolve by
manager email in the same tenant, role escalation is capped, and seat limits are
server-enforced.
"""
import io

import pytest
from rest_framework.test import APIClient

from apps.billing import services as billing_services
from apps.identity.models import User
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

IMPORT = "/api/admin/users/import"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_bulk_import_creates_updates_and_links_reporting_lines_within_tenant(org):
    admin = _client_for(org.admin)
    rows = [
        {
            "name": "Mira Manager",
            "email": "mira@acme.test",
            "role": "MANAGER",
            "department": "Sales",
            "designation": "Director",
        },
        {
            "name": "Ravi Report",
            "email": "ravi@acme.test",
            "role": "EMPLOYEE",
            "department": "Sales",
            "designation": "AE",
            "manager": "mira@acme.test",
        },
    ]

    resp = admin.post(IMPORT, {"rows": rows}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 2
    assert resp.json()["updated"] == 0
    assert resp.json()["errors"] == []
    with tenant_context(org.tenant.id):
        manager = User.objects.get(email="mira@acme.test")
        report = User.objects.get(email="ravi@acme.test")
        assert manager.role == User.Role.MANAGER
        assert manager.department == "Sales"
        assert manager.title == "Director"
        assert report.manager_id == manager.id
        assert not report.has_usable_password()

    # Idempotent: re-importing updates by email instead of duplicating.
    rows[1]["designation"] = "Senior AE"
    resp2 = admin.post(IMPORT, {"rows": rows}, format="json")
    assert resp2.status_code == 200
    assert resp2.json()["created"] == 0
    assert resp2.json()["updated"] == 2
    with tenant_context(org.tenant.id):
        assert User.objects.filter(email="ravi@acme.test").count() == 1
        assert User.objects.get(email="ravi@acme.test").title == "Senior AE"


def test_bulk_import_rejects_cross_tenant_manager_email(org, other_tenant):
    UserFactory(tenant=other_tenant, email="boss@other.test", role=User.Role.MANAGER)

    resp = _client_for(org.admin).post(
        IMPORT,
        {
            "rows": [
                {
                    "name": "New Employee",
                    "email": "new@acme.test",
                    "role": "EMPLOYEE",
                    "manager": "boss@other.test",
                }
            ]
        },
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["created"] == 1  # user exists, but no cross-tenant manager link
    assert body["skipped"] == 1
    assert "not found in this org" in body["errors"][0]["error"]
    with tenant_context(org.tenant.id):
        assert User.objects.get(email="new@acme.test").manager_id is None


def test_bulk_import_role_ceiling_and_rbac(org):
    # HRBP has INVITE_USERS, but cannot mint ADMINs.
    resp = _client_for(org.hrbp).post(
        IMPORT,
        {"rows": [{"name": "Escalate", "email": "x@acme.test", "role": "ADMIN"}]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 0
    assert "higher role" in resp.json()["errors"][0]["error"]

    # Employee has no INVITE_USERS capability.
    forbidden = _client_for(org.report).post(
        IMPORT,
        {"rows": [{"email": "e2@acme.test", "role": "EMPLOYEE"}]},
        format="json",
    )
    assert forbidden.status_code == 403


def test_bulk_import_seat_limit_blocks_creates(org):
    with tenant_context(org.tenant.id):
        billing_services.set_seats(org.tenant, 5, actor=org.admin)  # fixture already has 5 users

    resp = _client_for(org.admin).post(
        IMPORT,
        {"rows": [{"name": "No Seat", "email": "noseat@acme.test", "role": "EMPLOYEE"}]},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 0
    assert "seat" in resp.json()["errors"][0]["error"].lower()


def test_bulk_import_accepts_csv_upload(org):
    csv_body = "name,email,role,department,designation,manager\nCsv User,csv@acme.test,EMPLOYEE,Ops,Analyst,\n"
    upload = io.BytesIO(csv_body.encode("utf-8"))
    upload.name = "employees.csv"

    resp = _client_for(org.admin).post(IMPORT, {"file": upload}, format="multipart")

    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 1
    with tenant_context(org.tenant.id):
        assert User.objects.get(email="csv@acme.test").department == "Ops"
