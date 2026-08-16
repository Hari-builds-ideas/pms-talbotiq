"""
Data subject rights — export (D1) and erasure (D2).

Design and the reasoning behind every decision here: ``docs/BUILD/DATA_RIGHTS_DESIGN.md``.

Two things about this module are load-bearing.

**It reads through the tenant-scoped managers.** Every queryset below goes through
``Model.objects``, which ``TenantScopedManager`` filters by the bound tenant and
which fails closed (``qs.none()``) when no tenant is bound. An export that reached
across tenants would be the worst possible bug in this file, so it is not guarded
by a check that could be forgotten — it is the manager everyone already uses.

**It never egresses a feedback giver.** ``apps/feedback`` guarantees module-wide
that the giver identity leaves the API only to the giver themselves. An export is
a NEW egress boundary, which is exactly where a guarantee like that gets broken by
accident, so ``feedback_received`` is assembled field by field from a fixed list
and there is a test that scans the whole serialised export for every giver's id
and email.
"""
from __future__ import annotations

from apps.feedback.constants import ANONYMITY_GATED_GROUPS, MIN_FEEDBACK_VOLUME
from apps.feedback.models import Feedback, FeedbackCycle, OneOnOneNote

#: Marker for a relationship label withheld because its group is too small to be
#: anonymous. See ``_feedback_received``.
WITHHELD_SMALL_GROUP = "withheld_small_group"


def _iso(value):
    return value.isoformat() if value is not None else None


def _id(value):
    return str(value) if value is not None else None


def _person(user):
    """A person reference inside an export: id + display, never the raw row.

    ``display`` already falls back to the email when no display name is set, which
    is what every other surface in the product shows, so an export reads the same
    way as the screens it was taken from.
    """
    if user is None:
        return None
    return {"id": str(user.id), "display": user.display}


# ── profile ───────────────────────────────────────────────────────────────────


def _profile(user):
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
        "phone": user.phone,
        "title": user.title,
        "department": user.department,
        "employee_id": user.employee_id,
        "timezone": user.timezone,
        "language": user.language,
        # The file itself is not embedded — an avatar can be megabytes and the
        # export is meant to be readable. The path is what is HELD about them.
        "photo": user.photo.name or None,
        "preferences": user.preferences,
        "manager": _person(user.manager),
        "created_at": _iso(user.created_at),
        "erased_at": _iso(getattr(user, "erased_at", None)),
    }


def _reporting_line(user):
    """Who they report to and who reports to them.

    Direct reports only, deliberately: the full subtree is other people's
    reporting structure, not this person's data.
    """
    from apps.identity.models import User

    reports = User.objects.filter(manager=user).order_by("email")
    return {
        "manager": _person(user.manager),
        "direct_reports": [_person(u) for u in reports],
    }


# ── goals, KPIs, scores ───────────────────────────────────────────────────────


def _goals(user):
    from apps.goals.models import Goal, GoalUpdate, Kpi, KpiMeasurement

    goals = list(Goal.objects.filter(employee=user).select_related("cycle").order_by("created_at"))
    kpis = list(Kpi.objects.filter(goal__in=goals).order_by("created_at"))
    measurements = list(
        KpiMeasurement.objects.filter(kpi__in=kpis).order_by("recorded_at")
    )
    updates = list(
        GoalUpdate.objects.filter(goal__in=goals).select_related("author").order_by("created_at")
    )

    by_goal_kpis = {}
    for kpi in kpis:
        by_goal_kpis.setdefault(kpi.goal_id, []).append(kpi)
    by_kpi_measurements = {}
    for m in measurements:
        by_kpi_measurements.setdefault(m.kpi_id, []).append(m)
    by_goal_updates = {}
    for u in updates:
        by_goal_updates.setdefault(u.goal_id, []).append(u)

    return [
        {
            "id": str(goal.id),
            "title": goal.title,
            "description": goal.description,
            "objective": goal.objective,
            "weight": str(goal.weight),
            "status": goal.status,
            "cycle": goal.cycle.name if goal.cycle_id else None,
            "created_at": _iso(goal.created_at),
            "approved_at": _iso(goal.approved_at),
            "kpis": [
                {
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description,
                    "weight": str(kpi.weight),
                    "target_value": str(kpi.target_value),
                    "direction": kpi.direction,
                    "unit": kpi.unit,
                    "source": kpi.source,
                    "measurements": [
                        {
                            "value": str(m.value),
                            "recorded_at": _iso(m.recorded_at),
                            "source": m.source,
                        }
                        for m in by_kpi_measurements.get(kpi.id, [])
                    ],
                }
                for kpi in by_goal_kpis.get(goal.id, [])
            ],
            "updates": [
                {
                    "text": u.text,
                    "author": _person(u.author),
                    "created_at": _iso(u.created_at),
                }
                for u in by_goal_updates.get(goal.id, [])
            ],
        }
        for goal in goals
    ]


