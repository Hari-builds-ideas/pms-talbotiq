"""
HTTP tests for the Feedback API, hitting the REAL ``/api/feedback/...`` routes
(production urlconf — no ``@pytest.mark.urls``).

Themes:
  * the END-TO-END 360 flow over HTTP: create → open → invite → give ×5 →
    close → anonymised view (ZERO giver identifiers — the headline guarantee,
    proven by scanning the serialized response) → HRBP review queue → approve
    → the subject reads the RELEASED summary;
  * anti-spoof: a client-supplied ``giver`` is ignored — always request.user;
  * the invitation gate: no invitation → 403, one submission per invitation;
  * cross-peer privacy: no API surface returns another giver's identity;
  * the cycle fences over HTTP: 409 before open / after close / edit-after-close;
  * the anonymity-breach and sensitive HRBP_HOLD paths;
  * continuous feedback: recipient sees words, never the author;
  * 1:1 notes: private to the two participants — even Admin is locked out;
  * RBAC capability + scope gates, cross-tenant isolation (404);
  * the Agent-3 seam (re-summarize): 503 ``no_provider`` / 409 not-CLOSED;
  * the audit trail for every consequential action.
"""
import json

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    FeedbackCycleFactory,
    FeedbackRequestFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

FB = "/api/feedback/"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _give(user, cycle_id, body, **extra):
    return _client_for(user).post(
        f"{FB}cycles/{cycle_id}/give", {"body": body, **extra}, format="json"
    )


def _invited_collecting_cycle(org, *, givers=(), min_volume=None, **cycle_kwargs):
    """A COLLECTING cycle for org.report with PENDING PEER invitations for
    ``givers`` (built via factories — invitation mechanics are tested over
    HTTP in the E2E test)."""
    cycle = FeedbackCycleFactory(
        subject=org.report, min_volume=min_volume, **cycle_kwargs
    )
    for giver in givers:
        FeedbackRequestFactory(cycle=cycle, giver=giver, relationship="PEER")
    return cycle


# ── 1. end-to-end: the 360 flow over HTTP ───────────────────────────────────


