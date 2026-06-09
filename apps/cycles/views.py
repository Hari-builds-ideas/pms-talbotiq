"""
Performance-cycle API — cycle CRUD plus the score read/recompute endpoints.

Every view is RBAC-gated (``RBACMixin``); the tenant is bound from the JWT by
``TenantMiddleware`` so the scoped managers auto-filter — a cross-tenant row
simply does not resolve (404), and we never filter by tenant by hand. Views are
thin: cycle persistence is in ``CycleSerializer``, the score math is in
``apps.goals.tasks.recompute_cycle_scores`` (called synchronously), and every
consequential action audits BEFORE the side effect.
"""
from __future__ import annotations

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.goals.models import CycleScore
from apps.goals.tasks import recompute_cycle_scores
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin
from apps.rbac.scope import Scope, reporting_subtree_ids, scope_for_role

from .models import PerformanceCycle
from .serializers import CycleScoreSerializer, CycleSerializer


class CycleListCreateView(RBACMixin, APIView):
    """``GET, POST /api/cycles/`` — list + create cycles (HRBP/Admin)."""

    required_capability = Capability.MANAGE_CYCLES

    def get(self, request):
        cycles = PerformanceCycle.objects.all()
        return Response(CycleSerializer(cycles, many=True).data)

    def post(self, request):
        serializer = CycleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Audit the intent BEFORE the row is written.
        record(
            action="cycle.created",
            actor=request.user,
            target_type="cycle",
            metadata={"name": serializer.validated_data.get("name")},
        )
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CycleDetailView(RBACMixin, APIView):
    """``GET, PATCH, DELETE /api/cycles/<pk>`` — retrieve / update / soft-delete
    a cycle (HRBP/Admin). DELETE is a soft delete (``instance.delete()``)."""

    required_capability = Capability.MANAGE_CYCLES

    def _get_cycle(self, pk):
        # Scoped manager → a cycle from another tenant 404s.
        return get_object_or_404(PerformanceCycle.objects.all(), pk=pk)

    def get(self, request, pk):
        return Response(CycleSerializer(self._get_cycle(pk)).data)

    def patch(self, request, pk):
        cycle = self._get_cycle(pk)
        serializer = CycleSerializer(cycle, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        cycle = self._get_cycle(pk)
        cycle.delete()  # soft delete — stamps deleted_at
        return Response(status=status.HTTP_204_NO_CONTENT)


class CycleRecomputeView(RBACMixin, APIView):
    """``POST /api/cycles/<cycle_id>/recompute`` — trigger a synchronous score
    recompute for the whole tenant+cycle cohort (Manager+)."""

    required_capability = Capability.VIEW_TEAM_SCORES

    def post(self, request, cycle_id):
        # 404 if the cycle is not in the caller's tenant.
        get_object_or_404(PerformanceCycle.objects.all(), pk=cycle_id)
        # Audit BEFORE the recompute side effect.
        record(
            action="scores.recomputed",
            actor=request.user,
            target_type="cycle",
            target_id=cycle_id,
        )
        rows = recompute_cycle_scores(request.user.tenant_id, cycle_id)
        return Response({"cycle_id": str(cycle_id), "scored": len(rows)})


class MyCycleScoreView(RBACMixin, APIView):
    """``GET /api/cycles/<cycle_id>/scores/me`` — the caller's own CycleScore for
    the cycle (all roles, OWN scope). 404 if none has been computed yet."""

    required_capability = Capability.VIEW_OWN_GOALS

    def get(self, request, cycle_id):
        get_object_or_404(PerformanceCycle.objects.all(), pk=cycle_id)
        score = CycleScore.objects.filter(
            cycle_id=cycle_id, employee_id=request.user.id
        ).first()
        if score is None:
            raise Http404("No score for this cycle.")
        return Response(CycleScoreSerializer(score).data)


class CycleScoresView(RBACMixin, APIView):
    """``GET /api/cycles/<cycle_id>/scores`` — team / tenant scores (Manager+).

    Scope branches on the caller's role:
      * MANAGER (TEAM) → their reporting subtree plus themselves;
      * HRBP / ADMIN (TENANT) → every score in the tenant.
    The scoped manager already isolates the tenant, so cross-tenant scores never
    appear.
    """

    required_capability = Capability.VIEW_TEAM_SCORES

    def get(self, request, cycle_id):
        get_object_or_404(PerformanceCycle.objects.all(), pk=cycle_id)
        scores = CycleScore.objects.filter(cycle_id=cycle_id)
        if scope_for_role(request.user.role) is not Scope.TENANT:
            # TEAM scope: subtree + self.
            visible = reporting_subtree_ids(request.user) | {request.user.id}
            scores = scores.filter(employee_id__in=visible)
        return Response(CycleScoreSerializer(scores, many=True).data)
