"""
JD services — template seed/instantiate, role-scoped search, and export render.
"""
import pytest

from apps.jd import lifecycle, services
from apps.jd.exceptions import IllegalJDTransition
from apps.jd.models import JDRequest, JDTemplate, JobDescription
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

S = JobDescription.Status


# ── templates ────────────────────────────────────────────────────────────────


def test_seed_is_idempotent(org):
    n1 = services.seed_templates_for_tenant(org.tenant)
    assert n1 == len(services.DEFAULT_TEMPLATES)
    n2 = services.seed_templates_for_tenant(org.tenant)
    assert n2 == 0  # nothing duplicated
    with tenant_context(org.tenant):
        assert JDTemplate.objects.count() == len(services.DEFAULT_TEMPLATES)


def test_instantiate_template_creates_draft_jd_from_scaffold(org):
    services.seed_templates_for_tenant(org.tenant)
    with tenant_context(org.tenant):
        template = JDTemplate.objects.get(title_pattern="Software Engineer")
    jd = services.instantiate_template(template=template, actor=org.hrbp)
    assert jd.status == S.DRAFT
    assert jd.title == "Software Engineer" and jd.level == "L3"
    with tenant_context(org.tenant):
        v = lifecycle.working_version(jd)
        assert v.body["summary"] == template.default_body["summary"]
        # Editing the JD body must not mutate the template (deep copy).
        v.body["summary"] = "changed"
        v.save(update_fields=["body", "updated_at"])
        template.refresh_from_db()
        assert template.default_body["summary"] != "changed"


# ── search / scope ───────────────────────────────────────────────────────────


def _published(org, title):
    jd = lifecycle.create_jd(
        title=title, level="L3", actor=org.hrbp,
        body={"summary": "s", "responsibilities": ["r"], "must_haves": ["m"]},
    )
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    return jd


def test_employee_sees_published_only(org):
    _published(org, "Published Role")
    lifecycle.create_jd(  # a DRAFT, should be invisible to the employee
        title="Draft Role", level="L3", actor=org.hrbp, body={},
    )
    with tenant_context(org.tenant):
        titles = set(services.visible_jds(org.report).values_list("title", flat=True))
    assert titles == {"Published Role"}


def test_manager_sees_drafts_and_published(org):
    _published(org, "Published Role")
    lifecycle.create_jd(title="Draft Role", level="L3", actor=org.hrbp, body={})
    with tenant_context(org.tenant):
        titles = set(services.visible_jds(org.manager).values_list("title", flat=True))
    assert {"Published Role", "Draft Role"} <= titles


def test_search_filters_by_text_within_scope(org):
    _published(org, "Backend Engineer")
    _published(org, "Frontend Engineer")
    _published(org, "Account Executive")
    with tenant_context(org.tenant):
        hits = set(services.search_jds(org.hrbp, q="Engineer").values_list("title", flat=True))
    assert hits == {"Backend Engineer", "Frontend Engineer"}


def test_search_status_cannot_widen_employee_past_published(org):
    lifecycle.create_jd(title="Secret Draft", level="L3", actor=org.hrbp, body={})
    with tenant_context(org.tenant):
        # Even explicitly asking for DRAFT, an employee sees nothing non-published.
        hits = services.search_jds(org.report, status=S.DRAFT)
        assert hits.count() == 0


# ── export ───────────────────────────────────────────────────────────────────


def test_export_renders_text_and_structured_json(org):
    jd = _published(org, "Platform Engineer")
    with tenant_context(org.tenant):
        export = services.jd_export(jd)
    assert export["title"] == "Platform Engineer"
    assert export["status"] == S.PUBLISHED
    assert export["version_number"] == 1
    assert "Platform Engineer (L3)" in export["rendered_text"]
    assert "Responsibilities" in export["rendered_text"]
    assert export["body"]["must_haves"] == ["m"]


# ── JD requests ──────────────────────────────────────────────────────────────


def test_manager_creates_request_then_hrbp_fulfils(org):
    req = services.create_jd_request(
        requester=org.manager, title="New SRE role", level="L4", notes="urgent"
    )
    assert req.status == JDRequest.Status.OPEN
    assert req.requested_by_id == org.manager.id

    jd = _published(org, "New SRE role")
    services.fulfil_jd_request(request=req, jd=jd, actor=org.hrbp)
    req.refresh_from_db()
    assert req.status == JDRequest.Status.FULFILLED
    assert req.fulfilled_jd_id == jd.id


def test_fulfil_non_open_request_is_409(org):
    req = services.create_jd_request(requester=org.manager, title="x")
    services.decline_jd_request(request=req, actor=org.hrbp)
    req.refresh_from_db()
    assert req.status == JDRequest.Status.DECLINED
    jd = _published(org, "x")
    with pytest.raises(IllegalJDTransition):
        services.fulfil_jd_request(request=req, jd=jd, actor=org.hrbp)


def test_manager_sees_only_own_requests(org):
    services.create_jd_request(requester=org.manager, title="mine")
    # A second manager in the tenant.
    from apps.testsupport.factories import UserFactory

    other_mgr = UserFactory(tenant=org.tenant, role="MANAGER", email="mgr2@acme.test")
    services.create_jd_request(requester=other_mgr, title="theirs")
    with tenant_context(org.tenant):
        mine = set(services.visible_jd_requests(org.manager).values_list("title", flat=True))
        all_hrbp = set(services.visible_jd_requests(org.hrbp).values_list("title", flat=True))
    assert mine == {"mine"}
    assert {"mine", "theirs"} <= all_hrbp