def test_e2e_360_flow(org):
    mgr = _client_for(org.manager)
    subject = _client_for(org.report)
    hrbp = _client_for(org.hrbp)

    # Create → 201 DRAFT.
    created = mgr.post(FB + "cycles", {"subject": str(org.report.id)}, format="json")
    assert created.status_code == 201
    assert created.json()["status"] == "DRAFT"
    assert created.json()["subject"] == str(org.report.id)
    cycle_id = created.json()["id"]

    # Open → 200 COLLECTING.
    opened = mgr.post(f"{FB}cycles/{cycle_id}/open")
    assert opened.status_code == 200
    assert opened.json()["status"] == "COLLECTING"

    # Invitations: SELF→report, MANAGER→manager, PEER→3 peers (201 ×5).
    peers = [
        UserFactory(tenant=org.tenant, role="EMPLOYEE", email=f"e2epeer{i}@acme.test")
        for i in range(3)
    ]
    invitees = [
        (org.report, "SELF"),
        (org.manager, "MANAGER"),
        *[(p, "PEER") for p in peers],
    ]
    for giver, relationship in invitees:
        resp = mgr.post(
            f"{FB}cycles/{cycle_id}/requests",
            {"giver": str(giver.id), "relationship": relationship},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert resp.json()["status"] == "PENDING"

    # Each invitee gives feedback → 201; the giver is server-set and the
    # giver's own echo carries no giver field at all.
    bodies = {
        org.report.id: "I grew a lot this year.",
        org.manager.id: "Delivered consistently across the roadmap.",
        peers[0].id: "Great collaborator on the migration.",
        peers[1].id: "Communicates clearly in incidents.",
        peers[2].id: "Could delegate more during crunches.",
    }
    for giver, _ in invitees:
        resp = _give(giver, cycle_id, bodies[giver.id])
        assert resp.status_code == 201, resp.content
        assert "giver" not in resp.json()

    # Close → 200; the seam result is embedded (no provider until Module 10).
    closed = mgr.post(f"{FB}cycles/{cycle_id}/close")
    assert closed.status_code == 200
    assert closed.json()["cycle"]["status"] == "CLOSED"
    assert closed.json()["summary"]["reason"] == "no_provider"

    # The subject reads the anonymised payload: ZERO giver identifiers.
    anon = subject.get(f"{FB}cycles/{cycle_id}/anonymized")
    assert anon.status_code == 200
    payload = anon.json()
    blob = json.dumps(payload).lower()
    for giver in [org.report, org.manager, *peers]:
        assert giver.email.lower() not in blob
    # The ONLY id allowed anywhere is the subject's (the declared subject_id
    # field) — plus the cycle's own id. No giver UUID appears.
    assert payload["subject_id"] == str(org.report.id)
    for giver in [org.manager, *peers]:
        assert str(giver.id) not in blob
    # PEER group present (3 ≥ default threshold) with opaque pseudonyms.
    peer_group = payload["groups"]["PEER"]
    assert len(peer_group) == 3
    assert {e["pseudonym"] for e in peer_group} == {"PEER#1", "PEER#2", "PEER#3"}

    # The summary exists but is NOT released → the subject gets 403.
    held = subject.get(f"{FB}cycles/{cycle_id}/summary")
    assert held.status_code == 403
    assert held.json()["code"] == "SUMMARY_NOT_RELEASED"

    # HRBP review queue contains it (PENDING_HUMAN_REVIEW — clean path).
    queue = hrbp.get(FB + "summaries/review")
    assert queue.status_code == 200
    row = next(r for r in queue.json() if r["cycle"] == cycle_id)
    assert row["status"] == "PENDING_HUMAN_REVIEW"
    assert row["anonymity_passed"] is True
    assert "reviewed_by" not in row  # reviewer identity never egresses

    # HRBP approves → RELEASED.
    approved = hrbp.post(f"{FB}summaries/{row['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "RELEASED"

    # The subject now reads it: RELEASED, sections still null (no Agent 3 —
    # Module 4 never fabricates theme text).
    released = subject.get(f"{FB}cycles/{cycle_id}/summary")
    assert released.status_code == 200
    assert released.json()["status"] == "RELEASED"
    assert released.json()["sections"] is None
    assert released.json()["released_at"] is not None
    assert "reviewed_by" not in released.json()


# ── 2. anti-spoof: giver is ALWAYS request.user ─────────────────────────────


def test_client_supplied_giver_is_ignored(org):
    from apps.feedback.models import Feedback

    cycle = _invited_collecting_cycle(org, givers=[org.peer])
    resp = _client_for(org.peer).post(
        f"{FB}cycles/{cycle.id}/give",
        {"body": "Honest words.", "giver": str(org.manager.id)},  # spoof attempt
        format="json",
    )
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    # The DB records the ACTING user as the giver, not the spoofed id.
    with tenant_context(org.tenant):
        item = Feedback.objects.get(pk=item_id)
        assert item.giver_id == org.peer.id

    # And the giver sees it under /mine (their own attributed list).
    mine = _client_for(org.peer).get(FB + "mine").json()
    assert item_id in {row["id"] for row in mine}


# ── 3. the invitation gate ──────────────────────────────────────────────────


def test_give_requires_pending_invitation_and_is_single_use(org):
    cycle = _invited_collecting_cycle(org, givers=[org.peer])
    uninvited = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="lurker@acme.test")

    # No invitation → 403 INVITATION_REQUIRED.
    refused = _give(uninvited, cycle.id, "Unsolicited.")
    assert refused.status_code == 403
    assert refused.json()["code"] == "INVITATION_REQUIRED"

    # A PENDING invitation authorises exactly one submission.
    first = _give(org.peer, cycle.id, "My one take.")
    assert first.status_code == 201

    # The invitation is consumed (SUBMITTED) → a second give is 403.
    second = _give(org.peer, cycle.id, "A second take.")
    assert second.status_code == 403
    assert second.json()["code"] == "INVITATION_REQUIRED"


def test_giver_can_list_and_decline_own_invitation(org):
    cycle = _invited_collecting_cycle(org, givers=[org.peer])
    peer = _client_for(org.peer)

    mine = peer.get(FB + "requests/mine")
    assert mine.status_code == 200
    [row] = [r for r in mine.json() if r["cycle"] == str(cycle.id)]
    assert row["giver"] == str(org.peer.id)
    assert row["status"] == "PENDING"

    declined = peer.post(f"{FB}requests/{row['id']}/decline")
    assert declined.status_code == 200
    assert declined.json()["status"] == "DECLINED"

    # Only the invited giver may decline.
    other_cycle = _invited_collecting_cycle(org, givers=[org.report])
    with tenant_context(org.tenant):
        foreign_invite = other_cycle.requests.first()
    assert peer.post(f"{FB}requests/{foreign_invite.id}/decline").status_code == 400


# ── 4. cross-peer privacy ───────────────────────────────────────────────────


def test_no_surface_leaks_another_givers_identity(org):
    peer_a = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="peer.a@acme.test")
    peer_b = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="peer.b@acme.test")
    cycle = _invited_collecting_cycle(org, givers=[peer_a, peer_b])

    a_item = _give(peer_a, cycle.id, "Note from the first colleague.")
    b_item = _give(peer_b, cycle.id, "Note from the second colleague.")
    assert a_item.status_code == 201 and b_item.status_code == 201
    assert _client_for(org.manager).post(f"{FB}cycles/{cycle.id}/close").status_code == 200

    b = _client_for(peer_b)

    # A fellow giver is NOT a permitted reader of the anonymised view — and the
    # refusal itself leaks nothing about peer A.
    anon = b.get(f"{FB}cycles/{cycle.id}/anonymized")
    assert anon.status_code == 403
    blob = json.dumps(anon.json()).lower()
    assert peer_a.email.lower() not in blob
    assert str(peer_a.id) not in blob

    # /mine shows B only B's own item — never A's.
    mine = b.get(FB + "mine").json()
    assert {row["id"] for row in mine} == {b_item.json()["id"]}

    # The cycle's invitation list (the only giver-bearing listing) is for the
    # managing surface only — a peer holds no MANAGE_FEEDBACK_CYCLE → 403.
    assert b.get(f"{FB}cycles/{cycle.id}/requests").status_code == 403


