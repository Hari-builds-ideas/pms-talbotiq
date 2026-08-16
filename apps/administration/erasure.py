"""
Erasure (D2) — irreversible. Read ``docs/BUILD/DATA_RIGHTS_DESIGN.md`` before
changing anything here; the field-by-field decisions and their reasons live there.

The shape of it: content **about** the person is redacted, content they
**authored about others** keeps its text and has its author repointed at a
tombstone, and the audit log is never written to, updated or deleted.

The tombstone is the user row itself, mutated — not a separate pseudonym table
and not a nulled foreign key. That is what makes every historical audit row
render as ``Former employee 4f2a`` without the append-only log being touched at
all: the display changes because the row it references changed.
"""
from __future__ import annotations

from django.db.models import Q

from .data_rights import _iso

#: What replaces redacted free text. NOT an empty string: "" is indistinguishable
#: from "nobody wrote anything", so a reviewer looking at a blank assessment
#: cannot tell whether the process failed or the content was removed on request.
REDACTED = "[redacted — erased at the subject's request]"

#: Reserved by RFC 2606, so it can never route anywhere.
TOMBSTONE_EMAIL_DOMAIN = "erased.invalid"


class CannotErase(Exception):
    """An erasure that must not proceed. Surfaces as a 422."""


def _tombstone_email() -> str:
    """A unique, non-routable address.

    Unique per erasure rather than a fixed sentinel: ``(tenant, email)`` is a
    unique constraint, so a constant would make the SECOND erasure in a tenant
    die with an IntegrityError — halfway through, after the redaction had already
    run.
    """
    from uuid import uuid4

    return f"erased+{uuid4().hex}@{TOMBSTONE_EMAIL_DOMAIN}"


# ── redaction, by category ────────────────────────────────────────────────────


def _redact_reviews(subject) -> int:
    """Reviews OF this person, plus the assessments and comments on them.

    Rows are updated, never deleted. A missing review changes what the cycle
    looks like in every aggregate that counts it; a redacted one keeps the shape
    of history honest. Numbers stay, words go.

    The assessors and commenters keep their authorship: this is content *about*
    the subject, so the text goes and the author remains.
    """
    from apps.reviews.models import (
        Review,
        ReviewAssessment,
        ReviewComment,
        ReviewStateTransition,
    )

    reviews = Review.objects.filter(employee=subject)
    review_ids = list(reviews.values_list("id", flat=True))
    reviews.update(draft_body=REDACTED, final_body=REDACTED, rejected_reason="", citations=[])
    ReviewAssessment.objects.filter(review_id__in=review_ids).update(body=REDACTED)
    ReviewComment.objects.filter(review_id__in=review_ids).update(body=REDACTED)
    ReviewStateTransition.objects.filter(review_id__in=review_ids).update(note="")
    return len(review_ids)


def _redact_feedback(subject) -> int:
    from apps.feedback.models import Feedback, FeedbackSummary, OneOnOneNote

    received = Feedback.objects.filter(subject=subject)
    count = received.count()
    received.update(body=REDACTED, sentiment=None)
    FeedbackSummary.objects.filter(subject=subject).update(sections={}, insufficient_groups=[])
    # Both directions: a 1:1 note is a conversation about the employee, whichever
    # side typed it.
    OneOnOneNote.objects.filter(Q(employee=subject) | Q(manager=subject)).update(body=REDACTED)
    return count


def _redact_goals(subject) -> int:
    """Goals and the update threads on them.

    Goals are per-employee here (``Goal.employee`` is a single FK), so redacting
    one cannot damage a shared record. If team goals are ever added this needs
    revisiting — a shared goal's title is other people's data too.
    """
    from apps.goals.models import Goal, GoalUpdate

    goals = Goal.objects.filter(employee=subject)
    goal_ids = list(goals.values_list("id", flat=True))
    goals.update(title=REDACTED, description=REDACTED, objective=REDACTED)
    GoalUpdate.objects.filter(goal_id__in=goal_ids).update(text=REDACTED)
    return len(goal_ids)


def _redact_checkins(subject) -> int:
    from apps.checkins.models import CheckIn, CheckInPriority, ManagerResponse

    checkins = CheckIn.objects.filter(author=subject)
    ids = list(checkins.values_list("id", flat=True))
    checkins.update(wins=REDACTED, blockers=REDACTED, learning=REDACTED)
    CheckInPriority.objects.filter(check_in_id__in=ids).update(text=REDACTED)
    # The manager's reply is written about this person, so its text goes; the
    # manager remains the responder.
    ManagerResponse.objects.filter(check_in_id__in=ids).update(comment=REDACTED)
    return len(ids)