def _cycle_scores(user):
    from apps.goals.models import CycleScore

    rows = CycleScore.objects.filter(employee=user).select_related("cycle").order_by("computed_at")
    return [
        {
            "cycle": row.cycle.name if row.cycle_id else None,
            "raw_score": str(row.raw_score) if row.raw_score is not None else None,
            "z_score": str(row.z_score) if row.z_score is not None else None,
            "t_score": str(row.t_score) if row.t_score is not None else None,
            "cohort_size": row.cohort_size,
            "insufficient_cohort": row.insufficient_cohort,
            "risk_status": row.risk_status,
            "pace_behind": row.pace_behind,
            "computed_at": _iso(row.computed_at),
        }
        for row in rows
    ]


# ── reviews ───────────────────────────────────────────────────────────────────


def _reviews(user):
    from apps.reviews.models import Review, ReviewAssessment, ReviewComment

    reviews = list(
        Review.objects.filter(employee=user)
        .select_related("cycle", "reviewer", "human_reviewer")
        .order_by("created_at")
    )
    assessments = list(
        ReviewAssessment.objects.filter(review__in=reviews)
        .select_related("assessor")
        .order_by("created_at")
    )
    comments = list(
        ReviewComment.objects.filter(review__in=reviews)
        .select_related("author")
        .order_by("created_at")
    )

    by_review_assessments = {}
    for a in assessments:
        by_review_assessments.setdefault(a.review_id, []).append(a)
    by_review_comments = {}
    for c in comments:
        by_review_comments.setdefault(c.review_id, []).append(c)

    return [
        {
            "id": str(review.id),
            "cycle": review.cycle.name if review.cycle_id else None,
            "state": review.state,
            "reviewer": _person(review.reviewer),
            "human_reviewer": _person(review.human_reviewer),
            "draft_body": review.draft_body,
            "final_body": review.final_body,
            "rejected_reason": review.rejected_reason,
            # AI-drafted vs human-written, and how confident the model was: part of
            # the record of how a rating about this person was arrived at.
            "source": review.source,
            "confidence_score": (
                str(review.confidence_score) if review.confidence_score is not None else None
            ),
            "created_at": _iso(review.created_at),
            "approved_at": _iso(review.approved_at),
            "finalized_at": _iso(review.finalized_at),
            "assessments": [
                {
                    "assessment_type": a.assessment_type,
                    "assessor": _person(a.assessor),
                    "body": a.body,
                    "submitted_at": _iso(a.submitted_at),
                }
                for a in by_review_assessments.get(review.id, [])
            ],
            "comments": [
                {
                    "author": _person(c.author),
                    "section": c.section,
                    "body": c.body,
                    "created_at": _iso(c.created_at),
                    "edited_at": _iso(c.edited_at),
                }
                for c in by_review_comments.get(review.id, [])
            ],
        }
        for review in reviews
    ]


# ── feedback ──────────────────────────────────────────────────────────────────


def _small_groups(user):
    """Relationship groups whose response count is below the anonymity threshold.

    Computed per 360 cycle, matching ``apps.feedback.anonymize``: the threshold is
    per cycle and per group, and a cycle may raise it (``min_volume``).
    """
    small = set()
    cycles = FeedbackCycle.objects.filter(subject=user)
    for cycle in cycles:
        threshold = cycle.effective_min_volume
        counts = {}
        for item in Feedback.objects.filter(cycle=cycle, kind=Feedback.Kind.THREE_SIXTY):
            counts[item.relationship] = counts.get(item.relationship, 0) + 1
        for group in ANONYMITY_GATED_GROUPS:
            if 0 < counts.get(group, 0) < threshold:
                small.add((cycle.id, group))
    return small


def _feedback_received(user):
    """Feedback ABOUT this person — bodies included, giver NEVER included.

    ``apps/feedback`` guarantees the giver identity leaves the API only to the
    giver themselves. This function therefore lists its fields explicitly rather
    than serialising the row: a future field added to ``Feedback`` cannot leak
    through it, and ``giver`` is not among them.

    The ``relationship`` label is withheld for a PEER/UPWARD group below the
    minimum volume. Removing the giver id is not enough there — "the one peer
    comment on your 360" identifies its author to anyone who knows who was
    invited. The body is still exported: it is data about the subject, and
    withholding it would defeat the request.
    """
    small = _small_groups(user)
    rows = Feedback.objects.filter(subject=user).order_by("created_at")
    out = []
    for item in rows:
        gated = (item.cycle_id, item.relationship) in small
        out.append({
            "id": str(item.id),
            "kind": item.kind,
            "relationship": WITHHELD_SMALL_GROUP if gated else item.relationship,
            "body": item.body,
            "sentiment": item.sentiment,
            "created_at": _iso(item.created_at),
        })
    return out