# ── 5. cycle fences over HTTP ───────────────────────────────────────────────


def test_cycle_fences_409(org):
    # Before open (DRAFT): 409 CYCLE_NOT_COLLECTING.
    draft = _invited_collecting_cycle(org, givers=[org.peer], status="DRAFT")
    early = _give(org.peer, draft.id, "Too early.")
    assert early.status_code == 409
    assert early.json()["code"] == "CYCLE_NOT_COLLECTING"

    # After close: an unconsumed invitation still cannot submit (409), and a
    # submitted item becomes immutable (409 FEEDBACK_IMMUTABLE).
    late_giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="late@acme.test")
    cycle = _invited_collecting_cycle(org, givers=[org.peer, late_giver])
    submitted = _give(org.peer, cycle.id, "In the window.")
    assert submitted.status_code == 201
    assert _client_for(org.manager).post(f"{FB}cycles/{cycle.id}/close").status_code == 200

    late = _give(late_giver, cycle.id, "Too late.")
    assert late.status_code == 409
    assert late.json()["code"] == "CYCLE_NOT_COLLECTING"

    frozen = _client_for(org.peer).patch(
        f"{FB}items/{submitted.json()['id']}", {"body": "Rewritten."}, format="json"
    )
    assert frozen.status_code == 409
    assert frozen.json()["code"] == "FEEDBACK_IMMUTABLE"


# ── 6. the anonymity-breach hold path ───────────────────────────────────────


def test_breach_holds_summary_until_hrbp_approves(org):
    giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="whistle@acme.test")
    cycle = _invited_collecting_cycle(org, givers=[giver], min_volume=1)
    # The body names another tenant user's email — a de-anonymisation vector.
    leak = _give(giver, cycle.id, f"Ask {org.peer.email} about the outage.")
    assert leak.status_code == 201
    assert _client_for(org.manager).post(f"{FB}cycles/{cycle.id}/close").status_code == 200

    hrbp = _client_for(org.hrbp)
    row = next(
        r for r in hrbp.get(FB + "summaries/review").json() if r["cycle"] == str(cycle.id)
    )
    assert row["status"] == "HRBP_HOLD"
    assert row["anonymity_passed"] is False

    # Held → the subject cannot read it.
    subject = _client_for(org.report)
    blocked = subject.get(f"{FB}cycles/{cycle.id}/summary")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "SUMMARY_NOT_RELEASED"

    # The HRBP reviewed and cleared the hold → the subject reads it.
    assert hrbp.post(f"{FB}summaries/{row['id']}/approve").status_code == 200
    assert subject.get(f"{FB}cycles/{cycle.id}/summary").status_code == 200


# ── 7. the sensitive hold path ──────────────────────────────────────────────


def test_marked_sensitive_holds_summary(org):
    giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="careful@acme.test")
    cycle = _invited_collecting_cycle(org, givers=[giver], min_volume=1)
    resp = _give(giver, cycle.id, "A serious concern, handled discreetly.", marked_sensitive=True)
    assert resp.status_code == 201
    assert resp.json()["giver_marked_sensitive"] is True
    assert _client_for(org.manager).post(f"{FB}cycles/{cycle.id}/close").status_code == 200

    row = next(
        r
        for r in _client_for(org.hrbp).get(FB + "summaries/review").json()
        if r["cycle"] == str(cycle.id)
    )
    assert row["status"] == "HRBP_HOLD"
    assert row["sensitive"] is True


