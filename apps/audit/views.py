"""
The Audit Console — a READ-ONLY, tenant-scoped, paginated search over the
append-only :class:`~apps.audit.models.AuditLog`.

The console is HRBP (scoped) + Admin (tenant) and is READ-ONLY by construction:
it is a DRF :class:`~rest_framework.generics.ListAPIView`, so only ``GET`` is
exposed — a ``POST``/``PUT``/``DELETE`` is a 405. There is NO write surface here;
the audit log is append-only (Module-1 architecture rule 5) and the only writer
is :func:`apps.audit.services.record`, called by the services that mutate state.

Scope is automatic: ``AuditLog.objects`` is the tenant-scoped manager, so the
queryset is already confined to the caller's bound tenant (set from the JWT by
``TenantMiddleware``) — we never filter by tenant by hand. The view is the SOLE
RBAC gate (``required_capability``); the filters are plain, optional query-param
narrowing over the already-scoped rows.
"""
from __future__ import annotations

from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogPagination(PageNumberPagination):
    """Page the console: 50 rows/page by default, caller may raise to 200."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _parse_instant(value):
    """Parse an ISO date or datetime string into a value usable in a
    ``created_at`` range filter, or ``None`` when it is absent/blank/unparseable.
    A bare date parses fine (the DB compares it at midnight)."""
    if not value:
        return None
    return parse_datetime(value) or parse_date(value)


class AuditLogConsoleView(RBACMixin, ListAPIView):
    """``GET /api/audit/logs`` (VIEW_AUDIT_CONSOLE — HRBP+Admin) — a paginated,
    READ-ONLY, tenant-scoped search over the audit log.

    Optional query-param filters (absent/blank are ignored): ``actor`` (UUID),
    ``action`` (case-insensitive substring), ``target_type``, ``target_id``,
    ``date_from`` / ``date_to`` (ISO date/datetime → ``created_at`` range).
    Ordered newest-first (the model default).
    """

    required_capability = Capability.VIEW_AUDIT_CONSOLE
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination

    def get_queryset(self):
        # Tenant-scoped by the manager (the bound tenant) — never the whole table.
        qs = AuditLog.objects.all()
        params = self.request.query_params

        actor = params.get("actor")
        if actor:
            qs = qs.filter(actor_id=actor)

        action = params.get("action")
        if action:
            # Substring match: the console offers an "Action contains" box, so a
            # partial term like "approved" finds "review.approved".
            qs = qs.filter(action__icontains=action)

        target_type = params.get("target_type")
        if target_type:
            qs = qs.filter(target_type=target_type)

        target_id = params.get("target_id")
        if target_id:
            qs = qs.filter(target_id=target_id)

        date_from = _parse_instant(params.get("date_from"))
        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)

        date_to = _parse_instant(params.get("date_to"))
        if date_to is not None:
            qs = qs.filter(created_at__lte=date_to)

        return qs
