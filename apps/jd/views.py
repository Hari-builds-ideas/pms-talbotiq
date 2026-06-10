"""
JD Library API — the HTTP surface of the Module-6 manual authoring flow + the
loud AI-generator seam.

Views stay THIN on purpose:
  * creation goes through ``lifecycle.create_jd`` (DRAFT + v1, audited);
  * every state change goes through a ``lifecycle`` function, which enforces
    legality (409 ``ILLEGAL_JD_TRANSITION``) and the HITL/content gate
    (422 ``INVALID_JD_INPUT``) internally — the transition views only fast-fail
    the capability via ``RBACMixin`` (a cheap early 403), load the JD through the
    tenant-scoped manager (a cross-tenant id → 404), call the function and
    return the serialized JD;
  * library reads (detail/versions/export/search) go through
    ``services.visible_jds`` / ``services.search_jds`` so the §2 scope rule —
    managers+ see the whole library, everyone else PUBLISHED only — falls out as
    a 404 (never a 403 that leaks existence) for a non-manager on a non-published
    JD;
  * the AI body comes from ``tasks.generate_jd``, called SYNCHRONOUSLY. Until
    Module 10 ships a provider it returns ``no_provider`` and the view surfaces a
    loud 503 — the JD is left untouched and no fake body is ever written.

The tenant is bound from the JWT by ``TenantMiddleware``; the scoped managers
auto-filter, so a cross-tenant row never resolves and we never filter by tenant
by hand. The lifecycle/services do NOT re-check RBAC — these views are the SOLE
RBAC gate, so every endpoint declares its capability.

There is deliberately NO PATCH/PUT mutator: the lifecycle is the only mutator.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import lifecycle, services
from .models import JDRequest, JDTemplate, JobDescription
from .serializers import (
    FulfilRequestSerializer,
    JDDraftSerializer,
    JDRequestCreateSerializer,
    JDRequestSerializer,
    JDTemplateSerializer,
    JDVersionSerializer,
    JobDescriptionCreateSerializer,
    JobDescriptionSerializer,
    TemplateInstantiateSerializer,
)
from .tasks import generate_jd


class JDListCreateView(RBACMixin, APIView):
    """``GET, POST /api/jd/``.

    GET (VIEW_JD_LIBRARY): the actor-visible library, with optional ``?q=`` and
    ``?status=`` filters (an employee can never widen past PUBLISHED). POST
    (MANAGE_JD_LIBRARY): create a DRAFT job description (+ its first version).
    """

    _caps = {"GET": Capability.VIEW_JD_LIBRARY, "POST": Capability.MANAGE_JD_LIBRARY}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        jds = services.search_jds(
            request.user,
            q=request.query_params.get("q", ""),
            status=request.query_params.get("status"),
        )
        return Response(JobDescriptionSerializer(jds, many=True).data)

    def post(self, request):
        serializer = JobDescriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        jd = lifecycle.create_jd(
            title=data["title"],
            level=data["level"],
            department=data["department"],
            actor=request.user,
            body=data["body"],
            inputs=data["inputs"],
        )
        return Response(
            JobDescriptionSerializer(jd).data, status=status.HTTP_201_CREATED
        )


class JDDetailView(RBACMixin, APIView):
    """``GET /api/jd/<pk>`` — JD detail (VIEW_JD_LIBRARY). Loaded through
    ``visible_jds`` so a non-manager 404s on a non-published JD (the scope rule
    hides it rather than leaking a 403)."""

    required_capability = Capability.VIEW_JD_LIBRARY

    def get(self, request, pk):
        jd = get_object_or_404(services.visible_jds(request.user), pk=pk)
        return Response(JobDescriptionSerializer(jd).data)


class JDVersionListView(RBACMixin, APIView):
    """``GET /api/jd/<pk>/versions`` (VIEW_JD_LIBRARY) — the JD's version history
    (newest first; the model orders by ``-version_number``). Same visibility as
    the detail."""

    required_capability = Capability.VIEW_JD_LIBRARY

    def get(self, request, pk):
        jd = get_object_or_404(services.visible_jds(request.user), pk=pk)
        return Response(JDVersionSerializer(jd.versions.all(), many=True).data)


class JDExportView(RBACMixin, APIView):
    """``GET /api/jd/<pk>/export`` (VIEW_JD_LIBRARY) — the rendered text +
    structured body of the published (else working) version. Same visibility as
    the detail."""

    required_capability = Capability.VIEW_JD_LIBRARY

    def get(self, request, pk):
        jd = get_object_or_404(services.visible_jds(request.user), pk=pk)
        return Response(services.jd_export(jd))


class _JDTransitionView(RBACMixin, APIView):
    """Base for the lifecycle-transition endpoints: load the JD through the
    scoped manager (a cross-tenant id → 404), hand it to the lifecycle, return
    the serialized JD.

    The view's ``required_capability`` is the RBAC gate (these views ARE the
    sole gate); the lifecycle re-checks state legality (409) and content
    (422), which DRF's exception handler maps to the response.
    """

    def post(self, request, pk):
        jd = get_object_or_404(JobDescription.objects.all(), pk=pk)
        jd = self.transition(request, jd)
        return Response(JobDescriptionSerializer(jd).data)

    def transition(self, request, jd):  # pragma: no cover - abstract
        raise NotImplementedError


class JDSaveDraftView(_JDTransitionView):
    """``POST /api/jd/<pk>/save-draft`` (MANAGE_JD_LIBRARY) — edit the working
    version's body/inputs (legal in DRAFT or PENDING_HUMAN_REVIEW). Only the
    fields PRESENT in the request are passed through, so an absent field is left
    untouched rather than cleared."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def transition(self, request, jd):
        serializer = JDDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kwargs = {}
        if "body" in serializer.validated_data:
            kwargs["body"] = serializer.validated_data["body"]
        if "inputs" in serializer.validated_data:
            kwargs["inputs"] = serializer.validated_data["inputs"]
        return lifecycle.save_draft(jd, request.user, **kwargs)