# ── 8. continuous feedback ──────────────────────────────────────────────────


def test_continuous_feedback_recipient_never_sees_the_giver(org):
    giver = _client_for(org.peer)
    body = "Your incident writeups are consistently excellent."
    created = giver.post(
        FB + "continuous", {"subject": str(org.report.id), "body": body}, format="json"
    )
    assert created.status_code == 201
    assert created.json()["kind"] == "CONTINUOUS"

    # The recipient sees the words — and NO giver field anywhere.
    received = _client_for(org.report).get(FB + "received")
    assert received.status_code == 200
    [row] = [r for r in received.json() if r["body"] == body]
    assert "giver" not in row
    assert str(org.peer.id) not in json.dumps(received.json())

    # The giver sees it attributed under their own /mine.
    mine = giver.get(FB + "mine").json()
    assert any(r["body"] == body and r["subject"] == str(org.report.id) for r in mine)

    # Self-directed continuous feedback is rejected.
    selfie = giver.post(
        FB + "continuous", {"subject": str(org.peer.id), "body": "I am great."}, format="json"
    )
    assert selfie.status_code == 400


# ── 9. 1:1 notes — participants ONLY ────────────────────────────────────────


def test_one_on_one_notes_are_private_to_participants(org, other_tenant):
    mgr = _client_for(org.manager)
    created = mgr.post(
        FB + "one-on-ones",
        {
            "manager": str(org.manager.id),
            "employee": str(org.report.id),
            "body": "Discussed growth plan and Q3 scope.",
            "meeting_date": "2026-06-01",
        },
        format="json",
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    # Both participants read it (and see it in their listing).
    for participant in (org.manager, org.report):
        client = _client_for(participant)
        assert client.get(f"{FB}one-on-ones/{note_id}").status_code == 200
        assert note_id in {r["id"] for r in client.get(FB + "one-on-ones").json()}

    # NOBODY else: a peer, the HRBP, even the ADMIN → 403; their listings are empty.
    for outsider in (org.peer, org.hrbp, org.admin):
        client = _client_for(outsider)
        assert client.get(f"{FB}one-on-ones/{note_id}").status_code == 403
        assert note_id not in {r["id"] for r in client.get(FB + "one-on-ones").json()}

    # A participant edits; a non-participant cannot.
    patched = mgr.patch(
        f"{FB}one-on-ones/{note_id}", {"body": "Amended after the call."}, format="json"
    )
    assert patched.status_code == 200
    assert patched.json()["body"] == "Amended after the call."
    assert (
        _client_for(org.admin)
        .patch(f"{FB}one-on-ones/{note_id}", {"body": "x"}, format="json")
        .status_code
        == 403
    )

    # The creator must BE a participant.
    not_mine = _client_for(org.hrbp).post(
        FB + "one-on-ones",
        {
            "manager": str(org.manager.id),
            "employee": str(org.report.id),
            "body": "Ghost-written.",
            "meeting_date": "2026-06-01",
        },
        format="json",
    )
    assert not_mine.status_code == 403

    # Cross-tenant: an outsider's token binds THEIR tenant → 404.
    outsider = UserFactory(tenant=other_tenant, role="ADMIN")
    assert _client_for(outsider).get(f"{FB}one-on-ones/{note_id}").status_code == 404


# ── 10. RBAC + tenant isolation ─────────────────────────────────────────────


def test_rbac_and_tenant_isolation(org, other_tenant):
    # An EMPLOYEE lacks MANAGE_FEEDBACK_CYCLE → 403.
    refused = _client_for(org.report).post(
        FB + "cycles", {"subject": str(org.report.id)}, format="json"
    )
    assert refused.status_code == 403

    # A peer manager (no reports) holds the capability but org.report is
    # outside their subtree → scope-on-create 403.
    peer_manager = UserFactory(tenant=org.tenant, role="MANAGER", email="pm@acme.test")
    out_of_scope = _client_for(peer_manager).post(
        FB + "cycles", {"subject": str(org.report.id)}, format="json"
    )
    assert out_of_scope.status_code == 403

    # The review queue is HRBP/Admin-only.
    assert _client_for(org.report).get(FB + "summaries/review").status_code == 403
    assert _client_for(org.manager).get(FB + "summaries/review").status_code == 403

    # Cross-tenant: a foreign cycle never resolves — 404 on every route shape.
    outsider = UserFactory(tenant=other_tenant, role="EMPLOYEE")
    foreign = FeedbackCycleFactory(subject=outsider, status="CLOSED")
    mgr = _client_for(org.manager)
    assert mgr.post(f"{FB}cycles/{foreign.id}/open").status_code == 404
    assert mgr.get(f"{FB}cycles/{foreign.id}/anonymized").status_code == 404
    assert mgr.get(f"{FB}cycles/{foreign.id}/summary").status_code == 404
    # And a foreign manager's listing never contains our cycles.
    ours = FeedbackCycleFactory(subject=org.report)
    foreign_admin = UserFactory(tenant=other_tenant, role="ADMIN")
    listed = _client_for(foreign_admin).get(FB + "cycles").json()
    assert str(ours.id) not in {row["id"] for row in listed}


def test_anonymized_view_access_matrix(org):
    """Subject / scoped manager / HRBP / Admin read it; an unrelated employee
    and an out-of-scope manager do not; 409 while not CLOSED."""
    giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="g1@acme.test")
    cycle = _invited_collecting_cycle(org, givers=[giver], min_volume=1)
    assert _give(giver, cycle.id, "Fine work.").status_code == 201

    # Not CLOSED yet → 409 even for the subject.
    early = _client_for(org.report).get(f"{FB}cycles/{cycle.id}/anonymized")
    assert early.status_code == 409

    assert _client_for(org.manager).post(f"{FB}cycles/{cycle.id}/close").status_code == 200

    for allowed in (org.report, org.manager, org.hrbp, org.admin):
        assert (
            _client_for(allowed).get(f"{FB}cycles/{cycle.id}/anonymized").status_code == 200
        ), allowed.role
    peer_manager = UserFactory(tenant=org.tenant, role="MANAGER", email="pm2@acme.test")
    for denied in (org.peer, peer_manager):
        assert (
            _client_for(denied).get(f"{FB}cycles/{cycle.id}/anonymized").status_code == 403
        ), denied.role


