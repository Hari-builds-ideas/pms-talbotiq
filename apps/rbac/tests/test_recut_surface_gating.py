"""
RW_BUILD_1 1.4 — server-side defense in depth for the re-weighted navigation.

The nav re-cut (RW_BUILD_1) is purely a VISIBILITY change: it stops advertising to a
role what the server would deny, and it lets employees reach their own everyday
screens. Hiding a link is UX, never security — so these hit the REAL production
endpoints (the default urlconf, JWT per role) and prove the server still:

  * DENIES the demoted/gated surface to roles that lack the capability (the items we
    removed from a role's sidebar 403/404 if that role calls them anyway), AND
  * ALLOWS the newly-exposed everyday screens for an employee (own scope) — proving
    those sidebar items are real, not dead links.

No backend RBAC was changed in RW_BUILD_1; this locks that the surface is correct.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user

pytestmark = pytest.mark.django_db


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


# ── demoted / gated surface stays DENIED server-side ──────────────────────────

def test_employee_denied_succession_dashboard(org):
    # Demoted to Advanced (HR/Admin). Succession is invisible to employees — the
    # SuccessionParticipant gate yields 404 (not 403), the project's hard guardrail.
    resp = _client(org.report).get("/api/succession/dashboard")
    assert resp.status_code == 404


def test_employee_denied_department_analytics(org):
    # "Team Analytics" is Manager+; an employee never holds VIEW_DEPARTMENT_ANALYTICS.
    resp = _client(org.report).get("/api/analytics/department")
    assert resp.status_code == 403


def test_manager_denied_audit_console(org):
    # Audit is in the HRBP+ Advanced group; a manager lacks VIEW_AUDIT_CONSOLE.
    resp = _client(org.manager).get("/api/audit/logs")
    assert resp.status_code == 403


def test_manager_denied_calibration_grid(org):
    # Calibration (inside Analytics) is HRBP+; a manager lacks VIEW_CALIBRATION_GRID.
    resp = _client(org.manager).get("/api/analytics/calibration")
    assert resp.status_code == 403


def test_hrbp_denied_admin_users(org):
    # Administration is Admin-only; HRBP lacks MANAGE_USERS_ROLES (see Q4).
    resp = _client(org.hrbp).get("/api/admin/users")
    assert resp.status_code == 403


def test_hrbp_denied_integrations(org):
    # Integrations is Admin-only; HRBP lacks MANAGE_INTEGRATIONS (see Q4).
    resp = _client(org.hrbp).get("/api/integrations/")
    assert resp.status_code == 403


# ── newly-exposed everyday screens ALLOW an employee (own scope) — no dead link ──

def test_employee_allowed_own_goals(org):
    resp = _client(org.report).get("/api/goals/")
    assert resp.status_code == 200


def test_employee_allowed_own_reviews(org):
    resp = _client(org.report).get("/api/reviews/")
    assert resp.status_code == 200


def test_employee_allowed_own_feedback_requests(org):
    resp = _client(org.report).get("/api/feedback/requests/mine")
    assert resp.status_code == 200