class JDSubmitView(_JDTransitionView):
    """``POST /api/jd/<pk>/submit`` (MANAGE_JD_LIBRARY) — DRAFT →
    PENDING_HUMAN_REVIEW. The lifecycle validates the required content first
    (422 INVALID_JD_INPUT)."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def transition(self, request, jd):
        return lifecycle.submit_for_review(jd, request.user)


class JDApproveView(_JDTransitionView):
    """``POST /api/jd/<pk>/approve`` (MANAGE_JD_LIBRARY) — THE HITL human
    approval. With an active "jd" workflow it ENTERS the approval route
    (IN_REVIEW); with none it single-step PUBLISHES."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def transition(self, request, jd):
        return lifecycle.approve(jd, request.user)


class JDReviseView(_JDTransitionView):
    """``POST /api/jd/<pk>/revise`` (MANAGE_JD_LIBRARY) — PUBLISHED → a NEW DRAFT
    version (the published version stays live + immutable)."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def transition(self, request, jd):
        return lifecycle.revise(jd, request.user)


class JDArchiveView(_JDTransitionView):
    """``POST /api/jd/<pk>/archive`` (MANAGE_JD_LIBRARY) — any (non-ARCHIVED) →
    ARCHIVED."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def transition(self, request, jd):
        return lifecycle.archive(jd, request.user)