# ── 11. the Agent-3 seam: /summarize ────────────────────────────────────────


def test_summarize_endpoint_seam(org):
    giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="s1@acme.test")
    cycle = _invited_collecting_cycle(org, givers=[giver], min_volume=1)
    assert _give(giver, cycle.id, "Clean and clear.").status_code == 201
    mgr = _client_for(org.manager)

    # Not CLOSED → 409.
    early = mgr.post(f"{FB}cycles/{cycle.id}/summarize")
    assert early.status_code == 409
    assert early.json()["code"] == "ILLEGAL_CYCLE_TRANSITION"

    assert mgr.post(f"{FB}cycles/{cycle.id}/close").status_code == 200

    # CLOSED but no provider → 503, loudly pointing at Module 10.
    resp = mgr.post(f"{FB}cycles/{cycle.id}/summarize")
    assert resp.status_code == 503
    body = resp.json()
    assert body["reason"] == "no_provider"
    assert "Module 10" in body["detail"]


# ── 12. the audit trail ─────────────────────────────────────────────────────


def test_full_flow_writes_the_audit_trail(org):
    mgr = _client_for(org.manager)
    hrbp = _client_for(org.hrbp)
    giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="a1@acme.test")

    # Clean path: create → open → invite → give → close → approve.
    cycle_id = mgr.post(
        FB + "cycles", {"subject": str(org.report.id), "min_volume": 1}, format="json"
    ).json()["id"]
    assert mgr.post(f"{FB}cycles/{cycle_id}/open").status_code == 200
    assert (
        mgr.post(
            f"{FB}cycles/{cycle_id}/requests",
            {"giver": str(giver.id), "relationship": "PEER"},
            format="json",
        ).status_code
        == 201
    )
    assert _give(giver, cycle_id, "Audit-worthy diligence.").status_code == 201
    assert mgr.post(f"{FB}cycles/{cycle_id}/close").status_code == 200
    row = next(r for r in hrbp.get(FB + "summaries/review").json() if r["cycle"] == cycle_id)
    assert hrbp.post(f"{FB}summaries/{row['id']}/approve").status_code == 200

    with tenant_context(org.tenant):
        for action in (
            "feedback_cycle.opened",
            "feedback_cycle.closed",
            "feedback.submitted",
            "summary.generated",
            "summary.approved",
            "summary.released",
        ):
            assert AuditLog.objects.filter(action=action).exists(), action

    # Breach path additionally audits the hold.
    breach_giver = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="a2@acme.test")
    breach_cycle = _invited_collecting_cycle(org, givers=[breach_giver], min_volume=1)
    assert (
        _give(breach_giver, breach_cycle.id, f"Talk to {org.peer.email}.").status_code == 201
    )
    assert mgr.post(f"{FB}cycles/{breach_cycle.id}/close").status_code == 200
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="summary.held_for_hrbp").exists()
