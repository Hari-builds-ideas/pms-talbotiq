"""
``POST /api/admin/users/<id>/erase`` — irreversible erasure (D2).

What these tests are actually for. The easy half (their profile is anonymised)
is not where this goes wrong. The failures that matter are the ones that look
like success:

  * content the person wrote ABOUT OTHER PEOPLE being erased along with them,
    which silently rewrites somebody else's review history;
  * the audit log losing a row, or the erasure managing to update one;
  * a live access token surviving, because "revoke their sessions" was
    implemented as "delete their sessions" and ``session_is_revoked()`` reads a
    missing row as NOT revoked;
  * a second call failing after a timed-out first one;
  * tenant isolation quietly not applying to the most destructive endpoint in
    the product.
"""
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.administration.erasure import REDACTED, TOMBSTONE_EMAIL_DOMAIN
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _erase_url(user):
    return f"/api/admin/users/{user.id}/erase"


def _erase(admin, subject, **overrides):
    body = {
        "confirm": subject.email,
        "justification": "Erasure requested by the employee after leaving.",
    }
    body.update(overrides)
    return _client_for(admin).post(_erase_url(subject), body, format="json")


@pytest.fixture
def leaver(org):
    """A departing employee with content in both directions: things written about
    them, and things they wrote about other people."""
    from apps.checkins.models import CheckIn
    from apps.cycles.models import PerformanceCycle
    from apps.feedback.models import Feedback
    from apps.goals.models import Goal
    from apps.identity.models import DeviceSession, LoginEvent
    from apps.recognition.models import Recognition
    from apps.reviews.models import Review, ReviewComment

    subject = org.report
    t = org.tenant
    with tenant_context(t):
        cycle = PerformanceCycle.objects.create(
            tenant=t, name="H1 2026", start_date="2026-01-01", end_date="2026-06-30",
        )
        # ── about them ──
        Goal.objects.create(
            tenant=t, employee=subject, created_by=org.manager, cycle=cycle,
            title="Ship billing", description="Own it", objective="Revenue", weight="1.00",
        )
        review = Review.objects.create(
            tenant=t, employee=subject, reviewer=org.manager, cycle=cycle,
            draft_body="Strong quarter.", final_body="Strong quarter, promoted.",
        )
        ReviewComment.objects.create(
            tenant=t, review=review, author=org.manager, section="summary",
            body="I agree with the rating.",
        )
        Feedback.objects.create(
            tenant=t, subject=subject, giver=org.peer, relationship="PEER",
            kind="CONTINUOUS", body="Very easy to work with.",
        )
        CheckIn.objects.create(
            tenant=t, author=subject, week_of="2026-03-02", mood=4,
            wins="Closed the migration", blockers="Infra", learning="Binlogs",
        )
        Recognition.objects.create(
            tenant=t, sender=org.manager, recipient=subject,
            value="Ownership", message="Took the pager.",
        )
        # ── written BY them, about somebody else ──
        peer_review = Review.objects.create(
            tenant=t, employee=org.peer, reviewer=org.manager, cycle=cycle,
            draft_body="Peer had a solid half.", final_body="Peer had a solid half.",
        )
        ReviewComment.objects.create(
            tenant=t, review=peer_review, author=subject, section="summary",
            body="I worked with them on the migration and would again.",
        )
        Feedback.objects.create(
            tenant=t, subject=org.peer, giver=subject, relationship="PEER",
            kind="CONTINUOUS", body="Handled the on-call week without drama.",
        )
        Recognition.objects.create(
            tenant=t, sender=subject, recipient=org.peer,
            value="Teamwork", message="Covered for me while I was out.",
        )
        DeviceSession.objects.create(
            tenant=t, user=subject, ip="203.0.113.9", user_agent="Firefox",
            last_seen=timezone.now(),
        )
        LoginEvent.objects.create(
            tenant=t, user=subject, email=subject.email, event="LOGIN_SUCCESS",
            ip="203.0.113.9", user_agent="Firefox",
        )
    return subject


# ── the person is gone ────────────────────────────────────────────────────────