def _redact_recognition(subject) -> int:
    from apps.recognition.models import Recognition

    received = Recognition.objects.filter(recipient=subject)
    count = received.count()
    received.update(message=REDACTED)
    return count


def _redact_career_and_succession(subject) -> None:
    from apps.career.models import DevelopmentRoadmap
    from apps.succession.models import BenchCandidate, CriticalRole, NineBoxPlacement

    DevelopmentRoadmap.objects.filter(employee=subject).update(tiers=[], skill_gap={})
    BenchCandidate.objects.filter(candidate=subject).update(notes=REDACTED)
    NineBoxPlacement.objects.filter(employee=subject).update(override_rationale=REDACTED)
    # Only where they are the incumbent: a risk note is written about whoever
    # currently holds the role.
    CriticalRole.objects.filter(incumbent=subject).update(risk_notes=REDACTED)


def _scrub_stored_identity_snapshots(subject, pseudonym: str) -> int:
    """Succession plans freeze a copy of the person's identity into JSON.

    ``succession/engine.py`` writes ``ranked_bench`` entries carrying
    ``candidate_email`` and ``candidate_name`` — a snapshot taken at generation
    time. Tombstoning the user row does NOT reach it: the row is denormalised
    text, not a foreign key, so the name and email survive the erasure while
    every screen that renders a live FK correctly shows the pseudonym. It is the
    one place in the schema where that is true, which is exactly why it would be
    missed.

    The entries themselves stay — removing a candidate would change the plan's
    coverage assessment retroactively — but the identity in them is replaced.

    Iterates the tenant's plans in Python rather than trying to filter on JSON
    contents in MySQL: erasure is a rare admin operation and an SME tenant has
    tens of plans, so a query that is obviously correct beats one that is clever.
    """
    from apps.succession.models import SuccessionPlan

    subject_id = str(subject.id)
    needles = {subject_id}
    for value in (subject.email, subject.display_name):
        if value:
            needles.add(value)

    def scrub(node):
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key in ("candidate_email", "candidate_name") and node.get(
                    "candidate_id"
                ) == subject_id:
                    out[key] = pseudonym
                else:
                    out[key] = scrub(value)
            return out
        if isinstance(node, list):
            return [scrub(item) for item in node]
        if isinstance(node, str) and node != subject_id and node in needles:
            return pseudonym
        return node

    touched = 0
    for plan in SuccessionPlan.objects.all():
        bench = scrub(plan.ranked_bench)
        flags = scrub(plan.red_flags)
        actions = scrub(plan.action_items)
        if (bench, flags, actions) != (plan.ranked_bench, plan.red_flags, plan.action_items):
            plan.ranked_bench, plan.red_flags, plan.action_items = bench, flags, actions
            plan.save(update_fields=["ranked_bench", "red_flags", "action_items", "updated_at"])
            touched += 1
    return touched


def _clear_ai_traces(subject) -> None:
    """AI job parameters and chat sessions.

    ``AIJob.params`` is the prompt payload and can quote review text verbatim, so
    it is emptied rather than kept. Chat sessions are the person's own
    conversations — no one else's history depends on them — and go entirely,
    taking their turns and plans by cascade.
    """
    from apps.ai.models import AIJob, ChatSession

    AIJob.objects.filter(requested_by=subject).update(params={})
    # hard_delete, NOT delete: on a TenantScopedQuerySet `.delete()` is a SOFT
    # delete that stamps deleted_at and leaves every row (and its text) in the
    # table. For an erasure that is a silent failure — the endpoint reports
    # success and the data is still there. It also matters for the cascade: a
    # soft delete is an UPDATE, so it would never reach the turns and plans,
    # which is where the conversation text actually lives.
    ChatSession.objects.filter(owner=subject).hard_delete()


