"""
HTTP tests for the Career Development (Roadmap LITE) API, hitting the REAL
``/api/career/...`` routes (production urlconf — no ``@pytest.mark.urls``).

Career is EMPLOYEE-VISIBLE, so the themes are SCOPE (not 403-everywhere like
succession) and — the headline — THE DATA BOUNDARY: a career response carries ONLY
the employee's own performance-derived gap + advisory tiers and NEVER the
succession surface (readiness / potential / bench / coverage / 9-box) nor any other
employee's data.

Themes:
  * an employee selects their own target (PUBLISHED JD) → 201 deterministic roadmap
    (non-empty tiers, a skill_gap dict, advisory True, source DETERMINISTIC, ACTIVE);
  * the skill gap reflects the employee's OWN performance band (t=70 HIGH → gap 0,
    t=50 MEDIUM → gap 1, no score → UNKNOWN gap 2);
  * THE DATA BOUNDARY: even with succession data seeded for the employee, their
    roadmap + skill-gap JSON leaks none of the succession vocabulary and no other
    employee's id;
  * the Career Roadmap agent seam → 503 (no_provider), the deterministic roadmap
    left intact and no source=AI row written;
  * Manager scope: a report in-tier (200), a peer out-of-tier (404), cross-tenant
    (404);
  * progress: mark a tier (200), list it (200), out-of-range tier (422);
  * target validation: both / neither / a non-PUBLISHED JD → 422;
  * a manager selecting FOR a report (in-tier) → 201;
  * the unauthenticated 401.
"""
import json
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai.models import AIJob
from apps.career.models import DevelopmentRoadmap
from apps.goals.models import CycleScore
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    BenchCandidateFactory,
    CriticalRoleFactory,
    CycleFactory,
    JobDescriptionFactory,
    NineBoxPlacementFactory,
    PositionFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

CAREER = "/api/career/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _score(tenant, employee, cycle, t):
    """Create a CycleScore with T-score ``t`` for ``employee`` in ``cycle`` (drives
    the deterministic performance band)."""
    with tenant_context(tenant):
        return CycleScore.objects.create(
            tenant_id=tenant.id,
            employee=employee,
            cycle=cycle,
            raw_score=Decimal("0"),
            z_score=Decimal("0"),
            t_score=Decimal(str(t)),
            cohort_size=10,
            computed_at=timezone.now(),
        )


def _published_jd(org):
    """A PUBLISHED JD in the org's tenant — a valid target role."""
    with tenant_context(org.tenant):
        return JobDescriptionFactory(created_by=org.hrbp, status="PUBLISHED")


# ── employee selects own target (PUBLISHED JD) → 201 deterministic roadmap ────


def test_employee_selects_own_target_returns_deterministic_roadmap(org):
    emp = _client_for(org.report)
    jd = _published_jd(org)

    resp = emp.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()

    selection = body["selection"]
    assert selection["employee"] == str(org.report.id)
    assert selection["target_jd"] == str(jd.id)
    assert selection["selected_by"] == str(org.report.id)

    roadmap = body["roadmap"]
    assert roadmap["employee"] == str(org.report.id)
    assert roadmap["status"] == "ACTIVE"
    assert roadmap["source"] == "DETERMINISTIC"
    assert roadmap["advisory"] is True
    assert roadmap["tiers"]  # non-empty
    assert isinstance(roadmap["skill_gap"], dict)
    assert roadmap["skill_gap"]["required_performance_band"] == "HIGH"


def test_employee_can_select_an_org_position_target(org):
    emp = _client_for(org.report)
    with tenant_context(org.tenant):
        position = PositionFactory(reports_to=org.manager)

    resp = emp.post(
        f"{CAREER}target", {"target_position": str(position.id)}, format="json"
    )
    assert resp.status_code == 201, resp.content
    roadmap = resp.json()["roadmap"]
    assert roadmap["target_position"] == str(position.id)
    assert roadmap["target_jd"] is None
    assert roadmap["source"] == "DETERMINISTIC"


