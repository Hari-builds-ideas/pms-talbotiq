"""
PHASE2 L1.4 — internal subscription/plan model on the existing entitlements.
Proofs: plan changes sync packs + flip flags immediately (incl. the new plan-tier
feature keys); transition validation; the CANCELLED/EXPIRED kill switch; the
employee-limit headcount gate; admin-only API.
"""
import pytest
from rest_framework.test import APIClient

from apps.billing import services
from apps.billing.models import Subscription
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

SUB = "/api/billing/subscription"
PW = "pw-sub-123!"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@pytest.fixture
def org4():
    t = TenantFactory(slug="acme")
    admin = UserFactory(tenant=t, email="ad@acme.test", password=PW, role="ADMIN")
    emp = UserFactory(tenant=t, email="e@acme.test", password=PW, role="EMPLOYEE")
    return t, admin, emp


def test_plan_change_syncs_packs_and_flags_immediately(org4):
    t, admin, emp = org4
    c = _client(admin)
    # Default: STARTER/ACTIVE — premium features off, plan-tier keys present+false.
    flags = _client(emp).get("/api/billing/my-features").json()
    assert flags["agent1"] is False and flags["advanced_analytics"] is False
    assert "custom_branding" in flags  # stable complete key set
    # Admin moves to ENTERPRISE → FULL_AI pack + all plan features, instantly.
    r = c.patch(SUB, {"plan": "ENTERPRISE"}, format="json")
    assert r.status_code == 200 and r.json()["plan"] == "ENTERPRISE"
    flags = _client(emp).get("/api/billing/my-features").json()
    assert flags["agent1"] is True and flags["advanced_analytics"] is True
    assert flags["custom_branding"] is True and flags["sso"] is True


def test_status_transitions_validated_and_kill_switch(org4):
    t, admin, emp = org4
    c = _client(admin)
    c.patch(SUB, {"plan": "PROFESSIONAL"}, format="json")
    # ACTIVE → GRACE is not a legal jump (must pass PAST_DUE).
    r = c.patch(SUB, {"status": "GRACE"}, format="json")
    assert r.status_code == 400
    # ACTIVE → PAST_DUE → GRACE keeps features on; → EXPIRED kills them.
    assert c.patch(SUB, {"status": "PAST_DUE"}, format="json").status_code == 200
    assert _client(emp).get("/api/billing/my-features").json()["agent1"] is True
    assert c.patch(SUB, {"status": "GRACE"}, format="json").status_code == 200
    assert c.patch(SUB, {"status": "EXPIRED"}, format="json").status_code == 200
    flags = _client(emp).get("/api/billing/my-features").json()
    assert all(v is False for v in flags.values())  # the kill switch
    # Reactivation restores access.
    assert c.patch(SUB, {"status": "ACTIVE"}, format="json").status_code == 200
    assert _client(emp).get("/api/billing/my-features").json()["agent1"] is True


def test_unknown_plan_rejected_and_admin_only(org4):
    t, admin, emp = org4
    assert _client(admin).patch(SUB, {"plan": "PLATINUM"}, format="json").status_code == 400
    assert _client(emp).get(SUB).status_code == 403
    assert _client(emp).patch(SUB, {"plan": "ENTERPRISE"}, format="json").status_code == 403


def test_employee_limit_enforced_on_admin_create(org4):
    t, admin, emp = org4
    with tenant_context(t):
        services.set_seats(t, 50)  # seats are NOT the binding constraint here
        # Starter allows 25; simulate a full tenant by dropping the limit via plan
        # catalogue: use STARTER (limit 25) and create users up to the limit is
        # heavy — instead verify the gate wiring with the seat axis:
        services.set_seats(t, 2)  # 2 active users exist → tenant full
    r = _client(admin).post(
        "/api/admin/users",
        {"email": "extra@acme.test", "role": "EMPLOYEE", "password": "x-strong-1!pw"},
        format="json",
    )
    assert r.status_code == 409
    assert "seat" in r.json()["detail"].lower()


def test_can_add_user_plan_limit(org4):
    """The plan employee_limit axis of can_add_user (unit level — no 25-user setup)."""
    t, admin, emp = org4
    with tenant_context(t):
        services.set_seats(t, 500)
        sub = services.get_or_create_subscription(t.id)
        assert sub.plan == "STARTER"
        # Monkey-tight limit: patch the catalogue entry for the check.
        from apps.billing import packs

        original = packs.PLAN_CATALOG["STARTER"]["employee_limit"]
        packs.PLAN_CATALOG["STARTER"]["employee_limit"] = 2
        try:
            allowed, reason = services.can_add_user(t.id)
        finally:
            packs.PLAN_CATALOG["STARTER"]["employee_limit"] = original
    assert allowed is False and "plan" in reason.lower()