def test_the_profile_is_tombstoned_not_deleted(org, leaver):
    """The row survives on purpose: it is the pseudonymous id that every piece of
    content they authored now points at, and it is what makes historical audit
    rows render a pseudonym without the append-only log being touched."""
    from apps.identity.models import User

    resp = _erase(org.admin, leaver)
    assert resp.status_code == 200, resp.content

    with tenant_context(org.tenant):
        row = User.objects.get(pk=leaver.id)
    assert row.email.endswith(f"@{TOMBSTONE_EMAIL_DOMAIN}")
    assert row.display_name.startswith("Former employee ")
    assert (row.phone, row.title, row.department, row.employee_id) == ("", "", "", "")
    assert row.preferences == {}
    assert row.is_active is False
    assert row.has_usable_password() is False
    assert row.erased_at is not None
    # Still inside its tenant: a tombstone outside one would be visible to every
    # tenant through the unscoped manager.
    assert row.tenant_id == org.tenant.id


def test_content_about_them_is_redacted_with_a_marker_not_emptied(org, leaver):
    """An empty string cannot be told apart from "nobody wrote anything". A
    reviewer looking at a blank assessment would not know whether the process
    failed or the content was removed on request."""
    from apps.checkins.models import CheckIn
    from apps.cycles.models import PerformanceCycle
    from apps.feedback.models import Feedback
    from apps.goals.models import Goal
    from apps.reviews.models import Review

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        review = Review.objects.get(employee=leaver)
        goal = Goal.objects.get(employee=leaver)
        checkin = CheckIn.objects.get(author=leaver)
        received = Feedback.objects.get(subject=leaver)

    assert review.draft_body == REDACTED and review.final_body == REDACTED
    assert goal.title == REDACTED and goal.description == REDACTED
    assert checkin.wins == REDACTED and checkin.blockers == REDACTED
    assert received.body == REDACTED


def test_the_rows_themselves_are_kept(org, leaver):
    """Deleting them would change every aggregate that counts them — a cycle's
    score distribution shifts and nothing says why. Numbers stay, words go."""
    from apps.reviews.models import Review

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        assert Review.objects.filter(employee=leaver).count() == 1


# ── other people's history survives ───────────────────────────────────────────


def test_what_they_wrote_about_others_is_kept_verbatim(org, leaver):
    """The asymmetry that makes this design work. Erasing their words would
    silently rewrite the peer's review history: a rating that was justified by
    this input becomes unexplainable, and nobody is told."""
    from apps.feedback.models import Feedback
    from apps.recognition.models import Recognition
    from apps.reviews.models import ReviewComment

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        comment = ReviewComment.objects.get(review__employee=org.peer)
        given = Feedback.objects.get(subject=org.peer, giver=leaver)
        sent = Recognition.objects.get(recipient=org.peer)

    assert comment.body == "I worked with them on the migration and would again."
    assert given.body == "Handled the on-call week without drama."
    assert sent.message == "Covered for me while I was out."


def test_their_authorship_becomes_the_stable_pseudonym(org, leaver):
    """Not a nulled author. Two comments from "—" are unreadable; two from
    "Former employee 4f2a" are still a conversation."""
    from apps.reviews.models import ReviewComment

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        comment = ReviewComment.objects.select_related("author").get(review__employee=org.peer)

    assert comment.author_id == leaver.id
    assert comment.author.display.startswith("Former employee ")


def test_the_managers_own_words_about_them_are_redacted_but_his_authorship_stands(
    org, leaver
):
    """A manager's comment on the leaver's review is content ABOUT the leaver, so
    the text goes — but it stays attributed to the manager, who has not been
    erased."""
    from apps.reviews.models import ReviewComment

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        comment = ReviewComment.objects.get(review__employee=leaver)
    assert comment.body == REDACTED
    assert comment.author_id == org.manager.id


# ── the audit log ─────────────────────────────────────────────────────────────


def test_nothing_is_deleted_from_the_audit_log(org, leaver):
    """The table has BEFORE UPDATE and BEFORE DELETE triggers at the MySQL level.
    Erasure gets no exception from them — that immunity is the reason the log is
    worth anything."""
    from apps.audit.models import AuditLog

    with tenant_context(org.tenant):
        from apps.audit.services import record

        record(action="review.approved", actor=leaver, target_type="review",
               target_id="x", tenant=org.tenant)
        before = AuditLog.objects.count()

    _erase(org.admin, leaver)

    with tenant_context(org.tenant):
        after = AuditLog.objects.count()
    # Strictly more: the erasure adds its own row and removes none.
    assert after > before


