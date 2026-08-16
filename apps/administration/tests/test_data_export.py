"""
``GET /api/admin/users/<id>/export`` — the data subject access request (D1).

The tests that matter here are not "does it return 200". They are:

  * the export is COMPLETE — a person's review bodies, feedback, check-ins,
    nine-box placement and login history are all in it. An access request that
    quietly omits the succession assessment is worse than no endpoint;
  * the export never leaks a FEEDBACK GIVER. ``apps/feedback`` guarantees the
    giver identity leaves the API only to the giver themselves, and an export is
    a brand-new egress boundary — precisely where such a guarantee gets broken by
    accident. The proof scans the whole serialised payload for every giver's id
    and email, the same shape of proof ``apps/feedback`` uses for its own
    anonymised payloads;
  * it is Admin-only and tenant-scoped.
"""
import json

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


GIVER_EMAIL = "threesixty-giver@acme.test"


def _export_url(user):
    return f"/api/admin/users/{user.id}/export"


@pytest.fixture
def populated(org):
    """A subject with something in every category the export claims to cover."""
    from apps.checkins.models import CheckIn
    from apps.cycles.models import PerformanceCycle
    from apps.feedback.models import Feedback, FeedbackCycle
    from apps.goals.models import Goal, Kpi
    from apps.identity.models import LoginEvent
    from apps.recognition.models import Recognition
    from apps.reviews.models import Review, ReviewComment
    from apps.succession.models import NineBoxPlacement

    subject = org.report
    t = org.tenant
    with tenant_context(t):
        cycle = PerformanceCycle.objects.create(
            tenant=t, name="H1 2026", start_date="2026-01-01", end_date="2026-06-30",
        )
        goal = Goal.objects.create(
            tenant=t, employee=subject, created_by=org.manager, cycle=cycle,
            title="Ship the billing rewrite", description="Own it end to end",
            objective="Revenue", weight="1.00",
        )
        Kpi.objects.create(
            tenant=t, goal=goal, name="Invoices migrated", weight="1.00",
            target_value="100", direction="UP", unit="count",
        )
        review = Review.objects.create(
            tenant=t, employee=subject, reviewer=org.manager, cycle=cycle,
            draft_body="Consistently strong quarter.",
            final_body="Consistently strong quarter, promoted.",
        )
        ReviewComment.objects.create(
            tenant=t, review=review, author=org.manager, section="summary",
            body="Agreed with the rating.",
        )
        fcycle = FeedbackCycle.objects.create(tenant=t, subject=subject, opened_by=org.hrbp)
        # A giver who appears in NO other role, so the leak scan below cannot be
        # satisfied by an id that legitimately belongs somewhere else.
        giver = UserFactory(tenant=t, email=GIVER_EMAIL, role="EMPLOYEE")
        Feedback.objects.create(
            tenant=t, cycle=fcycle, subject=subject, giver=giver,
            relationship="PEER", kind="THREE_SIXTY",
            body="Unblocks people before they ask.",
        )
        Feedback.objects.create(
            tenant=t, subject=org.peer, giver=subject,
            relationship="PEER", kind="CONTINUOUS",
            body="Great handover on the migration.",
        )
        CheckIn.objects.create(
            tenant=t, author=subject, week_of="2026-03-02", mood=4,
            wins="Closed the migration", blockers="Waiting on infra",
            learning="Read up on binlogs",
        )
        Recognition.objects.create(
            tenant=t, sender=org.manager, recipient=subject,
            value="Ownership", message="Took the pager without being asked.",
        )
        NineBoxPlacement.objects.create(
            tenant=t, employee=subject, cycle=cycle,
            performance_band="HIGH", potential_band="HIGH", box="9",
            assessed_by=org.hrbp, assessed_at=timezone.now(),
            override_rationale="Ready now.",
        )
        LoginEvent.objects.create(
            tenant=t, user=subject, email=subject.email, event="LOGIN_SUCCESS",
            ip="203.0.113.9", user_agent="Firefox",
        )
    return subject


# ── completeness ──────────────────────────────────────────────────────────────


def test_the_export_covers_every_category_it_claims_to(org, populated):
    """An access request that silently omits a category is the failure mode —
    nobody reading the response can tell the difference between "no succession
    assessment exists" and "the export forgot to look"."""
    resp = _client_for(org.admin).get(_export_url(populated))
    assert resp.status_code == 200, resp.content
    data = resp.json()

    assert data["profile"]["email"] == populated.email
    assert data["goals"][0]["title"] == "Ship the billing rewrite"
    assert data["goals"][0]["kpis"][0]["name"] == "Invoices migrated"
    assert "Consistently strong quarter" in data["reviews"][0]["draft_body"]
    assert data["reviews"][0]["comments"][0]["body"] == "Agreed with the rating."
    assert data["feedback_received"][0]["body"] == "Unblocks people before they ask."
    assert data["feedback_given"][0]["body"] == "Great handover on the migration."
    assert data["check_ins"][0]["blockers"] == "Waiting on infra"
    assert data["recognition_received"][0]["message"].startswith("Took the pager")
    assert data["succession"]["nine_box_placements"][0]["box"] == 9
    assert data["login_history"][0]["ip"] == "203.0.113.9"
    assert data["reporting_line"]["manager"]["id"] == str(org.manager.id)


