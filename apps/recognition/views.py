"""
Recognition HTTP surface (mounted at ``/api/recognition/``). Thin views over the
services; RBAC capability gates on each (the FEED's row visibility + the
sender-only delete live in the services, not the capability layer).
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from .models import COMPANY_VALUES, REACTION_EMOJIS, Recognition
from .serializers import serialize_feed, serialize_recognition
from .services import (
    create_recognition,
    delete_recognition,
    recognition_analytics,
    recognition_feed,
    toggle_reaction,
)


class RecognitionListCreateView(RBACMixin, APIView):
    """``GET, POST /api/recognition/``.

    GET (VIEW_RECOGNITION): the caller's visibility-filtered feed.
    POST (GIVE_RECOGNITION): give a recognition to a teammate.
    """

    _caps = {"GET": Capability.VIEW_RECOGNITION, "POST": Capability.GIVE_RECOGNITION}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        feed = recognition_feed(request.user)
        return Response(serialize_feed(feed, request.user))

    def post(self, request):
        rec = create_recognition(
            request.user,
            recipient_id=request.data.get("recipient"),
            value=request.data.get("value", ""),
            message=request.data.get("message", ""),
            visibility=request.data.get("visibility", Recognition.Visibility.TEAM),
            badge=request.data.get("badge", ""),
        )
        return Response(serialize_recognition(rec, request.user), status=status.HTTP_201_CREATED)


class RecognitionDetailView(RBACMixin, APIView):
    """``DELETE /api/recognition/<id>`` (GIVE_RECOGNITION) — sender-only soft delete
    (enforced in the service)."""

    required_capability = Capability.GIVE_RECOGNITION

    def delete(self, request, pk):
        delete_recognition(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecognitionReactView(RBACMixin, APIView):
    """``POST /api/recognition/<id>/react`` (VIEW_RECOGNITION) — toggle the
    caller's emoji reaction; reacting to a card outside the caller's visibility is
    a 404 (never reveal it exists)."""

    required_capability = Capability.VIEW_RECOGNITION

    def post(self, request, pk):
        result = toggle_reaction(request.user, pk, request.data.get("emoji", ""))
        return Response(result)


class RecognitionMetaView(RBACMixin, APIView):
    """``GET /api/recognition/meta`` (VIEW_RECOGNITION) — the give-form options:
    company values, reaction palette, visibility choices."""

    required_capability = Capability.VIEW_RECOGNITION

    def get(self, request):
        return Response(
            {
                "values": COMPANY_VALUES,
                "reactions": REACTION_EMOJIS,
                "visibilities": [
                    {"value": v, "label": label} for v, label in Recognition.Visibility.choices
                ],
            }
        )


class RecognitionAnalyticsView(RBACMixin, APIView):
    """``GET /api/recognition/analytics`` (VIEW_RECOGNITION_ANALYTICS — Manager+) —
    aggregate-only stats (no per-person leaderboard)."""

    required_capability = Capability.VIEW_RECOGNITION_ANALYTICS

    def get(self, request):
        return Response(recognition_analytics(request.user))
