"""Service-level rules: cycle fences, the invitation flow, uniqueness, edits."""
import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditLog
from apps.feedback.exceptions import (
    CycleNotCollecting,
    FeedbackImmutable,
    IllegalCycleTransition,
    InvitationRequired,
)
from apps.feedback.models import Feedback, FeedbackCycle, FeedbackRequest
from apps.feedback.services import (
    close_cycle,
    decline_request,
    edit_own_feedback,
    give_continuous_feedback,
    give_feedback_360,
    open_cycle,
    send_feedback_request,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    FeedbackCycleFactory,
    FeedbackFactory,
    FeedbackRequestFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def draft_cycle(org):
    return FeedbackCycleFactory(subject=org.report, status="DRAFT")


@pytest.fixture
def collecting_cycle(org):
    return FeedbackCycleFactory(subject=org.report, status="COLLECTING")


# ── cycle transitions ──────────────────────────────────────────────────────


def test_open_then_close_with_audit(org, draft_cycle):
    open_cycle(draft_cycle, org.manager)
    assert draft_cycle.status == "COLLECTING" and draft_cycle.opened_at is not None
    cycle, job = close_cycle(draft_cycle, org.manager)
    assert cycle.status == "CLOSED" and cycle.closed_at is not None
    # The summarize seam is now async: close enqueues an AIJob that (eager)
    # degrades gracefully with no provider configured; the gates still ran.
    with tenant_context(org.tenant):
        job.refresh_from_db()
        assert job.status == "DEGRADED" and job.error_code == "NOT_CONFIGURED"
        actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"feedback_cycle.opened", "feedback_cycle.closed"} <= actions


def test_illegal_cycle_transitions_409(org, draft_cycle, collecting_cycle):
    with pytest.raises(IllegalCycleTransition):
        close_cycle(draft_cycle, org.manager)  # close from DRAFT
    open_cycle(draft_cycle, org.manager)
    with pytest.raises(IllegalCycleTransition):
        open_cycle(draft_cycle, org.manager)  # open twice
    close_cycle(collecting_cycle, org.manager)
    with pytest.raises(IllegalCycleTransition):
        close_cycle(collecting_cycle, org.manager)  # close twice


# ── invitations: the designated-reviewer flow ──────────────────────────────