def test_the_succession_assessment_is_included_even_though_it_is_unflattering(org, populated):
    """A person is normally never shown their own nine-box placement or bench
    notes. It is still data held about them, so it is exported — the protection
    is that the endpoint is Admin-only, not that the record is hidden."""
    data = _client_for(org.admin).get(_export_url(populated)).json()
    placement = data["succession"]["nine_box_placements"][0]
    assert placement["override_rationale"] == "Ready now."


# ── the anonymity guarantee, at a new egress boundary ─────────────────────────


def test_no_feedback_giver_identity_appears_anywhere_in_the_export(org, populated):
    """The proof, not a spot check: scan the ENTIRE serialised payload.

    ``apps/feedback`` states the guarantee module-wide — the giver leaves the API
    only to the giver themselves. Asserting on the shape of one dict would pass
    while a giver id rode along inside some nested structure added later, so the
    whole document is searched for the giver's UUID and email.
    """
    from apps.identity.models import User

    with tenant_context(org.tenant):
        giver = User.objects.get(email=GIVER_EMAIL)
    body = json.dumps(_client_for(org.admin).get(_export_url(populated)).json())

    assert str(giver.id) not in body, "a feedback giver's id leaked into the export"
    assert giver.email not in body, "a feedback giver's email leaked into the export"


def test_the_relationship_label_is_withheld_for_a_group_too_small_to_be_anonymous(
    org, populated
):
    """Removing the giver id is not enough on its own. "The one PEER comment on
    your 360" identifies its author to anybody who knows who was invited, which
    is why the module gates groups below MIN_FEEDBACK_VOLUME."""
    from apps.administration.data_rights import WITHHELD_SMALL_GROUP

    data = _client_for(org.admin).get(_export_url(populated)).json()
    cycle_item = [f for f in data["feedback_received"] if f["kind"] == "THREE_SIXTY"][0]
    assert cycle_item["relationship"] == WITHHELD_SMALL_GROUP
    # The body still ships: it is data about the subject, and withholding it
    # would defeat the request the export exists to answer.
    assert cycle_item["body"] == "Unblocks people before they ask."


def test_a_group_at_the_threshold_keeps_its_label(org, populated):
    from apps.feedback.models import Feedback, FeedbackCycle

    t = org.tenant
    with tenant_context(t):
        fcycle = FeedbackCycle.objects.filter(subject=populated).first()
        for i in range(2):
            giver = UserFactory(tenant=t, email=f"peer{i}@acme.test", role="EMPLOYEE")
            Feedback.objects.create(
                tenant=t, cycle=fcycle, subject=populated, giver=giver,
                relationship="PEER", kind="THREE_SIXTY", body=f"Peer view {i}.",
            )
    data = _client_for(org.admin).get(_export_url(populated)).json()
    labels = {f["relationship"] for f in data["feedback_received"] if f["kind"] == "THREE_SIXTY"}
    assert labels == {"PEER"}, labels


# ── access control ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["hrbp", "manager", "report"])
def test_only_an_admin_may_export(org, populated, role):
    """HRBP is tenant-wide by design and can already see a lot — but a single
    document containing somebody's entire performance history is a different
    thing from the screens it was assembled from."""
    actor = getattr(org, role)
    assert _client_for(actor).get(_export_url(populated)).status_code == 403


def test_an_id_from_another_tenant_is_a_404_not_a_403(org, other_tenant):
    """404, so the endpoint cannot be used to learn whether a person exists in
    another tenant. The scoped manager never sees the row."""
    stranger = UserFactory(tenant=other_tenant, email="someone@globex.test")
    assert _client_for(org.admin).get(_export_url(stranger)).status_code == 404


def test_unauthenticated_is_401(org, populated):
    assert APIClient().get(_export_url(populated)).status_code == 401


# ── the access is itself recorded ─────────────────────────────────────────────


def test_the_export_is_audited_with_the_subject(org, populated):
    """An admin reading an employee's whole record is legitimate and sensitive at
    the same time. The audit console is where that becomes visible afterwards."""
    from apps.audit.models import AuditLog

    _client_for(org.admin).get(_export_url(populated))
    with tenant_context(org.tenant):
        row = AuditLog.objects.filter(action="privacy.user_exported").latest("created_at")
    assert row.actor_id == org.admin.id
    assert row.target_id == str(populated.id)
