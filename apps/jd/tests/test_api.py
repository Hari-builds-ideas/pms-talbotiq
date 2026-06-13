"""
HTTP tests for the JD Library API, hitting the REAL ``/api/jd/...`` routes
(production urlconf — no ``@pytest.mark.urls``).

Themes:
  * the END-TO-END manual flow over HTTP: create → save-draft → submit →
    approve (single-step publish) → an employee reads the published JD, the
    list, the versions, and the export;
  * the status-code contract: 422 INVALID_JD_INPUT (empty body on submit /
    no inputs on generate), 409 ILLEGAL_JD_TRANSITION (approve a DRAFT);
  * the RBAC matrix over HTTP: capability gates (employee/manager denials);
  * the §2 visibility rule: a non-manager 404s on a non-published JD;
  * cross-tenant isolation (404);
  * the JD-Generator seam: generate with no provider → 503, JD untouched;
  * templates: seed + instantiate; JD requests: create / list / fulfil;
  * the audit trail.
"""
import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.identity.tokens import issue_tokens_for_user
from apps.jd import services
from apps.jd.models import JobDescription
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    JobDescriptionFactory,
    JDVersionFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

JD = "/api/jd/"

# A complete, submittable body (summary + responsibilities + must_haves).
GOOD_BODY = {
    "summary": "Owns the platform's reliability.",
    "responsibilities": ["Run the on-call rotation", "Cut toil"],
    "must_haves": ["Production ops experience"],
    "nice_to_haves": ["Kubernetes"],
}


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _draft_jd(org, *, actor=None, body=None, inputs=None, title="Draft Role"):
    """A DRAFT JD authored by ``actor`` (default org.hrbp), parked for
    transition/visibility tests."""
    actor = actor or org.hrbp
    return services.lifecycle.create_jd(
        title=title,
        level="L4",
        actor=actor,
        body=body if body is not None else {},
        inputs=inputs if inputs is not None else {},
    )


# ── end-to-end: the manual authoring flow over HTTP ────────────────────────