def _end_sessions(subject):
    """Revoke every session, and strip what those rows hold about them.

    The rows are REVOKED AND KEPT, not deleted, and that is the whole point:
    ``session_is_revoked()`` looks the device id up and reads a MISSING row as
    "not revoked" — an additive rollout, so a token whose session row is absent
    is deliberately not rejected. Deleting the sessions here would therefore hand
    the erased account a working access token until it expired on its own, which
    is the exact opposite of the intent. Stripped of ip and user agent they hold
    nothing about the person, and D3's retention purge removes them on the normal
    clock.

    Login history goes: it is a movement log — IP, user agent, the address they
    typed — and no one else's record depends on it.
    """
    from django.utils import timezone

    from apps.identity.models import DeviceSession, LoginEvent

    revoked = DeviceSession.objects.filter(user=subject, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    DeviceSession.objects.filter(user=subject).update(ip=None, user_agent="")
    # hard_delete for the same reason as the chat sessions: `.delete()` here is a
    # soft delete, which would leave every IP, user agent and typed email address
    # sitting in the table while reporting that the erasure succeeded.
    deleted, _ = LoginEvent.objects.filter(user=subject).hard_delete()
    return revoked, deleted


def _tombstone(subject) -> str | None:
    """Anonymise the user row in place. It survives as the pseudonymous id."""
    from django.utils import timezone

    old_photo = subject.photo.name or None

    subject.email = _tombstone_email()
    subject.display_name = f"Former employee {str(subject.id)[:4]}"
    subject.phone = ""
    subject.title = ""
    subject.department = ""
    subject.employee_id = ""
    subject.preferences = {}
    subject.photo = None
    subject.manager = None
    subject.is_active = False
    subject.set_unusable_password()
    subject.erased_at = timezone.now()
    # tenant, pk and role stay. The row must remain inside tenant isolation — a
    # tombstone outside a tenant would be visible to every tenant through the
    # unscoped manager — and serializers read `.role` off authors across the
    # codebase.
    subject.save(update_fields=[
        "email", "display_name", "phone", "title", "department", "employee_id",
        "preferences", "photo", "manager", "is_active", "password", "erased_at",
        "updated_at",
    ])

    # allauth keeps its own copy of the address, which no amount of tombstoning
    # the User row would reach.
    from allauth.account.models import EmailAddress

    EmailAddress.objects.filter(user=subject).delete()
    return old_photo


def _delete_photo_file(name: str) -> None:
    """Best-effort removal of the avatar from storage.

    Runs AFTER the transaction commits, never inside it: object storage is not
    transactional, so a rolled-back erasure must not have already deleted a file
    it should have kept. The opposite failure — a committed erasure whose file
    delete fails — leaves an avatar reachable only by an unguessable path with no
    user row pointing at it. That is logged rather than raised: the erasure has
    already happened, and raising here would report a completed operation as
    failed and invite a retry that cannot help.
    """
    import logging

    from django.core.files.storage import default_storage

    try:
        if name and default_storage.exists(name):
            default_storage.delete(name)
    except Exception:  # noqa: BLE001 — never fail a committed erasure
        logging.getLogger(__name__).exception(
            "erasure: could not delete avatar %s; it is now orphaned", name
        )


# ── the operation ─────────────────────────────────────────────────────────────


def erase_user(actor, subject, *, justification: str) -> dict:
    """Erase one person, irreversibly. Returns a summary of what was touched.

    Idempotent. A second call is a retry — the first may well have succeeded and
    then timed out on the caller's side — so it reports the existing erasure
    instead of erroring. A 409 here would invite the caller to "fix" it by
    reaching for something more destructive.

    Everything runs in ONE transaction. A half-erased person (profile anonymised,
    review bodies still readable) is worse than either outcome, and it is exactly
    what a timeout produces without this.
    """
    from django.db import transaction

    from apps.audit.services import audit_action

    if subject.erased_at is not None:
        return {
            "already_erased": True,
            "subject_id": str(subject.id),
            "erased_at": _iso(subject.erased_at),
            "pseudonym": subject.display_name,
        }
    if subject.id == actor.id:
        raise CannotErase(
            "You cannot erase your own account. Erasure is irreversible and revokes "
            "every session it touches, so it takes a second person."
        )

    summary: dict = {"already_erased": False, "subject_id": str(subject.id)}
    old_photo = None
    with transaction.atomic():
        # Audited BEFORE the effect, so the evidence of intent survives even if
        # the erasure then fails. The row names the subject and carries the
        # justification, and is never edited or deleted afterwards.
        with audit_action(
            action="privacy.user_erased",
            actor=actor,
            target_type="user",
            target_id=subject.id,
            justification=justification,
            metadata={"subject_email": subject.email},
            tenant=subject.tenant_id,
        ):
            summary["reviews_redacted"] = _redact_reviews(subject)
            summary["feedback_redacted"] = _redact_feedback(subject)
            summary["goals_redacted"] = _redact_goals(subject)
            summary["check_ins_redacted"] = _redact_checkins(subject)
            summary["recognition_redacted"] = _redact_recognition(subject)
            _redact_career_and_succession(subject)
            # Before the tombstone: the scrub needs the person's real email and
            # display name to find them in the frozen JSON.
            summary["succession_plans_scrubbed"] = _scrub_stored_identity_snapshots(
                subject, f"Former employee {str(subject.id)[:4]}"
            )
            _clear_ai_traces(subject)
            revoked, login_events = _end_sessions(subject)
            summary["sessions_revoked"] = revoked
            summary["login_events_deleted"] = login_events
            old_photo = _tombstone(subject)
            summary["pseudonym"] = subject.display_name
            summary["erased_at"] = _iso(subject.erased_at)

        if old_photo:
            transaction.on_commit(lambda: _delete_photo_file(old_photo))

    return summary