def test_historical_audit_rows_render_the_pseudonym_without_being_touched(org, leaver):
    """The whole mechanism: the display changes because the row it REFERENCES
    changed. No audit row is written, updated or deleted to achieve it."""
    from apps.audit.models import AuditLog
    from apps.audit.services import record

    with tenant_context(org.tenant):
        entry = record(action="review.approved", actor=leaver, target_type="review",
                       target_id="x", tenant=org.tenant)
        original_updated = entry.created_at

    _erase(org.admin, leaver)

    with tenant_context(org.tenant):
        reloaded = AuditLog.objects.select_related("actor").get(pk=entry.pk)
    assert reloaded.created_at == original_updated
    assert reloaded.actor_id == leaver.id
    assert reloaded.actor.display.startswith("Former employee ")


def test_the_erasure_is_audited_with_its_justification(org, leaver):
    from apps.audit.models import AuditLog

    _erase(org.admin, leaver, justification="Subject exercised their right to erasure.")
    with tenant_context(org.tenant):
        row = AuditLog.objects.filter(action="privacy.user_erased").latest("created_at")
    assert row.actor_id == org.admin.id
    assert row.target_id == str(leaver.id)
    assert "right to erasure" in row.justification


# ── sessions ──────────────────────────────────────────────────────────────────


def test_every_session_is_revoked_and_the_rows_are_kept(org, leaver):
    """Kept deliberately. ``session_is_revoked()`` reads a MISSING row as NOT
    revoked (tokens without a matching session are not rejected — it was an
    additive rollout), so deleting the sessions here would hand the erased
    account a working access token until it expired on its own."""
    from apps.identity.models import DeviceSession
    from apps.identity.security import session_is_revoked

    with tenant_context(org.tenant):
        session = DeviceSession.objects.filter(user=leaver).first()
    assert session_is_revoked(str(session.id)) is False

    _erase(org.admin, leaver)

    with tenant_context(org.tenant):
        assert DeviceSession.objects.filter(user=leaver).exists()
    assert session_is_revoked(str(session.id)) is True


def test_the_session_rows_keep_nothing_about_them(org, leaver):
    from apps.identity.models import DeviceSession

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        for session in DeviceSession.objects.filter(user=leaver):
            assert session.ip is None
            assert session.user_agent == ""


def test_login_history_is_really_deleted_not_soft_deleted(org, leaver):
    """A movement log — IP, user agent, the address they typed — that no other
    person's record depends on. It goes.

    Checked through ``all_objects``, which still sees soft-deleted rows. On a
    TenantScopedQuerySet ``.delete()`` STAMPS deleted_at and leaves the row
    intact, so an erasure written the obvious way reports success while every IP
    and email is still in the table. Asserting through the default manager would
    pass in exactly that case.
    """
    from apps.identity.models import LoginEvent

    _erase(org.admin, leaver)
    with tenant_context(org.tenant):
        assert LoginEvent.all_objects.filter(user=leaver).count() == 0


# ── safety rails ──────────────────────────────────────────────────────────────


def test_erasing_twice_is_a_retry_not_an_error(org, leaver):
    """The second call is usually a retry after a timeout, and the caller has no
    way to know whether the first one landed. A 409 would invite them to "fix" it
    with something more destructive."""
    first = _erase(org.admin, leaver)
    assert first.status_code == 200
    assert first.json()["already_erased"] is False

    with tenant_context(org.tenant):
        from apps.identity.models import User

        tombstoned = User.objects.get(pk=leaver.id)

    second = _client_for(org.admin).post(
        _erase_url(leaver),
        {"confirm": tombstoned.email, "justification": "Retry after a timeout."},
        format="json",
    )
    assert second.status_code == 200, second.content
    assert second.json()["already_erased"] is True


def test_a_wrong_confirmation_erases_nothing(org, leaver):
    """The mistake that actually happens is acting on the row below the one you
    meant, so the confirmation is this person's own address rather than a fixed
    word that becomes muscle memory."""
    from apps.identity.models import User

    resp = _erase(org.admin, leaver, confirm="someone.else@acme.test")
    assert resp.status_code == 422, resp.content
    with tenant_context(org.tenant):
        assert User.objects.get(pk=leaver.id).erased_at is None