def test_e2e_manual_jd_flow(org):
    hrbp = _client_for(org.hrbp)
    emp = _client_for(org.report)

    # 1. HRBP creates the JD → 201 DRAFT, audited.
    resp = hrbp.post(
        JD,
        {"title": "Site Reliability Engineer", "level": "L4", "department": "Eng"},
        format="json",
    )
    assert resp.status_code == 201
    jd = resp.json()
    assert jd["status"] == "DRAFT"
    assert jd["title"] == "Site Reliability Engineer"
    assert jd["created_by"] == str(org.hrbp.id)
    jd_id = jd["id"]
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="jd.created").exists()

    # 2. save-draft fills the body.
    draft = hrbp.post(f"{JD}{jd_id}/save-draft", {"body": GOOD_BODY}, format="json")
    assert draft.status_code == 200
    assert draft.json()["status"] == "DRAFT"

    # 3. submit → PENDING_HUMAN_REVIEW.
    submit = hrbp.post(f"{JD}{jd_id}/submit")
    assert submit.status_code == 200
    assert submit.json()["status"] == "PENDING_HUMAN_REVIEW"

    # 4. approve → PUBLISHED (no active "jd" workflow → single-step publish).
    approve = hrbp.post(f"{JD}{jd_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "PUBLISHED"
    assert approve.json()["current_version"] is not None

    # 5. an EMPLOYEE reads the published JD and sees it in the list.
    detail = emp.get(f"{JD}{jd_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "PUBLISHED"
    listing = emp.get(JD)
    assert listing.status_code == 200
    assert jd_id in {row["id"] for row in listing.json()["results"]}

    # 6. versions: one published version.
    versions = emp.get(f"{JD}{jd_id}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 1
    assert versions.json()[0]["is_published"] is True

    # 7. export: rendered text + structured body.
    export = emp.get(f"{JD}{jd_id}/export")
    assert export.status_code == 200
    assert "Site Reliability Engineer (L4)" in export.json()["rendered_text"]
    assert export.json()["body"]["must_haves"] == GOOD_BODY["must_haves"]

    # Audit: created + published rows exist (created has no id, published carries it).
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="jd.created", target_id=""
        ).exists()
        assert AuditLog.objects.filter(
            action="jd.published", target_id=str(jd_id)
        ).exists()


# ── status-code contract: 422 / 409 ────────────────────────────────────────


def test_submit_with_empty_body_is_422_invalid_input(org):
    jd = _draft_jd(org, body={})  # no summary/responsibilities/must_haves
    hrbp = _client_for(org.hrbp)
    resp = hrbp.post(f"{JD}{jd.id}/submit")
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_JD_INPUT"


def test_approve_from_draft_is_409_illegal_transition(org):
    jd = _draft_jd(org, body=GOOD_BODY)  # never submitted
    hrbp = _client_for(org.hrbp)
    resp = hrbp.post(f"{JD}{jd.id}/approve")
    assert resp.status_code == 409
    assert resp.json()["code"] == "ILLEGAL_JD_TRANSITION"


# ── RBAC denials over HTTP ─────────────────────────────────────────────────


def test_employee_cannot_create_jd(org):
    emp = _client_for(org.report)  # EMPLOYEE lacks MANAGE_JD_LIBRARY
    resp = emp.post(JD, {"title": "X", "level": "L1"}, format="json")
    assert resp.status_code == 403


def test_employee_cannot_generate_jd(org):
    jd = _draft_jd(org, inputs={"brief": "x"})
    emp = _client_for(org.report)  # EMPLOYEE lacks GENERATE_JD
    resp = emp.post(f"{JD}{jd.id}/generate")
    assert resp.status_code == 403


def test_manager_cannot_manage_library(org):
    # Only HRBP+ manage the library — a MANAGER is denied create.
    mgr = _client_for(org.manager)
    resp = mgr.post(JD, {"title": "X", "level": "L1"}, format="json")
    assert resp.status_code == 403


def test_employee_cannot_create_jd_request(org):
    # REQUEST_JD is Manager+; an EMPLOYEE is denied.
    emp = _client_for(org.report)
    resp = emp.post(f"{JD}requests", {"title": "Want a JD"}, format="json")
    assert resp.status_code == 403


# ── the JD-Generator seam: no provider → 503 / no inputs → 422 ─────────────


def test_generate_without_provider_is_503_and_jd_untouched(org):
    # WITH inputs so input-validation passes and we reach the provider check.
    jd = _draft_jd(org, inputs={"brief": "Reliability-focused SRE."})
    hrbp = _client_for(org.hrbp)

    resp = hrbp.post(f"{JD}{jd.id}/generate")
    assert resp.status_code == 503
    body = resp.json()
    assert body["generated"] is False
    assert body["reason"] == "no_provider"
    assert "Module 10" in body["detail"]

    # The loud seam never strands the JD: still DRAFT, manual path open.
    after = hrbp.get(f"{JD}{jd.id}")
    assert after.status_code == 200
    assert after.json()["status"] == "DRAFT"


def test_generate_without_inputs_is_422_invalid_input(org):
    jd = _draft_jd(org, inputs={})  # no inputs snapshot → generator refuses
    hrbp = _client_for(org.hrbp)
    resp = hrbp.post(f"{JD}{jd.id}/generate")
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_JD_INPUT"


# ── §2 visibility / scope over HTTP ────────────────────────────────────────


def test_employee_404s_on_draft_jd_but_manager_sees_it(org):
    jd = _draft_jd(org, body=GOOD_BODY)  # DRAFT, never published

    emp = _client_for(org.report)
    assert emp.get(f"{JD}{jd.id}").status_code == 404  # hidden by visible_jds

    mgr = _client_for(org.manager)
    seen = mgr.get(f"{JD}{jd.id}")
    assert seen.status_code == 200
    assert seen.json()["status"] == "DRAFT"


# ── cross-tenant isolation ─────────────────────────────────────────────────


def test_cross_tenant_jd_is_404(org, other_tenant):
    with tenant_context(other_tenant):
        outsider = UserFactory(tenant=other_tenant, role="HRBP")
        foreign = JobDescriptionFactory(created_by=outsider, status="PUBLISHED")
        JDVersionFactory(jd=foreign, version_number=1, is_published=True)

    hrbp = _client_for(org.hrbp)
    assert hrbp.get(f"{JD}{foreign.id}").status_code == 404
    assert hrbp.post(f"{JD}{foreign.id}/approve").status_code == 404


# ── templates ──────────────────────────────────────────────────────────────


def test_template_list_and_instantiate(org):
    services.seed_templates_for_tenant(org.tenant)
    hrbp = _client_for(org.hrbp)

    templates = hrbp.get(f"{JD}templates")
    assert templates.status_code == 200
    rows = templates.json()
    assert len(rows) == len(services.DEFAULT_TEMPLATES)
    se = next(r for r in rows if r["title_pattern"] == "Software Engineer")

    inst = hrbp.post(f"{JD}templates/{se['id']}/instantiate")
    assert inst.status_code == 201
    new_jd = inst.json()
    assert new_jd["status"] == "DRAFT"
    assert new_jd["title"] == "Software Engineer"

    # The scaffold body landed on the working version.
    export = hrbp.get(f"{JD}{new_jd['id']}/export")
    assert export.json()["body"]["summary"] == se["default_body"]["summary"]


def test_employee_cannot_list_templates(org):
    services.seed_templates_for_tenant(org.tenant)
    emp = _client_for(org.report)  # template management is MANAGE_JD_LIBRARY (HRBP+)
    assert emp.get(f"{JD}templates").status_code == 403


# ── JD requests ────────────────────────────────────────────────────────────


def test_jd_request_create_list_and_fulfil(org):
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)

    # Manager creates an OPEN request.
    created = mgr.post(
        f"{JD}requests",
        {"title": "Staff SRE", "level": "L5", "notes": "Q3 headcount."},
        format="json",
    )
    assert created.status_code == 201
    req = created.json()
    assert req["status"] == "OPEN"
    assert req["requested_by"] == str(org.manager.id)
    req_id = req["id"]

    # Manager sees their own request.
    mine = mgr.get(f"{JD}requests")
    assert mine.status_code == 200
    assert req_id in {r["id"] for r in mine.json()["results"]}

    # HRBP sees it tenant-wide.
    theirs = hrbp.get(f"{JD}requests")
    assert theirs.status_code == 200
    assert req_id in {r["id"] for r in theirs.json()["results"]}

    # HRBP fulfils with a JD they author.
    jd = JD_published(org, hrbp_client=hrbp)
    fulfil = hrbp.post(f"{JD}requests/{req_id}/fulfil", {"jd": jd}, format="json")
    assert fulfil.status_code == 200
    assert fulfil.json()["status"] == "FULFILLED"
    assert fulfil.json()["fulfilled_jd"] == jd

    # Fulfilling again is a 409 (no longer OPEN).
    again = hrbp.post(f"{JD}requests/{req_id}/fulfil", {"jd": jd}, format="json")
    assert again.status_code == 409
    assert again.json()["code"] == "ILLEGAL_JD_TRANSITION"


def JD_published(org, *, hrbp_client):
    """Create+publish a JD over HTTP and return its id (used by the request
    fulfil test)."""
    jd_id = hrbp_client.post(
        JD, {"title": "Staff SRE", "level": "L5"}, format="json"
    ).json()["id"]
    hrbp_client.post(f"{JD}{jd_id}/save-draft", {"body": GOOD_BODY}, format="json")
    hrbp_client.post(f"{JD}{jd_id}/submit")
    hrbp_client.post(f"{JD}{jd_id}/approve")
    return jd_id


# ── auth ───────────────────────────────────────────────────────────────────


def test_unauthenticated_list_is_401(org):
    resp = APIClient().get(JD)
    assert resp.status_code == 401
