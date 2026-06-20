"""
HTTP tests for the Succession & Talent API, hitting the REAL
``/api/succession/...`` routes (production urlconf — no ``@pytest.mark.urls``).

Succession is the MOST SENSITIVE data in the system. The headline theme is the
SENSITIVITY rule: there is NO employee access to ANY endpoint — an employee gets a
404 (NOT a 403) everywhere, so the module never leaks its own existence.

Themes:
  * the END-TO-END HITL flow over HTTP (HRBP): mark critical role → add bench →
    assess 9-box → generate (PENDING_HUMAN_REVIEW) → action-item → publish →
    dashboard shows the coverage;
  * coverage RED: a role whose only bench candidate has no CycleScore;
  * SENSITIVITY: an EMPLOYEE 404s on EVERY endpoint (even their own 9-box);
  * Manager scope: own report in-tier (200/201), a peer's report out-of-tier
    (404), dashboard scoped;
  * Manager lacking an HRBP-only capability → 403 (a participant, but not the
    cap);
  * cross-tenant isolation (404);
  * the Agent-4 seam → 503 (no_provider), the deterministic plan left intact;
  * the HITL status contract: 409 ILLEGAL_PLAN_TRANSITION on a double publish;
  * the unauthenticated 401.
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai.models import AIJob
from apps.goals.models import CycleScore
from apps.identity.tokens import issue_tokens_for_user
from apps.succession.models import SuccessionPlan
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, UserFactory

pytestmark = pytest.mark.django_db

SUCC = "/api/succession/"


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


# ── END-TO-END: the HITL flow over HTTP (HRBP) ────────────────────────────────


def test_e2e_hitl_flow_hrbp(org):
    hrbp = _client_for(org.hrbp)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    # A strong CycleScore + HIGH potential makes the report a READY_NOW successor.
    _score(org.tenant, org.report, cycle, 70)

    # 1. Mark a critical role (knowledge_risk HIGH) → 201.
    resp = hrbp.post(
        f"{SUCC}critical-roles",
        {
            "name": "Head of Platform",
            "criticality": "CRITICAL",
            "knowledge_risk": "HIGH",
            "incumbent": str(org.manager.id),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    role = resp.json()
    assert role["knowledge_risk"] == "HIGH"
    assert role["criticality"] == "CRITICAL"
    assert role["status"] == "ACTIVE"
    role_id = role["id"]

    # 2. Add a bench candidate (org.report) → 201.
    resp = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.report.id), "notes": "Strong successor"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["candidate"] == str(org.report.id)

    # 3. Assess the report's 9-box (HIGH potential + HIGH perf score → box 9).
    resp = hrbp.post(
        f"{SUCC}nine-box",
        {
            "employee": str(org.report.id),
            "cycle": str(cycle.id),
            "potential_band": "HIGH",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    placement = resp.json()
    assert placement["performance_band"] == "HIGH"
    assert placement["potential_band"] == "HIGH"
    assert placement["box"] == 9

    # 4. Generate the analysis → 201 PENDING_HUMAN_REVIEW with ranked bench + coverage.
    resp = hrbp.post(f"{SUCC}critical-roles/{role_id}/generate", {}, format="json")
    assert resp.status_code == 201, resp.content
    plan = resp.json()
    assert plan["status"] == "PENDING_HUMAN_REVIEW"
    assert plan["source"] == "DETERMINISTIC"
    assert plan["coverage_status"] == "GREEN"
    assert len(plan["ranked_bench"]) == 1
    assert plan["ranked_bench"][0]["readiness"] == "READY_NOW"
    plan_id = plan["id"]

    # 5. Add an action item during review → 200.
    resp = hrbp.post(
        f"{SUCC}plans/{plan_id}/action-item",
        {"item": "Shadow the incumbent for one quarter"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert len(resp.json()["action_items"]) == 1

    # 6. Publish → 200 PUBLISHED.
    resp = hrbp.post(f"{SUCC}plans/{plan_id}/publish", {}, format="json")
    assert resp.status_code == 200, resp.content
    published = resp.json()
    assert published["status"] == "PUBLISHED"
    assert published["reviewed_by"] == str(org.hrbp.id)
    assert published["published_at"] is not None

    # 7. The dashboard shows the role with its published coverage.
    resp = hrbp.get(f"{SUCC}dashboard")
    assert resp.status_code == 200, resp.content
    roles = resp.json()["critical_roles"]
    by_id = {r["id"]: r for r in roles}
    assert role_id in by_id
    assert by_id[role_id]["coverage_status"] == "GREEN"
    assert by_id[role_id]["published_plan"] == plan_id


# ── coverage RED: a bench candidate with no CycleScore ────────────────────────


def test_coverage_red_when_only_candidate_has_no_score(org):
    hrbp = _client_for(org.hrbp)
    resp = hrbp.post(
        f"{SUCC}critical-roles",
        {"name": "Lone Wolf Role", "criticality": "CRITICAL"},
        format="json",
    )
    role_id = resp.json()["id"]
    # org.peer has NO CycleScore → readiness NOT_READY → coverage RED.
    resp = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.peer.id)},
        format="json",
    )
    assert resp.status_code == 201, resp.content

    resp = hrbp.post(f"{SUCC}critical-roles/{role_id}/generate", {}, format="json")
    assert resp.status_code == 201, resp.content
    plan = resp.json()
    assert plan["coverage_status"] == "RED"
    assert plan["red_flags"]  # non-empty
    assert plan["red_flags"][0]["code"] == "INADEQUATE_COVERAGE"


# ── SENSITIVITY: an EMPLOYEE 404s on EVERY endpoint (NOT 403) ─────────────────


def test_employee_gets_404_on_every_endpoint(org):
    """The headline rule: succession is invisible to employees. Every endpoint —
    including the employee's OWN 9-box — returns 404, never 403, so the module
    does not leak its own existence."""
    # Seed real rows (as HRBP) so the 404s are the participant gate, not empties.
    hrbp = _client_for(org.hrbp)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle, 70)
    role_id = hrbp.post(
        f"{SUCC}critical-roles", {"name": "Secret Role"}, format="json"
    ).json()["id"]
    hrbp.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.report.id)},
        format="json",
    )
    hrbp.post(
        f"{SUCC}nine-box",
        {
            "employee": str(org.report.id),
            "cycle": str(cycle.id),
            "potential_band": "HIGH",
        },
        format="json",
    )
    plan_id = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/generate", {}, format="json"
    ).json()["id"]

    emp = _client_for(org.report)  # the EMPLOYEE — even their own data is invisible

    # Reads.
    assert emp.get(f"{SUCC}dashboard").status_code == 404
    assert emp.get(f"{SUCC}critical-roles").status_code == 404
    assert emp.get(f"{SUCC}critical-roles/{role_id}").status_code == 404
    assert emp.get(f"{SUCC}critical-roles/{role_id}/bench").status_code == 404
    assert emp.get(f"{SUCC}nine-box").status_code == 404  # their OWN 9-box, too
    assert emp.get(f"{SUCC}plans/{plan_id}").status_code == 404

    # Writes.
    assert (
        emp.post(
            f"{SUCC}critical-roles", {"name": "x"}, format="json"
        ).status_code
        == 404
    )
    assert (
        emp.post(
            f"{SUCC}nine-box",
            {
                "employee": str(org.report.id),
                "cycle": str(cycle.id),
                "potential_band": "HIGH",
            },
            format="json",
        ).status_code
        == 404
    )
    assert (
        emp.post(
            f"{SUCC}critical-roles/{role_id}/generate", {}, format="json"
        ).status_code
        == 404
    )
    assert (
        emp.post(f"{SUCC}plans/{plan_id}/publish", {}, format="json").status_code
        == 404
    )


# ── Manager scope: own tier vs out-of-tier (404) ──────────────────────────────


def test_manager_can_act_within_their_tier(org):
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    _score(org.tenant, org.report, cycle, 55)

    # HRBP marks a role whose incumbent is the manager's report — that puts the
    # role inside the manager's reporting tier, so the manager (a participant with
    # VIEW/MANAGE_BENCH/ASSESS) can add to its bench and assess their report's
    # 9-box. (A role touching no-one in the manager's tier is invisible — 404 — by
    # the locked service scope rule.)
    role_id = hrbp.post(
        f"{SUCC}critical-roles",
        {"name": "Team Lead", "incumbent": str(org.report.id)},
        format="json",
    ).json()["id"]

    resp = mgr.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.report.id)},
        format="json",
    )
    assert resp.status_code == 201, resp.content

    resp = mgr.post(
        f"{SUCC}nine-box",
        {
            "employee": str(org.report.id),
            "cycle": str(cycle.id),
            "potential_band": "MEDIUM",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content


def test_manager_out_of_tier_target_is_404(org):
    """A peer's report (org.peer) is OUT of the manager's reporting subtree, so the
    service hides them with a 404 (not a 403)."""
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)
    cycle = CycleFactory(tenant=org.tenant, status="ACTIVE")
    # An IN-TIER role (incumbent is the manager's report) so the role itself is
    # visible — the 404 below is specifically about the out-of-tier CANDIDATE,
    # not an out-of-scope role.
    role_id = hrbp.post(
        f"{SUCC}critical-roles",
        {"name": "Some Role", "incumbent": str(org.report.id)},
        format="json",
    ).json()["id"]

    # Manager assessing org.peer's 9-box → 404 (out of tier).
    resp = mgr.post(
        f"{SUCC}nine-box",
        {
            "employee": str(org.peer.id),
            "cycle": str(cycle.id),
            "potential_band": "HIGH",
        },
        format="json",
    )
    assert resp.status_code == 404, resp.content

    # Manager adding org.peer to a bench → 404 (out of tier).
    resp = mgr.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.peer.id)},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_manager_dashboard_is_scoped(org):
    """A manager's dashboard shows roles touching their tier (a role with their
    report on the bench), not a peer-only role (its only candidate is org.peer)."""
    hrbp = _client_for(org.hrbp)
    mgr = _client_for(org.manager)

    in_tier = hrbp.post(
        f"{SUCC}critical-roles", {"name": "In-tier Role"}, format="json"
    ).json()["id"]
    hrbp.post(
        f"{SUCC}critical-roles/{in_tier}/bench",
        {"candidate": str(org.report.id)},
        format="json",
    )

    peer_only = hrbp.post(
        f"{SUCC}critical-roles", {"name": "Peer-only Role"}, format="json"
    ).json()["id"]
    hrbp.post(
        f"{SUCC}critical-roles/{peer_only}/bench",
        {"candidate": str(org.peer.id)},
        format="json",
    )

    resp = mgr.get(f"{SUCC}dashboard")
    assert resp.status_code == 200, resp.content
    ids = {r["id"] for r in resp.json()["critical_roles"]}
    assert in_tier in ids
    assert peer_only not in ids


# ── Manager lacking an HRBP-only capability → 403 (participant, not the cap) ───


def test_manager_lacks_hrbp_capabilities_403(org):
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)

    # POST /critical-roles is MANAGE_CRITICAL_ROLES (HRBP+) → 403 for a manager.
    resp = mgr.post(f"{SUCC}critical-roles", {"name": "Nope"}, format="json")
    assert resp.status_code == 403, resp.content

    # Set up a role + plan as HRBP for the generate / publish checks.
    role_id = hrbp.post(
        f"{SUCC}critical-roles", {"name": "Role"}, format="json"
    ).json()["id"]
    hrbp.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.report.id)},
        format="json",
    )
    plan_id = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/generate", {}, format="json"
    ).json()["id"]

    # generate (GENERATE_SUCCESSION_ANALYSIS, HRBP+) → 403 for a manager.
    resp = mgr.post(f"{SUCC}critical-roles/{role_id}/generate", {}, format="json")
    assert resp.status_code == 403, resp.content

    # publish (PUBLISH_SUCCESSION_PLAN, HRBP+) → 403 for a manager.
    resp = mgr.post(f"{SUCC}plans/{plan_id}/publish", {}, format="json")
    assert resp.status_code == 403, resp.content


# ── cross-tenant isolation (404) ──────────────────────────────────────────────


def test_cross_tenant_is_404(org, other_tenant):
    hrbp = _client_for(org.hrbp)
    role_id = hrbp.post(
        f"{SUCC}critical-roles", {"name": "Acme Role"}, format="json"
    ).json()["id"]
    hrbp.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.report.id)},
        format="json",
    )
    plan_id = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/generate", {}, format="json"
    ).json()["id"]

    # A management user in a DIFFERENT tenant must not see org's rows.
    other_hrbp = UserFactory(tenant=other_tenant, role="HRBP")
    other = _client_for(other_hrbp)

    assert other.get(f"{SUCC}critical-roles/{role_id}").status_code == 404
    assert other.get(f"{SUCC}plans/{plan_id}").status_code == 404


# ── Agent-4 seam → async (enqueue+poll); the deterministic plan stays intact ──


def test_agent4_enrich_enqueues_job_degraded_and_plan_unchanged(org):
    hrbp = _client_for(org.hrbp)
    role_id = hrbp.post(
        f"{SUCC}critical-roles", {"name": "AI-curious Role"}, format="json"
    ).json()["id"]
    hrbp.post(
        f"{SUCC}critical-roles/{role_id}/bench",
        {"candidate": str(org.report.id)},
        format="json",
    )
    plan_id = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/generate", {}, format="json"
    ).json()["id"]

    # Enqueue → 202 + an AI job; the (eager) job DEGRADES with no provider.
    resp = hrbp.post(f"{SUCC}plans/{plan_id}/enrich", {}, format="json")
    assert resp.status_code == 202, resp.content
    body = resp.json()
    assert body["agent_code"] == "agent4"
    assert body["target_id"] == plan_id
    with tenant_context(org.tenant):
        job = AIJob.objects.get(id=body["id"])
        assert job.status == AIJob.Status.DEGRADED
        assert job.error_code == "NOT_CONFIGURED"

    # The deterministic plan is left COMPLETELY INTACT.
    resp = hrbp.get(f"{SUCC}plans/{plan_id}")
    assert resp.status_code == 200, resp.content
    plan = resp.json()
    assert plan["status"] == "PENDING_HUMAN_REVIEW"
    assert plan["source"] == "DETERMINISTIC"

    # And no new AI plan was created for the role.
    with tenant_context(org.tenant):
        assert not SuccessionPlan.objects.filter(
            critical_role_id=role_id, source=SuccessionPlan.Source.AI
        ).exists()


# ── HITL status contract: 409 on a double publish ─────────────────────────────


def test_double_publish_is_409(org):
    hrbp = _client_for(org.hrbp)
    role_id = hrbp.post(
        f"{SUCC}critical-roles", {"name": "Publish-twice Role"}, format="json"
    ).json()["id"]
    plan_id = hrbp.post(
        f"{SUCC}critical-roles/{role_id}/generate", {}, format="json"
    ).json()["id"]

    assert hrbp.post(f"{SUCC}plans/{plan_id}/publish", {}, format="json").status_code == 200
    resp = hrbp.post(f"{SUCC}plans/{plan_id}/publish", {}, format="json")
    assert resp.status_code == 409, resp.content
    assert resp.json()["code"] == "ILLEGAL_PLAN_TRANSITION"


# ── unauthenticated → 401 ─────────────────────────────────────────────────────


def test_unauthenticated_is_401(org):
    resp = APIClient().get(f"{SUCC}dashboard")
    assert resp.status_code == 401
