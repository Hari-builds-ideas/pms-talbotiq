"""
Reviews API — the HTTP surface of the Module-3 HITL flow.

Views stay THIN on purpose:
  * creation goes through ``services.create_review`` (ACTIVE-cycle 409 + audit);
  * every state change goes through a ``state_machine`` function, which
    enforces legality (409), the HITL gate (422), AND RBAC capability + row
    scope internally (403) — the transition views only fast-fail the capability
    via ``RBACMixin`` for a cheap early 403, load the review through the
    tenant-scoped manager (cross-tenant id → 404), call the function and return
    the serialized review;
  * assessments go through ``services.submit_assessment`` (SELF upsert,
    duplicate rejection, server-set ``submitted_at``, audit).

The tenant is bound from the JWT by ``TenantMiddleware``; the scoped managers
auto-filter, so a cross-tenant row never resolves and we never filter by tenant
by hand. Visibility follows the role scopes: OWN → own review only, TEAM →
reporting subtree, TENANT → everything (HRBP/Admin).
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.cycles.models import PerformanceCycle
from apps.identity.models import User
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin
from apps.rbac.scope import (
    Scope,
    actor_can_access,
    reporting_subtree_ids,
    scope_for_role,
)

from . import state_machine
from .models import Review, ReviewAssessment
from .serializers import (
    AssessmentSerializer,
    CalibrationRowSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
    TransitionSerializer,
)
from .services import create_review, submit_assessment


class ReviewListCreateView(RBACMixin, APIView):
    """``GET, POST /api/reviews/``.

    GET (VIEW_OWN_REVIEW): reviews filtered by the caller's data scope, with
    optional ``?cycle=<id>`` and ``?state=<state>`` filters. POST
    (MANAGE_REVIEWS): create a DRAFT review for a subject in an ACTIVE cycle.
    """

    _caps = {"GET": Capability.VIEW_OWN_REVIEW, "POST": Capability.MANAGE_REVIEWS}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        reviews = Review.objects.all()
        scope = scope_for_role(request.user.role)
        if scope is Scope.OWN:
            reviews = reviews.filter(employee_id=request.user.id)
        elif scope is Scope.TEAM:
            visible = reporting_subtree_ids(request.user) | {request.user.id}
            reviews = reviews.filter(employee_id__in=visible)
        # Scope.TENANT → all in tenant (scoped manager already isolates).
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            reviews = reviews.filter(cycle_id=cycle_id)
        state = request.query_params.get("state")
        if state:
            reviews = reviews.filter(state=state)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(reviews, request, view=self)
        return paginator.get_paginated_response(ReviewSerializer(page, many=True).data)

    def post(self, request):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Tenant-scoped lookups: a cross-tenant employee/cycle id simply 404s.
        employee = get_object_or_404(
            User.objects.all(), pk=serializer.validated_data["employee"]
        )
        cycle = get_object_or_404(
            PerformanceCycle.objects.all(), pk=serializer.validated_data["cycle"]
        )
        # Scope-on-CREATE: no object yet, so check the target subject explicitly.
        if not actor_can_access(request.user, employee):
            raise PermissionDenied("This record is outside your access scope.")
        # create_review enforces the ACTIVE-cycle rule (409) and audits.
        review = create_review(
            employee=employee,
            cycle=cycle,
            actor=request.user,
            draft_body=serializer.validated_data.get("draft_body", ""),
        )
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class ReviewDetailView(RBACMixin, APIView):
    """``GET /api/reviews/<pk>`` — review detail (VIEW_OWN_REVIEW + object
    scope: OWN sees only their own review, TEAM the subtree, TENANT all).

    There is deliberately NO PATCH: the state machine is the only mutator
    (``draft_body`` is written via the submit transition).
    """

    required_capability = Capability.VIEW_OWN_REVIEW
    scope_subject_attr = "employee"

    def get(self, request, pk):
        review = get_object_or_404(Review.objects.all(), pk=pk)
        self.check_object_scope(review)
        return Response(ReviewSerializer(review).data)


class ReviewTimelineView(RBACMixin, APIView):
    """``GET /api/reviews/<pk>/timeline`` — the review's state-transition rows
    (the approval tracker). Same visibility as the review detail."""

    required_capability = Capability.VIEW_OWN_REVIEW
    scope_subject_attr = "employee"

    def get(self, request, pk):
        review = get_object_or_404(Review.objects.all(), pk=pk)
        self.check_object_scope(review)
        transitions = review.transitions.all()  # model Meta orders by `at`
        return Response(TransitionSerializer(transitions, many=True).data)


class _TransitionView(RBACMixin, APIView):
    """Base for the transition endpoints: load the review through the scoped
    manager (cross-tenant → 404), hand it to the state machine, return the
    serialized review.

    The view's ``required_capability`` is only a FAST-FAIL gate — the state
    machine re-checks capability AND row scope itself and raises 403/409/422,
    which DRF's exception handler maps to the response.
    """

    def post(self, request, pk):
        review = get_object_or_404(Review.objects.all(), pk=pk)
        review = self.transition(request, review)
        return Response(ReviewSerializer(review).data)

    def transition(self, request, review):  # pragma: no cover - abstract
        raise NotImplementedError


class ReviewStartEditView(_TransitionView):
    """``POST /api/reviews/<pk>/start-edit`` — DRAFT/PENDING/REJECTED → EDITING."""

    required_capability = Capability.MANAGE_REVIEWS

    def transition(self, request, review):
        return state_machine.start_edit(review, request.user)


class ReviewSubmitView(_TransitionView):
    """``POST /api/reviews/<pk>/submit`` (alias ``/save-draft``) — save the
    draft and submit it for human review: EDITING → PENDING_HUMAN_REVIEW.
    Optional body ``{draft_body}`` overwrites the draft before submitting."""

    required_capability = Capability.MANAGE_REVIEWS

    def transition(self, request, review):
        return state_machine.submit_for_review(
            review, request.user, draft_body=request.data.get("draft_body")
        )


class ReviewApproveView(_TransitionView):
    """``POST /api/reviews/<pk>/approve`` — THE HITL human approval:
    PENDING_HUMAN_REVIEW → APPROVED (stamps ``human_reviewer``)."""

    required_capability = Capability.APPROVE_REVIEW

    def transition(self, request, review):
        return state_machine.approve(review, request.user)


class ReviewRejectView(_TransitionView):
    """``POST /api/reviews/<pk>/reject`` — PENDING_HUMAN_REVIEW → REJECTED.
    Body ``{reason}`` is REQUIRED (422 otherwise — the machine enforces it)."""

    required_capability = Capability.APPROVE_REVIEW

    def transition(self, request, review):
        return state_machine.reject(review, request.user, reason=request.data.get("reason"))


class ReviewFinalizeView(_TransitionView):
    """``POST /api/reviews/<pk>/finalize`` — APPROVED → FINALIZED. The HITL
    gate: without a recorded human approval this is 422 HITL_APPROVAL_REQUIRED."""

    required_capability = Capability.FINALIZE_REVIEW

    def transition(self, request, review):
        return state_machine.finalize(review, request.user)


class ReviewRequestAIDraftView(RBACMixin, APIView):
    """``POST /api/reviews/<pk>/request-ai-draft`` — the Agent-1 seam
    (RUN_AI_REVIEW_DRAFT). Calls the drafting task SYNCHRONOUSLY.

    The LOUD seam: until Module 10 ships a provider, this returns 503 with
    ``reason: no_provider`` and the review stays in DRAFT — the manual path is
    never blocked and no fake draft is ever written.
    """

    required_capability = Capability.RUN_AI_REVIEW_DRAFT
    scope_subject_attr = "employee"

    def post(self, request, pk):
        review = get_object_or_404(Review.objects.all(), pk=pk)
        self.check_object_scope(review)
        # Synchronous call by design for the MVP (production may .delay() later).
        from .tasks import draft_review_with_agent1

        result = draft_review_with_agent1(
            str(request.user.tenant_id), str(pk), actor_id=str(request.user.id)
        )
        if not result.get("drafted"):
            if result.get("reason") == "no_provider":
                body = dict(result)
                body["detail"] = (
                    "Review Assistant (Agent 1) is not configured; "
                    "it lands in Module 10."
                )
                return Response(body, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response(result, status=status.HTTP_409_CONFLICT)
        review.refresh_from_db()
        return Response(ReviewSerializer(review).data)


class ReviewAssessmentListCreateView(RBACMixin, APIView):
    """``GET, POST /api/reviews/<pk>/assessments``.

    GET (VIEW_OWN_REVIEW + object scope): the review's assessments. The SUBJECT
    (OWN scope) sees ONLY their own submitted SELF row; manager-scope and
    HRBP/Admin see all of them.

    POST: submit an assessment.
      * SELF — SUBMIT_SELF_ASSESSMENT (everyone); the service additionally
        enforces that the caller IS the review's subject, and re-submission
        upserts.
      * MANAGER/PEER/UPWARD — SUBMIT_ASSESSMENT (Manager+) AND the caller must
        be in scope of the subject. Peer/upward capture for non-manager
        assessors arrives with Module 4 (360° Feedback); until then these
        types are deliberately manager-gated.
    """

    scope_subject_attr = "employee"

    def get_permissions(self):
        if self.request.method == "POST":
            # The capability depends on the assessment type: SELF is universal,
            # everything else is Manager+. Unknown/missing types fall through
            # to the stricter gate (fails closed); the serializer then 400s.
            if self.request.data.get("assessment_type") == ReviewAssessment.Type.SELF:
                self.required_capability = Capability.SUBMIT_SELF_ASSESSMENT
            else:
                self.required_capability = Capability.SUBMIT_ASSESSMENT
        else:
            self.required_capability = Capability.VIEW_OWN_REVIEW
        return super().get_permissions()

    def get(self, request, pk):
        review = get_object_or_404(Review.objects.all(), pk=pk)
        self.check_object_scope(review)
        assessments = review.assessments.all()
        if scope_for_role(request.user.role) is Scope.OWN:
            # The subject (object scope already guarantees caller == subject)
            # sees only what they themselves submitted — their SELF row.
            assessments = assessments.filter(assessor_id=request.user.id)
        return Response(AssessmentSerializer(assessments, many=True).data)

    def post(self, request, pk):
        review = get_object_or_404(Review.objects.all(), pk=pk)
        serializer = AssessmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assessment_type = serializer.validated_data["assessment_type"]
        if assessment_type != ReviewAssessment.Type.SELF:
            # MANAGER/PEER/UPWARD: the assessor must be in scope of the subject.
            if not actor_can_access(request.user, review.employee):
                raise PermissionDenied("This record is outside your access scope.")
        # The service enforces the structural rules (SELF subject==assessor,
        # SELF upsert, one row per (review, assessor)) and audits.
        assessment = submit_assessment(
            review=review,
            assessor=request.user,
            assessment_type=assessment_type,
            body=serializer.validated_data["body"],
        )
        return Response(
            AssessmentSerializer(assessment).data, status=status.HTTP_201_CREATED
        )


class ReviewCalibrationView(RBACMixin, APIView):
    """``GET /api/reviews/calibration?cycle=<id>`` — HRBP/Admin
    (CALIBRATE_REVIEWS): the tenant-wide calibration read view for a cycle,
    with an optional ``?state=`` filter. Read-only for now; calibration
    flagging arrives with a later module."""

    required_capability = Capability.CALIBRATE_REVIEWS

    def get(self, request):
        cycle_id = request.query_params.get("cycle")
        if not cycle_id:
            raise ValidationError({"cycle": "This query parameter is required."})
        # Tenant-scoped: a cross-tenant cycle id yields an empty list.
        reviews = Review.objects.filter(cycle_id=cycle_id)
        state = request.query_params.get("state")
        if state:
            reviews = reviews.filter(state=state)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(reviews, request, view=self)
        return paginator.get_paginated_response(
            CalibrationRowSerializer(page, many=True).data
        )