def test_peer_with_invitation_can_submit_and_without_cannot(org, collecting_cycle):
    with pytest.raises(InvitationRequired):
        give_feedback_360(cycle=collecting_cycle, giver=org.peer, body="hi")
    send_feedback_request(
        cycle=collecting_cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    item = give_feedback_360(cycle=collecting_cycle, giver=org.peer, body="Great teammate.")
    assert item.relationship == "PEER"  # comes from the invitation, not the client
    with tenant_context(org.tenant):
        req = FeedbackRequest.objects.get(cycle=collecting_cycle, giver=org.peer)
    assert req.status == "SUBMITTED"


def test_one_submission_per_giver(org, collecting_cycle):
    send_feedback_request(
        cycle=collecting_cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    give_feedback_360(cycle=collecting_cycle, giver=org.peer, body="one")
    # The invitation is consumed (SUBMITTED): a second submit is unauthorised.
    with pytest.raises(InvitationRequired):
        give_feedback_360(cycle=collecting_cycle, giver=org.peer, body="two")


def test_self_invitation_only_to_subject(org, collecting_cycle):
    with pytest.raises(ValidationError):
        send_feedback_request(
            cycle=collecting_cycle, giver=org.peer, relationship="SELF", actor=org.manager
        )
    with pytest.raises(ValidationError):
        # The subject may hold only the SELF invitation.
        send_feedback_request(
            cycle=collecting_cycle, giver=org.report, relationship="PEER", actor=org.manager
        )
    send_feedback_request(
        cycle=collecting_cycle, giver=org.report, relationship="SELF", actor=org.manager
    )
    item = give_feedback_360(cycle=collecting_cycle, giver=org.report, body="self view")
    assert item.relationship == "SELF"


def test_one_invitation_per_giver(org, collecting_cycle):
    send_feedback_request(
        cycle=collecting_cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    with pytest.raises(ValidationError):
        send_feedback_request(
            cycle=collecting_cycle, giver=org.peer, relationship="UPWARD", actor=org.manager
        )


def test_decline_only_by_giver_while_pending(org, collecting_cycle):
    req = send_feedback_request(
        cycle=collecting_cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    with pytest.raises(ValidationError):
        decline_request(req, org.manager)  # not the giver
    decline_request(req, org.peer)
    assert req.status == "DECLINED"
    with pytest.raises(ValidationError):
        decline_request(req, org.peer)  # not pending anymore
    # A declined invitation no longer authorises a submission.
    with pytest.raises(InvitationRequired):
        give_feedback_360(cycle=collecting_cycle, giver=org.peer, body="late")


# ── cycle fences ───────────────────────────────────────────────────────────


def test_feedback_only_while_collecting(org, draft_cycle):
    send_feedback_request(
        cycle=draft_cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    with pytest.raises(CycleNotCollecting):
        give_feedback_360(cycle=draft_cycle, giver=org.peer, body="too early")
    open_cycle(draft_cycle, org.manager)
    give_feedback_360(cycle=draft_cycle, giver=org.peer, body="on time")
    close_cycle(draft_cycle, org.manager)
    # After close: another invited giver can no longer submit.
    send_invite_fails = False
    try:
        send_feedback_request(
            cycle=draft_cycle, giver=org.hrbp, relationship="PEER", actor=org.manager
        )
    except IllegalCycleTransition:
        send_invite_fails = True
    assert send_invite_fails


def test_edit_own_feedback_until_close(org, collecting_cycle):
    send_feedback_request(
        cycle=collecting_cycle, giver=org.peer, relationship="PEER", actor=org.manager
    )
    item = give_feedback_360(cycle=collecting_cycle, giver=org.peer, body="v1")
    with pytest.raises(ValidationError):
        edit_own_feedback(item, org.manager, body="not yours")  # only the giver
    edit_own_feedback(item, org.peer, body="v2")
    assert item.body == "v2"
    close_cycle(collecting_cycle, org.manager)
    with pytest.raises(FeedbackImmutable):
        edit_own_feedback(item, org.peer, body="v3")  # immutable after close


# ── continuous feedback ────────────────────────────────────────────────────


def test_continuous_feedback_is_cycle_less_and_not_self(org):
    item = give_continuous_feedback(subject=org.report, giver=org.peer, body="nice work")
    assert item.cycle_id is None and item.kind == "CONTINUOUS"
    with pytest.raises(ValidationError):
        give_continuous_feedback(subject=org.peer, giver=org.peer, body="self pat")


def test_many_continuous_items_coexist_despite_unique_constraint(org):
    # MySQL NULL-distinct semantics: the (tenant, cycle, giver) constraint only
    # binds when cycle is set.
    give_continuous_feedback(subject=org.report, giver=org.peer, body="one")
    give_continuous_feedback(subject=org.report, giver=org.peer, body="two")
    with tenant_context(org.tenant):
        assert Feedback.objects.filter(giver=org.peer, cycle__isnull=True).count() == 2


def test_db_constraint_blocks_second_360_row(org, collecting_cycle):
    # Belt-and-braces under the service rule: a direct second row violates the DB.
    FeedbackFactory(cycle=collecting_cycle, giver=org.peer, relationship="PEER")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FeedbackFactory(cycle=collecting_cycle, giver=org.peer, relationship="PEER")


# ── isolation ──────────────────────────────────────────────────────────────


def test_cross_tenant_isolation_on_feedback_models(org, other_tenant):
    cycle = FeedbackCycleFactory(subject=org.report)
    FeedbackFactory(cycle=cycle, giver=org.peer, relationship="PEER")
    with tenant_context(other_tenant):
        assert FeedbackCycle.objects.filter(id=cycle.id).count() == 0
        assert Feedback.objects.count() == 0