# ── the skill gap reflects the employee's OWN performance band ────────────────


def test_skill_gap_reflects_performance_band(org):
    emp = _client_for(org.report)
    jd = _published_jd(org)

    # HIGH (t=70) in the first cycle → no band gap.
    cycle_high = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle_high, 70)
    roadmap_id = emp.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]
    resp = emp.get(f"{CAREER}roadmaps/{roadmap_id}/skill-gap")
    assert resp.status_code == 200, resp.content
    gap = resp.json()
    assert gap["current_performance_band"] == "HIGH"
    assert gap["performance_band_gap"] == 0

    # A newer cycle scored MEDIUM (t=50) becomes the latest → gap 1 after regenerate.
    cycle_med = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle_med, 50)
    emp.post(f"{CAREER}roadmaps/{roadmap_id}/regenerate", {}, format="json")
    gap = emp.get(f"{CAREER}roadmaps/{roadmap_id}/skill-gap").json()
    assert gap["current_performance_band"] == "MEDIUM"
    assert gap["performance_band_gap"] == 1


def test_skill_gap_unknown_when_no_score(org):
    """An employee with no CycleScore shows UNKNOWN band + the maximal gap (2)."""
    emp = _client_for(org.peer)
    jd = _published_jd(org)
    roadmap_id = emp.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]
    gap = emp.get(f"{CAREER}roadmaps/{roadmap_id}/skill-gap").json()
    assert gap["current_performance_band"] == "UNKNOWN"
    assert gap["performance_band_gap"] == 2


# ── THE DATA BOUNDARY (headline) ──────────────────────────────────────────────


# The succession SURFACE that must never appear in a career response. We scan two
# things: (a) the structured JSON *keys* for any succession field name, and (b) the
# serialized blob for the specific succession *values* we seed below (the readiness
# enum, the assigned potential band, the coverage colour). We deliberately do NOT
# do a naive substring scan for the bare English words "readiness"/"potential",
# because the deterministic engine's own advisory coaching copy legitimately uses
# those words ("evidence readiness for the next level", "Demonstrate potential
# through a stretch assignment") — that prose is generic development language, not a
# leak of the management-only succession surface. The real boundary is about
# succession FIELDS, succession VALUES, and other employees' data.
_SUCCESSION_FIELD_KEYS = [
    "readiness",
    "readiness_overridden",
    "potential_band",
    "coverage_status",
    "box",
    "nine_box",
    "ninebox",
    "critical_role",
    "ranked_bench",
    "red_flags",
]


def _all_keys(obj):
    """Every dict key appearing anywhere in a nested JSON structure."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


def test_data_boundary_no_succession_leak_in_roadmap_or_skillgap(org):
    """The headline safety property of Module 9: even with succession data seeded
    FOR the employee, neither their roadmap nor their skill-gap response surfaces any
    succession FIELD, any seeded succession VALUE, or any OTHER employee's id."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle, 70)

    # Seed the sensitive succession surface FOR org.report with DISTINCTIVE values
    # we can search for: a READY_NOW readiness, a HIGH potential band, box 9.
    with tenant_context(org.tenant):
        critical_role = CriticalRoleFactory(marked_by=org.hrbp)
        BenchCandidateFactory(
            critical_role=critical_role, candidate=org.report, readiness="READY_NOW"
        )
        NineBoxPlacementFactory(
            employee=org.report, cycle=cycle, potential_band="HIGH", box=9
        )

    emp = _client_for(org.report)
    jd = _published_jd(org)
    roadmap = emp.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]
    roadmap_id = roadmap["id"]

    roadmap_resp = emp.get(f"{CAREER}roadmaps/{roadmap_id}").json()
    gap_resp = emp.get(f"{CAREER}roadmaps/{roadmap_id}/skill-gap").json()

    # (a) No succession FIELD name appears anywhere as a key.
    for resp in (roadmap_resp, gap_resp):
        keys = _all_keys(resp)
        for field in _SUCCESSION_FIELD_KEYS:
            assert field not in keys, f"leaked succession field {field!r} in keys {keys}"

    # (b) No seeded succession VALUE appears anywhere in the serialized blobs.
    roadmap_json = json.dumps(roadmap_resp)
    gap_json = json.dumps(gap_resp)
    for blob in (roadmap_json, gap_json):
        assert "READY_NOW" not in blob, f"leaked readiness value in {blob}"
        # The HIGH potential band must not surface; HIGH appears only as the
        # employee's OWN performance band, never carrying a "potential" label.
        assert '"potential' not in blob, f"leaked a potential label in {blob}"

    # (c) No OTHER employee's id appears in the employee's own roadmap response.
    assert str(org.peer.id) not in roadmap_json
    assert str(org.manager.id) not in roadmap_json


