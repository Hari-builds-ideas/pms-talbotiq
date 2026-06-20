"""
Feedback API — the HTTP surface of the Module-4 360°/anonymisation flow.

Views stay THIN on purpose:
  * every consequential write goes through ``services.py`` (open/close/invite/
    decline/give/edit/approve), which audits BEFORE the effect, binds the
    tenant, and raises the right 409/403/400s itself;
  * rows load through the TENANT-SCOPED managers, so a cross-tenant id simply
    404s — we never filter by tenant by hand;
  * THE HEADLINE RULE — giver identity never egresses — is enforced at the
    SERIALIZER layer (see ``serializers.py``): the only Feedback-row serializer
    has no ``giver`` field and only ever renders the caller's own rows, and a
    recipient's 360 view is ``build_anonymized_payload`` verbatim, never model
    rows.

1:1 notes are PRIVATE TO THEIR TWO PARTICIPANTS: nobody else — not the
subject's other managers, not HRBP, not even Admin — can read them via the API.
They are mutual working context, not org data.
"""
from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.serializers import AIJobSerializer
from apps.ai.services import enqueue_agent_job
from apps.core.pagination import StandardResultsSetPagination
from apps.cycles.models import PerformanceCycle
from apps.identity.models import User
from apps.rbac.matrix import Capability, role_has_capability
from apps.rbac.mixins import RBACMixin
from apps.rbac.scope import Scope, actor_can_access, reporting_subtree_ids, scope_for_role

from .anonymize import build_anonymized_payload
from .exceptions import IllegalCycleTransition
from .models import Feedback, FeedbackCycle, FeedbackRequest, FeedbackSummary, OneOnOneNote
from .serializers import (
    ContinuousFeedbackSerializer,
    EditFeedbackSerializer,
    FeedbackCycleCreateSerializer,
    FeedbackCycleSerializer,
    FeedbackRequestCreateSerializer,
    FeedbackRequestSerializer,
    FeedbackSummarySerializer,
    GiveFeedbackSerializer,
    MyFeedbackCycleSerializer,
    OneOnOneNoteCreateSerializer,
    OneOnOneNoteEditSerializer,
    OneOnOneNoteSerializer,
    OwnFeedbackSerializer,
    ReceivedContinuousFeedbackSerializer,
)
from .services import (
    approve_summary,
    close_cycle,
    decline_request,
    edit_own_feedback,
    give_continuous_feedback,
    give_feedback_360,
    open_cycle,
    send_feedback_request,
)

_OUT_OF_SCOPE = "This record is outside your access scope."


# ── cycles ──────────────────────────────────────────────────────────────────


