"""
Check-in HTTP surface (mounted at ``/api/checkins/``). Thin views over the
services; the capability gates are coarse (own vs team), the real ROW scope (own /
reporting-subtree / 404) lives in the services.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from .serializers import serialize_checkin, serialize_list
from .services import (
    checkin_goal_progress,
    get_readable_checkin,
    my_checkins,
    respond_to_checkin,
    team_checkins,
    upsert_checkin,
)


class CheckInListCreateView(RBACMixin, APIView):
    """``GET, POST /api/checkins/`` (MANAGE_OWN_CHECKIN) — the caller's OWN check-ins;
    POST upserts the caller's check-in for a week (one per week)."""

    required_capability = Capability.MANAGE_OWN_CHECKIN

    def get(self, request):
        return Response(serialize_list(my_checkins(request.user)))

    def post(self, request):
        ci = upsert_checkin(
            request.user,
            week_of=request.data.get("week_of"),
            mood=request.data.get("mood"),
            wins=request.data.get("wins", ""),
            blockers=request.data.get("blockers", ""),
            learning=request.data.get("learning", ""),
            priorities=request.data.get("priorities"),
        )
        # Re-read with relations for a complete payload.
        return Response(serialize_checkin(get_readable_checkin(request.user, ci.id)), status=status.HTTP_201_CREATED)


class TeamCheckInsView(RBACMixin, APIView):
    """``GET /api/checkins/team`` (VIEW_TEAM_CHECKINS — Manager+) — check-ins from the
    caller's reporting subtree (scope-bound in the service)."""

    required_capability = Capability.VIEW_TEAM_CHECKINS

    def get(self, request):
        return Response(serialize_list(team_checkins(request.user)))


class CheckInDetailView(RBACMixin, APIView):
    """``GET /api/checkins/<id>`` (MANAGE_OWN_CHECKIN — everyone holds it; the SERVICE
    enforces own-or-manager-scope, else 404). Includes the author's read-only goal
    progress pulled live from the goals engine."""

    required_capability = Capability.MANAGE_OWN_CHECKIN

    def get(self, request, pk):
        ci = get_readable_checkin(request.user, pk)
        data = serialize_checkin(ci)
        data["goal_progress"] = checkin_goal_progress(ci.author)
        return Response(data)


class CheckInRespondView(RBACMixin, APIView):
    """``POST /api/checkins/<id>/respond`` (RESPOND_CHECKIN — Manager+) — respond to a
    REPORT's check-in (scope-bound; 404 if out of scope, 403 if it's your own)."""

    required_capability = Capability.RESPOND_CHECKIN

    def post(self, request, pk):
        respond_to_checkin(
            request.user,
            pk,
            comment=request.data.get("comment", ""),
            reaction=request.data.get("reaction", ""),
            follow_up=request.data.get("follow_up", False),
            add_to_one_on_one=request.data.get("add_to_one_on_one", False),
        )
        return Response(serialize_checkin(get_readable_checkin(request.user, pk)))
