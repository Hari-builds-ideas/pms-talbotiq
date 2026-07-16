"""
PHASE2 L1.5 — org settings + branding hooks. Proofs: typed validation, the
custom_branding plan gate, and branding served on /me only when entitled.
"""
import pytest
from rest_framework.test import APIClient

from apps.billing.services import set_plan
from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

ORG = "/api/admin/org-settings"
PW = "pw-org-123!"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@pytest.fixture
def org5():
    t = TenantFactory(slug="acme")
    admin = UserFactory(tenant=t, email="ad@acme.test", password=PW, role="ADMIN")
    emp = UserFactory(tenant=t, email="e@acme.test", password=PW, role="EMPLOYEE")
    return t, admin, emp


def test_org_settings_typed_validation_and_admin_only(org5):
    t, admin, emp = org5
    c = _client(admin)
    assert c.patch(ORG, {"timezone": "Mars/Olympus"}, format="json").status_code == 400
    r = c.patch(ORG, {"name": "Acme Sdn Bhd", "timezone": "Asia/Kuala_Lumpur", "language": "en"},
                format="json")
    assert r.status_code == 200 and r.json()["timezone"] == "Asia/Kuala_Lumpur"
    assert c.get(ORG).json()["name"] == "Acme Sdn Bhd"
    assert _client(emp).get(ORG).status_code == 403


def test_branding_gated_by_plan_and_served_on_me(org5):
    t, admin, emp = org5
    c = _client(admin)
    # STARTER plan → branding fields refused (custom_branding off).
    r = c.patch(ORG, {"logo_url": "https://cdn.acme.test/logo.png"}, format="json")
    assert r.status_code == 403
    assert _client(emp).get("/api/auth/me").json()["tenant_branding"] is None
    # ENTERPRISE plan → branding accepted, hex validated, served on /me for everyone.
    set_plan(t.id, "ENTERPRISE", actor=admin)
    assert c.patch(ORG, {"primary_color": "not-a-color"}, format="json").status_code == 400
    r = c.patch(ORG, {"logo_url": "https://cdn.acme.test/logo.png", "primary_color": "#0d5c3a"},
                format="json")
    assert r.status_code == 200, r.content
    branding = _client(emp).get("/api/auth/me").json()["tenant_branding"]
    assert branding == {"logo_url": "https://cdn.acme.test/logo.png", "primary_color": "#0d5c3a"}