class FeedbackCycleListCreateView(RBACMixin, APIView):
    """``GET, POST /api/feedback/cycles`` — MANAGE_FEEDBACK_CYCLE (Manager+).

    GET: cycles whose SUBJECT falls in the caller's data scope (TEAM → the
    reporting subtree + self; TENANT → everything). POST: create a DRAFT cycle
    for a subject in scope. Creation is quiet by design — OPENING is the
    consequential, audited act (``open_cycle``).
    """

    required_capability = Capability.MANAGE_FEEDBACK_CYCLE

    def get(self, request):
        cycles = FeedbackCycle.objects.all()
        scope = scope_for_role(request.user.role)
        if scope is Scope.OWN:  # unreachable for Manager+, but fail closed
            cycles = cycles.filter(subject_id=request.user.id)
        elif scope is Scope.TEAM:
            visible = reporting_subtree_ids(request.user) | {request.user.id}
            cycles = cycles.filter(subject_id__in=visible)
        # Scope.TENANT → all in tenant (scoped manager already isolates).
        # subject_name derefs the subject FK — select_related to stay bounded.
        # (Givers are never resolved on this serializer; anonymity is unaffected.)
        cycles = cycles.select_related("subject")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(cycles, request, view=self)
        return paginator.get_paginated_response(
            FeedbackCycleSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = FeedbackCycleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Tenant-scoped lookups: cross-tenant ids 404, never 400.
        subject = get_object_or_404(User.objects.all(), pk=data["subject"])
        performance_cycle = None
        if data.get("performance_cycle"):
            performance_cycle = get_object_or_404(
                PerformanceCycle.objects.all(), pk=data["performance_cycle"]
            )
        # Scope-on-CREATE: no object yet, so check the target subject explicitly.
        if not actor_can_access(request.user, subject):
            raise PermissionDenied(_OUT_OF_SCOPE)
        cycle = FeedbackCycle.objects.create(
            tenant_id=request.user.tenant_id,
            subject=subject,
            opened_by=request.user,  # server-set, never client-supplied
            performance_cycle=performance_cycle,
            min_volume=data.get("min_volume"),
            status=FeedbackCycle.Status.DRAFT,
        )
        return Response(
            FeedbackCycleSerializer(cycle).data, status=status.HTTP_201_CREATED
        )


class _CycleActionView(RBACMixin, APIView):
    """Base for cycle sub-routes: capability + object scope on the cycle's
    subject, loaded through the scoped manager (cross-tenant → 404)."""

    required_capability = Capability.MANAGE_FEEDBACK_CYCLE
    scope_subject_attr = "employee"  # FeedbackCycle.employee == its subject

    def get_cycle(self, pk):
        cycle = get_object_or_404(FeedbackCycle.objects.all(), pk=pk)
        self.check_object_scope(cycle)
        return cycle


class CycleOpenView(_CycleActionView):
    """``POST /api/feedback/cycles/<pk>/open`` — DRAFT → COLLECTING (audited)."""

    def post(self, request, pk):
        cycle = open_cycle(self.get_cycle(pk), request.user)
        return Response(FeedbackCycleSerializer(cycle).data)


class CycleCloseView(_CycleActionView):
    """``POST /api/feedback/cycles/<pk>/close`` — COLLECTING → CLOSED (sync,
    audited), then ENQUEUES the summarize pipeline (anonymise → threshold →
    breach guard → Agent-3 seam) to run async. 200 with the enqueued AI job
    embedded under ``job``: the CLOSE succeeded; the summary is produced off the
    request thread and polled via ``GET /api/ai/jobs/<id>``."""

    def post(self, request, pk):
        cycle, job = close_cycle(self.get_cycle(pk), request.user)
        return Response(
            {"cycle": FeedbackCycleSerializer(cycle).data, "job": AIJobSerializer(job).data}
        )


class CycleSummarizeView(_CycleActionView):
    """``POST /api/feedback/cycles/<pk>/summarize`` — (re-)run the summarize
    pipeline on a CLOSED cycle (409 otherwise). ENQUEUES Agent 3 and returns
    ``202`` + an AI job id; the client polls ``GET /api/ai/jobs/<id>``.

    Async by design (BUILD_2). The anonymised payload, the deterministic breach
    guard, the HRBP_HOLD and the PENDING_HUMAN_REVIEW gate all still run — in the
    worker. Outcome maps onto the job: no provider → DEGRADED (NOT_CONFIGURED), a
    breach/sensitive → DEGRADED (ANONYMITY_HOLD, the summary held), clean →
    SUCCEEDED (summary PENDING). The CLOSED precondition stays a synchronous 409.
    """

    def post(self, request, pk):
        cycle = self.get_cycle(pk)
        if cycle.status != FeedbackCycle.Status.CLOSED:
            raise IllegalCycleTransition(cycle.status, "summarize")
        job = enqueue_agent_job(
            actor=request.user,
            agent_code="agent3",
            target_type="feedback_cycle",
            target_id=cycle.id,
        )
        return Response(AIJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class CycleRequestListCreateView(_CycleActionView):
    """``GET, POST /api/feedback/cycles/<pk>/requests`` — the inviter's surface
    (MANAGE_FEEDBACK_CYCLE + object scope).

    The giver IS visible here: the inviter created these invitations. This
    never leaks who SUBMITTED what — invitation rows are never joined to
    feedback content anywhere in the API.
    """

    def get(self, request, pk):
        cycle = self.get_cycle(pk)
        return Response(
            FeedbackRequestSerializer(cycle.requests.all(), many=True).data
        )

    def post(self, request, pk):
        cycle = self.get_cycle(pk)
        serializer = FeedbackRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        giver = get_object_or_404(
            User.objects.all(), pk=serializer.validated_data["giver"]
        )
        invitation = send_feedback_request(
            cycle=cycle,
            giver=giver,
            relationship=serializer.validated_data["relationship"],
            actor=request.user,
        )
        return Response(
            FeedbackRequestSerializer(invitation).data, status=status.HTTP_201_CREATED
        )


# ── the giver's surface ─────────────────────────────────────────────────────


class MyRequestsView(RBACMixin, APIView):
    """``GET /api/feedback/requests/mine`` — the caller's own invitations, any
    state. The giver field is the caller themselves."""

    required_capability = Capability.GIVE_FEEDBACK

    def get(self, request):
        invitations = FeedbackRequest.objects.filter(giver_id=request.user.id)
        return Response(FeedbackRequestSerializer(invitations, many=True).data)


class RequestDeclineView(RBACMixin, APIView):
    """``POST /api/feedback/requests/<pk>/decline`` — the invited giver
    declines (the service enforces giver-only + PENDING-only)."""

    required_capability = Capability.GIVE_FEEDBACK

    def post(self, request, pk):
        invitation = get_object_or_404(FeedbackRequest.objects.all(), pk=pk)
        invitation = decline_request(invitation, request.user)
        return Response(FeedbackRequestSerializer(invitation).data)


class GiveFeedbackView(RBACMixin, APIView):
    """``POST /api/feedback/cycles/<pk>/give`` — submit 360 feedback.

    NO object-scope gate on purpose: the PENDING invitation IS the
    authorisation (the service 403s INVITATION_REQUIRED without one, and 409s
    outside COLLECTING). The giver is ALWAYS request.user — a client-supplied
    ``giver`` is ignored (anti-spoof), and the relationship comes from the
    invitation, never the request.
    """

    required_capability = Capability.GIVE_FEEDBACK

    def post(self, request, pk):
        cycle = get_object_or_404(FeedbackCycle.objects.all(), pk=pk)
        serializer = GiveFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = give_feedback_360(
            cycle=cycle,
            giver=request.user,  # server-set, ALWAYS
            body=serializer.validated_data["body"],
            marked_sensitive=serializer.validated_data["marked_sensitive"],
        )
        return Response(OwnFeedbackSerializer(item).data, status=status.HTTP_201_CREATED)


class ContinuousFeedbackView(RBACMixin, APIView):
    """``POST /api/feedback/continuous`` — any-time, cycle-less feedback about
    a colleague (the service rejects self-feedback). Giver is request.user."""

    required_capability = Capability.GIVE_FEEDBACK

    def post(self, request):
        serializer = ContinuousFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = get_object_or_404(
            User.objects.all(), pk=serializer.validated_data["subject"]
        )
        item = give_continuous_feedback(
            subject=subject,
            giver=request.user,
            body=serializer.validated_data["body"],
            marked_sensitive=serializer.validated_data["marked_sensitive"],
        )
        return Response(OwnFeedbackSerializer(item).data, status=status.HTTP_201_CREATED)


class MyFeedbackView(RBACMixin, APIView):
    """``GET /api/feedback/mine`` — everything the caller HAS GIVEN (both
    kinds), attributed to them because it IS them."""

    required_capability = Capability.GIVE_FEEDBACK

    def get(self, request):
        items = Feedback.objects.filter(giver_id=request.user.id)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        return paginator.get_paginated_response(
            OwnFeedbackSerializer(page, many=True).data
        )


class FeedbackItemEditView(RBACMixin, APIView):
    """``PATCH /api/feedback/items/<pk>`` — a giver edits their OWN item (the
    service enforces giver-only and immutability once the cycle is CLOSED)."""

    required_capability = Capability.GIVE_FEEDBACK

    def patch(self, request, pk):
        item = get_object_or_404(Feedback.objects.all(), pk=pk)
        serializer = EditFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = edit_own_feedback(
            item,
            request.user,
            body=serializer.validated_data.get("body"),
            marked_sensitive=serializer.validated_data.get("marked_sensitive"),
        )
        return Response(OwnFeedbackSerializer(item).data)


class ReceivedFeedbackView(RBACMixin, APIView):
    """``GET /api/feedback/received`` — CONTINUOUS feedback ABOUT the caller,
    words only, NEVER the author (giver-less serializer). The caller's 360
    content arrives exclusively via the anonymised cycle view."""

    required_capability = Capability.GIVE_FEEDBACK

    def get(self, request):
        items = Feedback.objects.filter(
            subject_id=request.user.id, kind=Feedback.Kind.CONTINUOUS
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        return paginator.get_paginated_response(
            ReceivedContinuousFeedbackSerializer(page, many=True).data
        )


# ── the recipient / reviewer surfaces ───────────────────────────────────────


class CycleAnonymizedView(RBACMixin, APIView):
    """``GET /api/feedback/cycles/<pk>/anonymized`` — THE 360 egress artifact:
    ``build_anonymized_payload`` verbatim (giver-stripped, pseudonymised,
    volume-gated). Never serialized Feedback rows.

    Allowed: (a) the cycle's subject; (b) MANAGE_FEEDBACK_CYCLE holders with
    the subject in their data scope (managers up the chain, HRBP/Admin
    tenant-wide). Anyone else — including an invited peer — gets 403. Only
    once the cycle is CLOSED (409 before: collection isn't finished, partial
    groups must never egress).
    """

    required_capability = Capability.VIEW_OWN_FEEDBACK_SUMMARY

    def get(self, request, pk):
        cycle = get_object_or_404(FeedbackCycle.objects.all(), pk=pk)
        if request.user.id != cycle.subject_id:
            if not (
                role_has_capability(request.user.role, Capability.MANAGE_FEEDBACK_CYCLE)
                and actor_can_access(request.user, cycle.subject)
            ):
                raise PermissionDenied(_OUT_OF_SCOPE)
        if cycle.status != FeedbackCycle.Status.CLOSED:
            raise IllegalCycleTransition(cycle.status, "read the anonymized payload of")
        return Response(build_anonymized_payload(cycle))


class MyCyclesView(RBACMixin, APIView):
    """``GET /api/feedback/my-cycles`` — the cycles whose SUBJECT is the caller.

    Subject-scoped DISCOVERY so an employee can find the 360 cycles that are
    about them (and the id of their released summary) WITHOUT the Manager+
    cycles list. Gated by ``VIEW_OWN_FEEDBACK_SUMMARY`` (held by everyone, OWN
    scope) — the same capability that already governs the subject's released
    summary read. The tenant-scoped manager isolates by tenant, and the
    ``subject_id == caller`` filter makes it own-only: a caller never sees
    another person's cycle here. No giver identities and no summary CONTENT
    egress — only the summary id + lifecycle status, exactly as
    ``CycleSummaryView`` already discloses to the subject."""

    required_capability = Capability.VIEW_OWN_FEEDBACK_SUMMARY

    def get(self, request):
        cycles = FeedbackCycle.objects.filter(
            subject_id=request.user.id
        ).prefetch_related("summaries")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(cycles, request, view=self)
        return paginator.get_paginated_response(
            MyFeedbackCycleSerializer(page, many=True).data
        )


class CycleSummaryView(RBACMixin, APIView):
    """``GET /api/feedback/cycles/<pk>/summary`` — the SUBJECT reads their own
    RELEASED summary. 403 for anyone else; 404 when no summary exists yet; 403
    SUMMARY_NOT_RELEASED while it awaits HRBP review (existence is fine to
    disclose to the subject — its content is not)."""

    required_capability = Capability.VIEW_OWN_FEEDBACK_SUMMARY

    def get(self, request, pk):
        cycle = get_object_or_404(FeedbackCycle.objects.all(), pk=pk)
        if request.user.id != cycle.subject_id:
            raise PermissionDenied(_OUT_OF_SCOPE)
        summary = cycle.summaries.first()  # unique per (tenant, cycle)
        if summary is None:
            return Response(
                {"detail": "No summary exists for this cycle yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if summary.status != FeedbackSummary.Status.RELEASED:
            raise PermissionDenied(
                {
                    "detail": "This summary has not been released yet.",
                    "code": "SUMMARY_NOT_RELEASED",
                }
            )
        return Response(FeedbackSummarySerializer(summary).data)


class SummaryReviewQueueView(RBACMixin, APIView):
    """``GET /api/feedback/summaries/review`` — the HRBP/Admin review queue:
    every summary awaiting a human (HRBP_HOLD + PENDING_HUMAN_REVIEW)."""

    required_capability = Capability.APPROVE_FEEDBACK_SUMMARY

    def get(self, request):
        queue = FeedbackSummary.objects.filter(
            status__in=[
                FeedbackSummary.Status.HRBP_HOLD,
                FeedbackSummary.Status.PENDING_HUMAN_REVIEW,
            ]
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queue, request, view=self)
        return paginator.get_paginated_response(
            FeedbackSummarySerializer(page, many=True).data
        )


class SummaryApproveView(RBACMixin, APIView):
    """``POST /api/feedback/summaries/<pk>/approve`` — HRBP/Admin clears a hold
    / approves: → RELEASED (audited; ``reviewed_by``/``released_at``
    server-set)."""

    required_capability = Capability.APPROVE_FEEDBACK_SUMMARY

    def post(self, request, pk):
        summary = get_object_or_404(FeedbackSummary.objects.all(), pk=pk)
        summary = approve_summary(summary, request.user)
        return Response(FeedbackSummarySerializer(summary).data)


# ── 1:1 notes — participants ONLY ───────────────────────────────────────────


class OneOnOneListCreateView(RBACMixin, APIView):
    """``GET, POST /api/feedback/one-on-ones`` — MANAGE_ONE_ON_ONE (everyone),
    participant-gated at the object level.

    GET: only notes where the caller is the manager OR the employee — NOBODY
    else sees a 1:1, not HRBP, not Admin. POST: ``{manager, employee, body,
    meeting_date}`` where request.user must BE one of the two (403 otherwise).
    """

    required_capability = Capability.MANAGE_ONE_ON_ONE

    def get(self, request):
        notes = OneOnOneNote.objects.filter(
            Q(manager_id=request.user.id) | Q(employee_id=request.user.id)
        )
        return Response(OneOnOneNoteSerializer(notes, many=True).data)

    def post(self, request):
        serializer = OneOnOneNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if request.user.id not in (data["manager"], data["employee"]):
            raise PermissionDenied("A 1:1 note can only be created by one of its participants.")
        manager = get_object_or_404(User.objects.all(), pk=data["manager"])
        employee = get_object_or_404(User.objects.all(), pk=data["employee"])
        note = OneOnOneNote.objects.create(
            tenant_id=request.user.tenant_id,
            manager=manager,
            employee=employee,
            body=data["body"],
            meeting_date=data["meeting_date"],
        )
        return Response(
            OneOnOneNoteSerializer(note).data, status=status.HTTP_201_CREATED
        )


class OneOnOneDetailView(RBACMixin, APIView):
    """``GET, PATCH /api/feedback/one-on-ones/<pk>`` — participants only
    (object-level ``is_participant`` check → 403 for everyone else, Admin
    included; cross-tenant ids 404 via the scoped manager)."""

    required_capability = Capability.MANAGE_ONE_ON_ONE

    def _get_note(self, request, pk):
        note = get_object_or_404(OneOnOneNote.objects.all(), pk=pk)
        if not note.is_participant(request.user):
            raise PermissionDenied("1:1 notes are private to their two participants.")
        return note

    def get(self, request, pk):
        return Response(OneOnOneNoteSerializer(self._get_note(request, pk)).data)

    def patch(self, request, pk):
        note = self._get_note(request, pk)
        serializer = OneOnOneNoteEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "body" in data:
            note.body = data["body"]
        if "meeting_date" in data:
            note.meeting_date = data["meeting_date"]
        note.save()
        return Response(OneOnOneNoteSerializer(note).data)