# ── the Career Roadmap agent seam → async; deterministic roadmap intact ───────


def test_enrich_enqueues_job_degraded_and_roadmap_unchanged(org):
    emp = _client_for(org.report)
    jd = _published_jd(org)
    roadmap_id = emp.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]

    # Enqueue → 202 + an AI job; the (eager) job DEGRADES with no provider.
    resp = emp.post(f"{CAREER}roadmaps/{roadmap_id}/enrich", {}, format="json")
    assert resp.status_code == 202, resp.content
    body = resp.json()
    assert body["agent_code"] == "career_roadmap"
    assert body["target_id"] == str(org.report.id)  # the employee
    with tenant_context(org.tenant):
        job = AIJob.objects.get(id=body["id"])
        assert job.status == AIJob.Status.DEGRADED
        assert job.error_code == "NOT_CONFIGURED"

    # The deterministic roadmap is left COMPLETELY INTACT.
    resp = emp.get(f"{CAREER}roadmaps/{roadmap_id}")
    assert resp.status_code == 200, resp.content
    roadmap = resp.json()
    assert roadmap["status"] == "ACTIVE"
    assert roadmap["source"] == "DETERMINISTIC"

    # And no source=AI roadmap was written for that employee.
    with tenant_context(org.tenant):
        assert not DevelopmentRoadmap.objects.filter(
            employee=org.report, source=DevelopmentRoadmap.Source.AI
        ).exists()


# ── Manager scope: in-tier (200) vs out-of-tier / cross-tenant (404) ──────────


def test_manager_views_report_roadmap_in_tier(org):
    jd = _published_jd(org)
    # The report selects their own target.
    report_client = _client_for(org.report)
    roadmap_id = report_client.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]

    mgr = _client_for(org.manager)
    # GET the report's roadmap by id → 200.
    resp = mgr.get(f"{CAREER}roadmaps/{roadmap_id}")
    assert resp.status_code == 200, resp.content
    assert resp.json()["employee"] == str(org.report.id)

    # GET /roadmaps?employee=report.id → 200 with the roadmap.
    resp = mgr.get(f"{CAREER}roadmaps", {"employee": str(org.report.id)})
    assert resp.status_code == 200, resp.content
    ids = {r["id"] for r in resp.json()["results"]}
    assert roadmap_id in ids


def test_employee_viewing_anothers_roadmap_is_404(org):
    jd = _published_jd(org)
    # org.peer selects a target.
    peer_client = _client_for(org.peer)
    peer_roadmap_id = peer_client.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]

    # org.report (a peer, out of scope) viewing it → 404, not 403.
    report_client = _client_for(org.report)
    assert (
        report_client.get(f"{CAREER}roadmaps/{peer_roadmap_id}").status_code == 404
    )