def _feedback_given(user):
    """Feedback this person WROTE. Theirs, and it names who it was about.

    That disclosure is unavoidable in a 360 system and is the reason this endpoint
    is Admin-only rather than something an employee can pull for themselves.
    """
    rows = (
        Feedback.objects.filter(giver=user).select_related("subject").order_by("created_at")
    )
    return [
        {
            "id": str(item.id),
            "subject": _person(item.subject),
            "kind": item.kind,
            "relationship": item.relationship,
            "body": item.body,
            "created_at": _iso(item.created_at),
        }
        for item in rows
    ]


def _one_on_ones(user):
    from django.db.models import Q

    rows = (
        OneOnOneNote.objects.filter(Q(employee=user) | Q(manager=user))
        .select_related("manager", "employee")
        .order_by("meeting_date")
    )
    return [
        {
            "id": str(note.id),
            "manager": _person(note.manager),
            "employee": _person(note.employee),
            "body": note.body,
            "meeting_date": _iso(note.meeting_date),
        }
        for note in rows
    ]


# ── check-ins, recognition ────────────────────────────────────────────────────


def _check_ins(user):
    from apps.checkins.models import CheckIn, CheckInPriority, ManagerResponse

    rows = list(CheckIn.objects.filter(author=user).order_by("week_of"))
    priorities = {}
    for p in CheckInPriority.objects.filter(check_in__in=rows).order_by("order"):
        priorities.setdefault(p.check_in_id, []).append(p)
    responses = {
        r.check_in_id: r
        for r in ManagerResponse.objects.filter(check_in__in=rows).select_related("responder")
    }
    out = []
    for row in rows:
        response = responses.get(row.id)
        out.append({
            "id": str(row.id),
            "week_of": _iso(row.week_of),
            "mood": row.mood,
            "wins": row.wins,
            "blockers": row.blockers,
            "learning": row.learning,
            "priorities": [
                {"text": p.text, "status": p.status} for p in priorities.get(row.id, [])
            ],
            "manager_response": None if response is None else {
                "responder": _person(response.responder),
                "comment": response.comment,
                "reaction": response.reaction,
                "follow_up": response.follow_up,
                "created_at": _iso(response.created_at),
            },
        })
    return out


def _recognition(user):
    from apps.recognition.models import Recognition

    def serialize(row, other_key, other):
        return {
            "id": str(row.id),
            other_key: _person(other),
            "value": row.value,
            "message": row.message,
            "badge": row.badge,
            "visibility": row.visibility,
            "created_at": _iso(row.created_at),
        }

    sent = Recognition.objects.filter(sender=user).select_related("recipient").order_by("created_at")
    received = (
        Recognition.objects.filter(recipient=user).select_related("sender").order_by("created_at")
    )
    return (
        [serialize(r, "recipient", r.recipient) for r in sent],
        [serialize(r, "sender", r.sender) for r in received],
    )


# ── career, succession ────────────────────────────────────────────────────────


def _career(user):
    from apps.career.models import DevelopmentRoadmap, RoadmapProgress, TargetRoleSelection

    roadmaps = list(
        DevelopmentRoadmap.objects.filter(employee=user)
        .select_related("target_jd", "target_position")
        .order_by("created_at")
    )
    progress = {}
    for p in RoadmapProgress.objects.filter(roadmap__in=roadmaps).order_by("tier_index"):
        progress.setdefault(p.roadmap_id, []).append(p)
    selections = (
        TargetRoleSelection.objects.filter(employee=user)
        .select_related("target_jd", "target_position")
        .order_by("selected_at")
    )
    return {
        "roadmaps": [
            {
                "id": str(r.id),
                "status": r.status,
                "target_jd": r.target_jd.title if r.target_jd_id else None,
                "target_position": r.target_position.title if r.target_position_id else None,
                "tiers": r.tiers,
                "skill_gap": r.skill_gap,
                "source": r.source,
                "advisory": r.advisory,
                "generated_at": _iso(r.generated_at),
                "progress": [
                    {"tier_index": p.tier_index, "status": p.status}
                    for p in progress.get(r.id, [])
                ],
            }
            for r in roadmaps
        ],
        "target_role_selections": [
            {
                "target_jd": s.target_jd.title if s.target_jd_id else None,
                "target_position": s.target_position.title if s.target_position_id else None,
                "selected_at": _iso(s.selected_at),
            }
            for s in selections
        ],
    }


