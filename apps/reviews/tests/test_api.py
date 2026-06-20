"""
HTTP tests for the Reviews API, hitting the REAL ``/api/reviews/...`` routes
(production urlconf — no ``@pytest.mark.urls``).

Themes:
  * the END-TO-END manual HITL flow over HTTP: create → assessments → edit →
    submit → (finalize blocked 422) → approve → finalize → subject reads it;
  * the status-code contract: 409 illegal transition / non-ACTIVE cycle,
    422 HITL_APPROVAL_REQUIRED / REJECTION_REASON_REQUIRED;
  * the RBAC matrix over HTTP: capability gates, object scope (peer manager),
    cross-tenant isolation (404);
  * assessments: SELF subject-only + upsert, duplicate rejection, visibility;
  * the Agent-1 seam: request-ai-draft with no provider → 503, review untouched;
  * the timeline (approval tracker) and the audit trail.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.models import AIJob
from apps.audit.models import AuditLog
from apps.identity.tokens import issue_tokens_for_user
from apps.reviews.models import Review, ReviewAssessment
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    ReviewAssessmentFactory,
    ReviewFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

REVIEWS = "/api/reviews/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _make_review(org, *, state="DRAFT", employee=None, cycle=None, **kwargs):
    """A review for ``employee`` (default org.report) in ``cycle`` (default a
    fresh ACTIVE cycle), parked directly in ``state`` for transition tests."""
    employee = employee or org.report
    cycle = cycle or CycleFactory(tenant=org.tenant, status="ACTIVE")
    with tenant_context(org.tenant):
        return ReviewFactory(employee=employee, cycle=cycle, state=state, **kwargs)


# ── end-to-end: the manual HITL flow over HTTP ─────────────────────────────


def test_e2e_manual_hitl_flow(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    emp = _client_for(org.report)

    # 1. Manager creates the review for their report → 201 DRAFT, audited.
    resp = mgr.post(
        REVIEWS,
        {"employee": str(org.report.id), "cycle": str(cycle.id)},
        format="json",
    )
    assert resp.status_code == 201
    review = resp.json()
    assert review["state"] == "DRAFT"
    assert review["employee"] == str(org.report.id)
    assert review["reviewer"] == str(org.manager.id)
    review_id = review["id"]
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="review.created").exists()

    # 2. The subject submits their SELF assessment → 201.
    self_resp = emp.post(
        f"{REVIEWS}{review_id}/assessments",
        {"assessment_type": "SELF", "body": "I shipped the thing."},
        format="json",
    )
    assert self_resp.status_code == 201
    assert self_resp.json()["assessor"] == str(org.report.id)

    # 3. The manager submits their MANAGER assessment → 201.
    mgr_resp = mgr.post(
        f"{REVIEWS}{review_id}/assessments",
        {"assessment_type": "MANAGER", "body": "Solid quarter."},
        format="json",
    )
    assert mgr_resp.status_code == 201

    # 4. Manager starts the manual draft → EDITING.
    edit = mgr.post(f"{REVIEWS}{review_id}/start-edit")
    assert edit.status_code == 200
    assert edit.json()["state"] == "EDITING"

    # 5. Manager submits the draft for human review → PENDING_HUMAN_REVIEW.
    draft = "Strong performance against all KPIs."
    submit = mgr.post(
        f"{REVIEWS}{review_id}/submit", {"draft_body": draft}, format="json"
    )
    assert submit.status_code == 200
    assert submit.json()["state"] == "PENDING_HUMAN_REVIEW"
    assert submit.json()["draft_body"] == draft

    # 6. THE HITL GATE: finalize before any human approval → 422.
    blocked = mgr.post(f"{REVIEWS}{review_id}/finalize")
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "HITL_APPROVAL_REQUIRED"

    # 7. Human approval → APPROVED, the approver is recorded, audited.
    approve = mgr.post(f"{REVIEWS}{review_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["state"] == "APPROVED"
    assert approve.json()["human_reviewer"] == str(org.manager.id)
    assert approve.json()["approved_at"] is not None
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="review.approved", target_id=str(review_id)
        ).exists()

    # 8. Finalize → FINALIZED; the approved draft becomes the final body.
    final = mgr.post(f"{REVIEWS}{review_id}/finalize")
    assert final.status_code == 200
    assert final.json()["state"] == "FINALIZED"
    assert final.json()["final_body"] == draft
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="review.finalized", target_id=str(review_id)
        ).exists()

    # 9. The subject reads their own finalized review.
    own = emp.get(f"{REVIEWS}{review_id}")
    assert own.status_code == 200
    assert own.json()["state"] == "FINALIZED"

    # 10. The timeline (approval tracker) shows the ordered from/to chain —
    # the subject may read it too (same visibility as the detail).
    timeline = emp.get(f"{REVIEWS}{review_id}/timeline")
    assert timeline.status_code == 200
    chain = [(t["from_state"], t["to_state"]) for t in timeline.json()]
    assert chain == [
        ("DRAFT", "EDITING"),
        ("EDITING", "PENDING_HUMAN_REVIEW"),
        ("PENDING_HUMAN_REVIEW", "APPROVED"),
        ("APPROVED", "FINALIZED"),
    ]


# ── status-code contract: 409 / 422 ────────────────────────────────────────


def test_create_against_non_active_cycle_is_409(org):
    draft_cycle = CycleFactory(tenant=org.tenant, status="DRAFT")
    mgr = _client_for(org.manager)
    resp = mgr.post(
        REVIEWS,
        {"employee": str(org.report.id), "cycle": str(draft_cycle.id)},
        format="json",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "CYCLE_NOT_ACTIVE"


def test_approve_from_draft_is_409_illegal_transition(org):
    review = _make_review(org, state="DRAFT")
    mgr = _client_for(org.manager)
    resp = mgr.post(f"{REVIEWS}{review.id}/approve")
    assert resp.status_code == 409
    assert resp.json()["code"] == "ILLEGAL_TRANSITION"


def test_approve_twice_is_409(org):
    review = _make_review(org, state="PENDING_HUMAN_REVIEW")
    mgr = _client_for(org.manager)
    assert mgr.post(f"{REVIEWS}{review.id}/approve").status_code == 200
    again = mgr.post(f"{REVIEWS}{review.id}/approve")
    assert again.status_code == 409
    assert again.json()["code"] == "ILLEGAL_TRANSITION"


def test_reject_requires_reason_then_rejects_then_revise(org):
    review = _make_review(org, state="PENDING_HUMAN_REVIEW")
    mgr = _client_for(org.manager)

    # No reason → 422.
    no_reason = mgr.post(f"{REVIEWS}{review.id}/reject", {}, format="json")
    assert no_reason.status_code == 422
    assert no_reason.json()["code"] == "REJECTION_REASON_REQUIRED"

    # With a reason → 200 REJECTED (audited).
    rejected = mgr.post(
        f"{REVIEWS}{review.id}/reject", {"reason": "Needs evidence."}, format="json"
    )
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "REJECTED"
    assert rejected.json()["rejected_reason"] == "Needs evidence."
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(
            action="review.rejected", target_id=str(review.id)
        ).exists()

    # Revise: REJECTED → EDITING.
    revise = mgr.post(f"{REVIEWS}{review.id}/start-edit")
    assert revise.status_code == 200
    assert revise.json()["state"] == "EDITING"


# ── RBAC / scope over HTTP ─────────────────────────────────────────────────


def test_employee_cannot_create_review(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    emp = _client_for(org.report)  # EMPLOYEE lacks MANAGE_REVIEWS
    resp = emp.post(
        REVIEWS,
        {"employee": str(org.report.id), "cycle": str(cycle.id)},
        format="json",
    )
    assert resp.status_code == 403


def test_manager_cannot_create_review_outside_subtree(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    # peer reports to hrbp, NOT to manager → out of scope → 403.
    resp = mgr.post(
        REVIEWS,
        {"employee": str(org.peer.id), "cycle": str(cycle.id)},
        format="json",
    )
    assert resp.status_code == 403


def test_peer_manager_out_of_scope_gets_403(org):
    # A second MANAGER in the tenant with NO reports: holds the capabilities
    # but the report is outside their reporting subtree.
    peer_manager = UserFactory(tenant=org.tenant, role="MANAGER")
    review = _make_review(org, state="PENDING_HUMAN_REVIEW")
    pm = _client_for(peer_manager)

    assert pm.get(f"{REVIEWS}{review.id}").status_code == 403
    assert pm.post(f"{REVIEWS}{review.id}/approve").status_code == 403


def test_employee_cannot_approve_or_finalize_own_review(org):
    review = _make_review(org, state="PENDING_HUMAN_REVIEW")
    emp = _client_for(org.report)  # EMPLOYEE lacks APPROVE_REVIEW / FINALIZE_REVIEW
    assert emp.post(f"{REVIEWS}{review.id}/approve").status_code == 403
    assert emp.post(f"{REVIEWS}{review.id}/finalize").status_code == 403


def test_hrbp_tenant_scope_detail_and_calibration(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    review = _make_review(org, cycle=cycle)
    hrbp = _client_for(org.hrbp)

    # Tenant scope: HRBP sees a review they neither authored nor manage.
    assert hrbp.get(f"{REVIEWS}{review.id}").status_code == 200

    cal = hrbp.get(f"{REVIEWS}calibration?cycle={cycle.id}")
    assert cal.status_code == 200
    assert str(review.id) in {row["id"] for row in cal.json()["results"]}

    # ?state= filter narrows the rows.
    none = hrbp.get(f"{REVIEWS}calibration?cycle={cycle.id}&state=FINALIZED")
    assert none.status_code == 200
    assert none.json()["results"] == []


def test_calibration_hides_final_body_until_finalized(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _make_review(org, cycle=cycle, state="PENDING_HUMAN_REVIEW", draft_body="secret")
    hrbp = _client_for(org.hrbp)
    rows = hrbp.get(f"{REVIEWS}calibration?cycle={cycle.id}").json()["results"]
    assert rows[0]["final_body"] is None


def test_employee_cannot_read_calibration(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    emp = _client_for(org.report)  # EMPLOYEE lacks CALIBRATE_REVIEWS
    resp = emp.get(f"{REVIEWS}calibration?cycle={cycle.id}")
    assert resp.status_code == 403


def test_review_list_scopes_and_filters(org):
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    report_review = _make_review(org, employee=org.report, cycle=cycle)
    peer_review = _make_review(org, employee=org.peer, cycle=cycle)

    # OWN: the employee sees only their own review.
    emp_rows = _client_for(org.report).get(REVIEWS).json()["results"]
    assert {r["id"] for r in emp_rows} == {str(report_review.id)}

    # TEAM: the manager sees the subtree (the report), not the peer.
    mgr_rows = _client_for(org.manager).get(f"{REVIEWS}?cycle={cycle.id}").json()["results"]
    assert {r["id"] for r in mgr_rows} == {str(report_review.id)}

    # TENANT: HRBP sees both; ?state= filters.
    hrbp = _client_for(org.hrbp)
    assert {r["id"] for r in hrbp.get(REVIEWS).json()["results"]} == {
        str(report_review.id),
        str(peer_review.id),
    }
    assert hrbp.get(f"{REVIEWS}?state=FINALIZED").json()["results"] == []


# ── cross-tenant isolation ─────────────────────────────────────────────────


def test_cross_tenant_review_is_404(org, other_tenant):
    other_cycle = CycleFactory(tenant=other_tenant, status="ACTIVE")
    with tenant_context(other_tenant):
        outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE")
        foreign = ReviewFactory(
            employee=outsider, cycle=other_cycle, state="PENDING_HUMAN_REVIEW"
        )

    mgr = _client_for(org.manager)
    assert mgr.get(f"{REVIEWS}{foreign.id}").status_code == 404
    assert mgr.post(f"{REVIEWS}{foreign.id}/approve").status_code == 404


# ── assessments ────────────────────────────────────────────────────────────


def test_self_assessment_by_non_subject_is_rejected(org):
    review = _make_review(org, employee=org.report)
    peer = _client_for(org.peer)  # an employee who is NOT the subject
    resp = peer.post(
        f"{REVIEWS}{review.id}/assessments",
        {"assessment_type": "SELF", "body": "Not my review."},
        format="json",
    )
    assert resp.status_code in (400, 403)


def test_duplicate_manager_assessment_is_400(org):
    review = _make_review(org, employee=org.report)
    mgr = _client_for(org.manager)
    first = mgr.post(
        f"{REVIEWS}{review.id}/assessments",
        {"assessment_type": "MANAGER", "body": "First take."},
        format="json",
    )
    assert first.status_code == 201
    dup = mgr.post(
        f"{REVIEWS}{review.id}/assessments",
        {"assessment_type": "MANAGER", "body": "Second take."},
        format="json",
    )
    assert dup.status_code == 400


def test_self_assessment_resubmission_upserts(org):
    review = _make_review(org, employee=org.report)
    emp = _client_for(org.report)
    first = emp.post(
        f"{REVIEWS}{review.id}/assessments",
        {"assessment_type": "SELF", "body": "v1"},
        format="json",
    )
    assert first.status_code in (200, 201)
    second = emp.post(
        f"{REVIEWS}{review.id}/assessments",
        {"assessment_type": "SELF", "body": "v2 — refined"},
        format="json",
    )
    assert second.status_code in (200, 201)
    with tenant_context(org.tenant):
        rows = list(ReviewAssessment.objects.filter(review_id=review.id))
    assert len(rows) == 1  # still one row — upserted, not duplicated
    assert rows[0].body == "v2 — refined"


def test_assessment_visibility_subject_vs_manager(org):
    review = _make_review(org, employee=org.report)
    with tenant_context(org.tenant):
        ReviewAssessmentFactory(
            review=review, assessor=org.report, assessment_type="SELF", body="mine"
        )
        ReviewAssessmentFactory(
            review=review, assessor=org.manager, assessment_type="MANAGER", body="boss"
        )

    # The subject (OWN scope) sees ONLY their own SELF row.
    emp_rows = _client_for(org.report).get(f"{REVIEWS}{review.id}/assessments").json()
    assert [r["assessment_type"] for r in emp_rows] == ["SELF"]
    assert emp_rows[0]["assessor"] == str(org.report.id)

    # The manager sees all of the review's assessments.
    mgr_rows = _client_for(org.manager).get(f"{REVIEWS}{review.id}/assessments").json()
    assert {r["assessment_type"] for r in mgr_rows} == {"SELF", "MANAGER"}


def test_employee_cannot_submit_manager_assessment(org):
    review = _make_review(org, employee=org.report)
    emp = _client_for(org.report)  # EMPLOYEE lacks SUBMIT_ASSESSMENT
    resp = emp.post(
        f"{REVIEWS}{review.id}/assessments",
        {"assessment_type": "MANAGER", "body": "Nope."},
        format="json",
    )
    assert resp.status_code == 403


# ── the Agent-1 seam: request-ai-draft is async (enqueue + poll) ───────────


def test_request_ai_draft_enqueues_job_and_degrades_without_provider(org):
    """Async seam: the endpoint returns 202 + an AI job; with no provider the
    (eager) job DEGRADES and the review is never stranded (stays DRAFT)."""
    review = _make_review(org, state="DRAFT")
    mgr = _client_for(org.manager)

    resp = mgr.post(f"{REVIEWS}{review.id}/request-ai-draft")
    assert resp.status_code == 202
    body = resp.json()
    assert body["agent_code"] == "agent1"
    assert body["target_type"] == "review"
    assert body["target_id"] == str(review.id)

    with tenant_context(org.tenant):
        job = AIJob.objects.get(id=body["id"])
        assert job.status == AIJob.Status.DEGRADED  # no provider -> graceful
        assert job.error_code == "NOT_CONFIGURED"

    # The loud seam never strands the review: still DRAFT, manual path open.
    after = mgr.get(f"{REVIEWS}{review.id}")
    assert after.status_code == 200
    assert after.json()["state"] == "DRAFT"


@override_settings(
    LLM_PROVIDER="apps.ai.providers.FakeLLMProvider",
    REVIEW_ASSISTANT_PROVIDER="apps.ai.agents.review.ReviewAssistantProvider",
)
def test_request_ai_draft_async_locks_pending_when_wired(org):
    """With a provider wired, the enqueued job runs (eager) and the HITL gate is
    preserved: the review ends PENDING_HUMAN_REVIEW, exactly as the sync seam did."""
    review = _make_review(org, state="DRAFT")
    mgr = _client_for(org.manager)

    resp = mgr.post(f"{REVIEWS}{review.id}/request-ai-draft")
    assert resp.status_code == 202
    assert resp.json()["target_id"] == str(review.id)

    with tenant_context(org.tenant):
        job = AIJob.objects.get(id=resp.json()["id"])
        assert job.status == AIJob.Status.SUCCEEDED
    after = mgr.get(f"{REVIEWS}{review.id}")
    assert after.json()["state"] == "PENDING_HUMAN_REVIEW"  # HITL lock preserved


# ── audit trail ────────────────────────────────────────────────────────────


def test_full_flow_writes_the_audit_trail(org):
    """review.created / review.approved / review.finalized rows exist after the
    flow (review.rejected is asserted in the reject test)."""
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    mgr = _client_for(org.manager)
    review_id = mgr.post(
        REVIEWS,
        {"employee": str(org.report.id), "cycle": str(cycle.id)},
        format="json",
    ).json()["id"]
    mgr.post(f"{REVIEWS}{review_id}/start-edit")
    mgr.post(f"{REVIEWS}{review_id}/submit", {"draft_body": "Done."}, format="json")
    mgr.post(f"{REVIEWS}{review_id}/approve")
    mgr.post(f"{REVIEWS}{review_id}/finalize")

    with tenant_context(org.tenant):
        for action in ("review.created", "review.approved", "review.finalized"):
            assert AuditLog.objects.filter(action=action).exists(), action