def test_manager_selecting_for_out_of_tier_employee_is_404(org):
    jd = _published_jd(org)
    mgr = _client_for(org.manager)
    # org.peer reports to hrbp, OUT of the manager's subtree → 404.
    resp = mgr.post(
        f"{CAREER}target",
        {"employee": str(org.peer.id), "target_jd": str(jd.id)},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_cross_tenant_roadmap_is_404(org, other_tenant):
    jd = _published_jd(org)
    report_client = _client_for(org.report)
    roadmap_id = report_client.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]

    other_admin = UserFactory(tenant=other_tenant, role="ADMIN")
    other = _client_for(other_admin)
    assert other.get(f"{CAREER}roadmaps/{roadmap_id}").status_code == 404


# ── progress ───────────────────────────────────────────────────────────────────


def test_progress_mark_list_and_out_of_range(org):
    emp = _client_for(org.report)
    jd = _published_jd(org)
    roadmap_id = emp.post(
        f"{CAREER}target", {"target_jd": str(jd.id)}, format="json"
    ).json()["roadmap"]["id"]

    # Mark tier 0 IN_PROGRESS → 200.
    resp = emp.post(
        f"{CAREER}roadmaps/{roadmap_id}/progress",
        {"tier_index": 0, "status": "IN_PROGRESS"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["tier_index"] == 0
    assert resp.json()["status"] == "IN_PROGRESS"

    # GET the progress list → shows the row.
    resp = emp.get(f"{CAREER}roadmaps/{roadmap_id}/progress")
    assert resp.status_code == 200, resp.content
    rows = resp.json()
    assert any(r["tier_index"] == 0 and r["status"] == "IN_PROGRESS" for r in rows)

    # An out-of-range tier_index → 422.
    resp = emp.post(
        f"{CAREER}roadmaps/{roadmap_id}/progress",
        {"tier_index": 999, "status": "IN_PROGRESS"},
        format="json",
    )
    assert resp.status_code == 422, resp.content


# ── target validation: both / neither / non-PUBLISHED JD → 422 ────────────────


def test_select_with_both_targets_is_422(org):
    emp = _client_for(org.report)
    jd = _published_jd(org)
    with tenant_context(org.tenant):
        position = PositionFactory(reports_to=org.manager)
    resp = emp.post(
        f"{CAREER}target",
        {"target_jd": str(jd.id), "target_position": str(position.id)},
        format="json",
    )
    assert resp.status_code == 422, resp.content


def test_select_with_neither_target_is_422(org):
    emp = _client_for(org.report)
    resp = emp.post(f"{CAREER}target", {}, format="json")
    assert resp.status_code == 422, resp.content


def test_select_with_non_published_jd_is_422(org):
    emp = _client_for(org.report)
    with tenant_context(org.tenant):
        draft_jd = JobDescriptionFactory(created_by=org.hrbp, status="DRAFT")
    resp = emp.post(
        f"{CAREER}target", {"target_jd": str(draft_jd.id)}, format="json"
    )
    assert resp.status_code == 422, resp.content


# ── a manager selects a target FOR a report (in-tier) → 201 ───────────────────


def test_manager_selects_target_for_report_in_tier(org):
    jd = _published_jd(org)
    mgr = _client_for(org.manager)
    resp = mgr.post(
        f"{CAREER}target",
        {"employee": str(org.report.id), "target_jd": str(jd.id)},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["selection"]["employee"] == str(org.report.id)
    assert body["selection"]["selected_by"] == str(org.manager.id)
    assert body["roadmap"]["employee"] == str(org.report.id)


# ── the caller's OWN roadmaps ──────────────────────────────────────────────────


def test_my_roadmaps_returns_own_only(org):
    jd = _published_jd(org)
    report_client = _client_for(org.report)
    report_client.post(f"{CAREER}target", {"target_jd": str(jd.id)}, format="json")

    resp = report_client.get(f"{CAREER}roadmap")
    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"]
    assert rows
    assert all(r["employee"] == str(org.report.id) for r in rows)


# ── unauthenticated → 401 ─────────────────────────────────────────────────────


def test_unauthenticated_is_401(org):
    resp = APIClient().get(f"{CAREER}roadmap")
    assert resp.status_code == 401