def _succession(user):
    """Nine-box placements and bench candidacies.

    This is the most sensitive category in the product: a person is usually not
    told they are on a bench list, or which box they were placed in. It is held
    about them, so it is exported — and the endpoint being Admin-only is what
    keeps that from being a disclosure the employee makes to themselves.
    """
    from apps.succession.models import BenchCandidate, NineBoxPlacement

    placements = (
        NineBoxPlacement.objects.filter(employee=user)
        .select_related("cycle")
        .order_by("assessed_at")
    )
    bench = (
        BenchCandidate.objects.filter(candidate=user)
        .select_related("critical_role")
        .order_by("created_at")
    )
    return {
        "nine_box_placements": [
            {
                "cycle": p.cycle.name if p.cycle_id else None,
                "performance_band": p.performance_band,
                "potential_band": p.potential_band,
                "box": p.box,
                "override_box": p.override_box,
                "override_rationale": p.override_rationale,
                "assessed_at": _iso(p.assessed_at),
            }
            for p in placements
        ],
        "bench_candidacies": [
            {
                "critical_role": b.critical_role.name if b.critical_role_id else None,
                "readiness": b.readiness,
                "readiness_overridden": b.readiness_overridden,
                "notes": b.notes,
                "created_at": _iso(b.created_at),
            }
            for b in bench
        ],
    }


# ── account activity ──────────────────────────────────────────────────────────


def _login_history(user):
    from apps.identity.models import DeviceSession, LoginEvent

    events = LoginEvent.objects.filter(user=user).order_by("created_at")
    sessions = DeviceSession.objects.filter(user=user).order_by("created_at")
    return (
        [
            {
                "event": e.event,
                "ip": e.ip,
                "user_agent": e.user_agent,
                "created_at": _iso(e.created_at),
            }
            for e in events
        ],
        [
            {
                "ip": s.ip,
                "user_agent": s.user_agent,
                "last_seen": _iso(s.last_seen),
                "revoked_at": _iso(s.revoked_at),
                "created_at": _iso(s.created_at),
            }
            for s in sessions
        ],
    )


def _ai_jobs(user):
    from apps.ai.models import AIJob

    rows = AIJob.objects.filter(requested_by=user).order_by("created_at")
    return [
        {
            "agent_code": j.agent_code,
            "target_type": j.target_type,
            "target_id": j.target_id,
            "status": j.status,
            "error_code": j.error_code,
            "created_at": _iso(j.created_at),
            "finished_at": _iso(j.finished_at),
        }
        for j in rows
    ]


def _approvals(user):
    from apps.approvals.models import ApprovalStepInstance

    rows = (
        ApprovalStepInstance.objects.filter(approver=user)
        .select_related("route")
        .order_by("created_at")
    )
    return [
        {
            "artifact_type": s.route.artifact_type if s.route_id else None,
            "status": s.status,
            "comment": s.comment,
            "decided_at": _iso(s.decided_at),
            "escalated": s.escalated,
        }
        for s in rows
    ]


# ── the export ────────────────────────────────────────────────────────────────


def export_user(subject) -> dict:
    """Everything held about one employee, as one JSON-serialisable dict.

    Not paginated and not streamed. One employee's full history is a few hundred
    KB even after years, and a partial export that looks complete is a worse
    outcome than a slow one.

    The caller is responsible for the capability gate and for auditing the access
    (see ``views.UserExportView``) — this function is a pure read.
    """
    sent, received = _recognition(subject)
    login_events, device_sessions = _login_history(subject)
    return {
        "schema": "pms.data-export.v1",
        "subject_id": str(subject.id),
        "profile": _profile(subject),
        "reporting_line": _reporting_line(subject),
        "goals": _goals(subject),
        "cycle_scores": _cycle_scores(subject),
        "reviews": _reviews(subject),
        "feedback_received": _feedback_received(subject),
        "feedback_given": _feedback_given(subject),
        "one_on_one_notes": _one_on_ones(subject),
        "check_ins": _check_ins(subject),
        "recognition_sent": sent,
        "recognition_received": received,
        "career": _career(subject),
        "succession": _succession(subject),
        "login_history": login_events,
        "device_sessions": device_sessions,
        "ai_jobs": _ai_jobs(subject),
        "approvals_acted_on": _approvals(subject),
        "notes": {
            "feedback_received": (
                "Giver identities are never included: feedback is given under a "
                "module-wide anonymity guarantee. A relationship label of "
                f"'{WITHHELD_SMALL_GROUP}' means that group had fewer than "
                f"{MIN_FEEDBACK_VOLUME} responses, so naming it would identify "
                "the giver."
            ),
            "audit_log": (
                "Actions this person took are recorded in the audit log, which is "
                "append-only and is not included here. Query it through the audit "
                "console."
            ),
        },
    }