class JDGenerateView(RBACMixin, APIView):
    """``POST /api/jd/<pk>/generate`` (GENERATE_JD) — the JD-Generator seam.
    Calls the drafting task SYNCHRONOUSLY.

    The LOUD seam: until Module 10 ships a provider this returns 503 with
    ``reason: no_provider`` and the JD stays in DRAFT — the manual path is never
    blocked and no fake body is ever written. A missing inputs snapshot raises
    ``InvalidJDInput`` (422) inside the task and propagates automatically; any
    other skip reason (not_found / bad_state / actor_*) is a 409.
    """

    required_capability = Capability.GENERATE_JD

    def post(self, request, pk):
        # Synchronous call by design for the MVP (production may .delay() later).
        # InvalidJDInput (missing inputs) propagates as 422 — do NOT catch it.
        result = generate_jd(
            str(request.user.tenant_id), str(pk), actor_id=str(request.user.id)
        )
        if not result.get("generated"):
            if result.get("reason") == "no_provider":
                body = dict(result)
                body["detail"] = (
                    "The JD Generator is not configured; it lands in Module 10."
                )
                return Response(body, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response(result, status=status.HTTP_409_CONFLICT)
        jd = get_object_or_404(JobDescription.objects.all(), pk=pk)
        return Response(JobDescriptionSerializer(jd).data)


class JDTemplateListView(RBACMixin, APIView):
    """``GET /api/jd/templates`` (MANAGE_JD_LIBRARY) — the tenant's role-family
    scaffolds (seeded per tenant)."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def get(self, request):
        return Response(
            JDTemplateSerializer(JDTemplate.objects.all(), many=True).data
        )


class JDTemplateInstantiateView(RBACMixin, APIView):
    """``POST /api/jd/templates/<pk>/instantiate`` (MANAGE_JD_LIBRARY) — create a
    DRAFT JD (+ v1) from the template scaffold. Blank/absent title/level/
    department fall back to the template's own pattern/level inside the
    service."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def post(self, request, pk):
        template = get_object_or_404(JDTemplate.objects.all(), pk=pk)
        serializer = TemplateInstantiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        kwargs = {}
        if data.get("title"):
            kwargs["title"] = data["title"]
        if data.get("level"):
            kwargs["level"] = data["level"]
        if data.get("department"):
            kwargs["department"] = data["department"]
        jd = services.instantiate_template(
            template=template, actor=request.user, **kwargs
        )
        return Response(
            JobDescriptionSerializer(jd).data, status=status.HTTP_201_CREATED
        )


class JDRequestListCreateView(RBACMixin, APIView):
    """``GET, POST /api/jd/requests``.

    GET (REQUEST_JD): the JD requests the actor may see — a Manager sees their
    OWN, HRBP/Admin see the whole tenant's (they fulfil them). POST (REQUEST_JD):
    a Manager+ asks HRBP to author/generate a JD (OPEN, requester server-set).
    """

    _caps = {"GET": Capability.REQUEST_JD, "POST": Capability.REQUEST_JD}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        requests = services.visible_jd_requests(request.user)
        return Response(JDRequestSerializer(requests, many=True).data)

    def post(self, request):
        serializer = JDRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        jd_request = services.create_jd_request(
            requester=request.user,
            title=data["title"],
            level=data["level"],
            notes=data["notes"],
        )
        return Response(
            JDRequestSerializer(jd_request).data, status=status.HTTP_201_CREATED
        )


class JDRequestFulfilView(RBACMixin, APIView):
    """``POST /api/jd/requests/<pk>/fulfil`` (MANAGE_JD_LIBRARY) — mark an OPEN
    request FULFILLED, linking the JD that satisfies it. Both the request and
    the JD are loaded through the scoped manager (cross-tenant id → 404); the
    service 409s if the request is not OPEN."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def post(self, request, pk):
        jd_request = get_object_or_404(JDRequest.objects.all(), pk=pk)
        serializer = FulfilRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        jd = get_object_or_404(
            JobDescription.objects.all(), pk=serializer.validated_data["jd"]
        )
        jd_request = services.fulfil_jd_request(
            request=jd_request, jd=jd, actor=request.user
        )
        return Response(JDRequestSerializer(jd_request).data)


class JDRequestDeclineView(RBACMixin, APIView):
    """``POST /api/jd/requests/<pk>/decline`` (MANAGE_JD_LIBRARY) — mark an OPEN
    request DECLINED (optional body ``{reason}``). 409 if the request is not
    OPEN."""

    required_capability = Capability.MANAGE_JD_LIBRARY

    def post(self, request, pk):
        jd_request = get_object_or_404(JDRequest.objects.all(), pk=pk)
        jd_request = services.decline_jd_request(
            request=jd_request,
            actor=request.user,
            reason=request.data.get("reason", ""),
        )
        return Response(JDRequestSerializer(jd_request).data)