def test_a_missing_or_trivial_justification_is_refused(org, leaver):
    """It lands in an append-only log, and whoever reads that row later cannot go
    and look at the data to work out what happened — erasing it was the point."""
    assert _client_for(org.admin).post(
        _erase_url(leaver), {"confirm": leaver.email}, format="json"
    ).status_code == 400
    assert _erase(org.admin, leaver, justification="test").status_code == 400


def test_an_admin_cannot_erase_themselves(org):
    resp = _erase(org.admin, org.admin)
    assert resp.status_code == 422
    assert "second person" in resp.json()["detail"]


@pytest.mark.parametrize("role", ["hrbp", "manager", "report"])
def test_only_an_admin_may_erase(org, leaver, role):
    actor = getattr(org, role)
    assert _client_for(actor).post(
        _erase_url(leaver),
        {"confirm": leaver.email, "justification": "Attempting without the capability."},
        format="json",
    ).status_code == 403


def test_a_subject_in_another_tenant_is_a_404(org, other_tenant):
    """Tenant isolation applies to the most destructive endpoint in the product,
    through the same scoped manager as everything else — not a bespoke check that
    could be forgotten."""
    from apps.identity.models import User

    stranger = UserFactory(tenant=other_tenant, email="someone@globex.test")
    resp = _client_for(org.admin).post(
        _erase_url(stranger),
        {"confirm": stranger.email, "justification": "Cross-tenant attempt."},
        format="json",
    )
    assert resp.status_code == 404
    with tenant_context(other_tenant):
        assert User.objects.get(pk=stranger.id).erased_at is None


def test_a_failure_partway_through_erases_nothing(org, leaver):
    """One transaction, because a half-erased person — profile anonymised, review
    bodies still readable — is worse than either outcome, and it is precisely
    what a timeout produces without it."""
    from unittest.mock import patch

    from apps.identity.models import User
    from apps.reviews.models import Review

    with patch("apps.administration.erasure._tombstone", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            _erase(org.admin, leaver)

    with tenant_context(org.tenant):
        assert User.objects.get(pk=leaver.id).erased_at is None
        assert Review.objects.get(employee=leaver).draft_body == "Strong quarter."


def test_the_export_of_an_erased_person_shows_the_redaction(org, leaver):
    """Not an empty document. Someone auditing the erasure afterwards needs to
    see that content was removed on request, not that it never existed."""
    _erase(org.admin, leaver)
    data = _client_for(org.admin).get(f"/api/admin/users/{leaver.id}/export").json()
    assert data["profile"]["erased_at"] is not None
    assert data["reviews"][0]["draft_body"] == REDACTED


def test_a_frozen_identity_snapshot_in_a_succession_plan_is_scrubbed(org, leaver):
    """The one place tombstoning does not reach on its own.

    ``succession/engine.py`` writes ``candidate_email`` and ``candidate_name``
    into ``ranked_bench`` as denormalised TEXT. Every screen that renders a live
    foreign key shows the pseudonym correctly after an erasure, which is exactly
    what makes this copy easy to miss: the product looks right while the person's
    name and email are still sitting in a JSON column.
    """
    import json

    from django.utils import timezone

    from apps.succession.models import CriticalRole, SuccessionPlan

    with tenant_context(org.tenant):
        role = CriticalRole.objects.create(
            tenant=org.tenant, name="Head of Billing", marked_by=org.hrbp,
            criticality="HIGH",
        )
        plan = SuccessionPlan.objects.create(
            tenant=org.tenant, critical_role=role, coverage_status="AMBER",
            generated_at=timezone.now(),
            ranked_bench=[{
                "candidate_id": str(leaver.id),
                "candidate_email": leaver.email,
                "candidate_name": leaver.display,
                "readiness": "READY_SOON",
                "performance_band": "HIGH",
                "readiness_overridden": False,
            }],
        )

    _erase(org.admin, leaver)

    with tenant_context(org.tenant):
        plan.refresh_from_db()
    body = json.dumps(plan.ranked_bench)
    assert leaver.email not in body
    assert plan.ranked_bench[0]["candidate_name"].startswith("Former employee ")
    # The ENTRY stays: removing a candidate would retroactively change the plan's
    # coverage assessment, which is a statement about the role, not the person.
    assert plan.ranked_bench[0]["readiness"] == "READY_SOON"
