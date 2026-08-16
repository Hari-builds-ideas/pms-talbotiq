"""
The Admin Hub API — the HTTP surface of Module 11's administration app, mounted
under ``/api/admin/``. EVERY endpoint is Admin-only.

Views stay THIN and are the SOLE RBAC gate: each declares its
``required_capability`` (or, for a multi-method view, a ``_caps`` map + a
``get_permissions`` override). The ``services`` are the SOLE mutators and the SOLE
audit writers — the views only gate the capability, validate the body shape,
resolve referenced users through the tenant-scoped ``User.objects`` manager (a
cross-tenant id → 404), call the service, and serialize.

Everything that could be spoofed is server-set: the actor is ``request.user`` and
the tenant is ``request.user.tenant`` (bound from the verified JWT by
``TenantMiddleware``) — never accepted from the client. Service exceptions
propagate to DRF automatically: an unknown role / duplicate email → 422
(``InvalidAdminInput``); a reporting cycle → 422 (``ReportingCycle``); a
cross-tenant referenced id → 404 (``get_object_or_404`` over the scoped manager).
"""
from __future__ import annotations

import re

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.concurrency import check_version
from apps.core.pagination import StandardResultsSetPagination
from apps.identity.models import User
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin

from . import data_rights, erasure, services
from .exceptions import InvalidAdminInput
from .serializers import (
    EraseUserSerializer,
    CreateUserSerializer,
    DisplayNameSerializer,
    ReportingLineSerializer,
    SetRoleSerializer,
    TenantConfigSerializer,
    UserAdminSerializer,
)


# ── data subject rights (D1/D2) ───────────────────────────────────────────────


class UserExportView(RBACMixin, APIView):
    """``GET /api/admin/users/<id>/export`` (MANAGE_TENANT — Admin).

    Everything held about one employee, as one JSON document. See
    ``docs/BUILD/DATA_RIGHTS_DESIGN.md``.

    MANAGE_TENANT rather than MANAGE_USERS_ROLES: both are Admin-only today, but
    they mean different things. Managing users is routine administration; reading
    one person's entire performance history — every review body, every piece of
    360 feedback about them, their nine-box placement — is not, and the
    capability it requires should say so if the two ever diverge.

    The access is audited with the subject's id. An admin pulling an employee's
    complete record is exactly the legitimate-but-sensitive action the audit
    console exists to make visible afterwards.
    """

    required_capability = Capability.MANAGE_TENANT

    def get(self, request, pk):
        subject = get_object_or_404(User.objects.all(), pk=pk)
        record(
            action="privacy.user_exported",
            actor=request.user,
            target_type="user",
            target_id=subject.id,
            metadata={"subject_email": subject.email},
            tenant=request.user.tenant_id,
        )
        return Response(data_rights.export_user(subject))


class UserEraseView(RBACMixin, APIView):
    """``POST /api/admin/users/<id>/erase`` (MANAGE_TENANT — Admin).

    Irreversible. Body::

        {"confirm": "<the subject's email>", "justification": "why, in words"}

    The confirmation is the subject's own email typed back, not a checkbox and
    not the literal word ERASE. A fixed word is muscle memory by the second time;
    retyping *this person's* address is the one thing that cannot be done
    absent-mindedly on the wrong row — and acting on the id below the one you
    meant is the mistake that actually happens here.

    The justification is required and must be more than a token, because it lands
    in the append-only audit log. "test" tells a future auditor nothing, and by
    the time they read it the data is gone and cannot be re-read for context.
    """

    required_capability = Capability.MANAGE_TENANT

    def post(self, request, pk):
        subject = get_object_or_404(User.objects.all(), pk=pk)
        serializer = EraseUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Compared against the CURRENT email, so a repeat confirm can never match
        # a stale address the admin still has on screen after a tombstone.
        if data["confirm"].strip().lower() != subject.email.strip().lower():
            raise InvalidAdminInput(
                "The confirmation does not match this person's email address. Type "
                "it exactly to confirm you are erasing the right record."
            )
        try:
            summary = erasure.erase_user(
                request.user, subject, justification=data["justification"].strip()
            )
        except erasure.CannotErase as exc:
            raise InvalidAdminInput(str(exc)) from exc
        return Response(summary)


# ── users / roles ──────────────────────────────────────────────────────────────


class UserListCreateView(RBACMixin, APIView):
    """``GET, POST /api/admin/users`` (MANAGE_USERS_ROLES — Admin).

    GET: the actor's tenant users, PAGINATED (``{count,next,previous,results}``,
    50/page) with an optional ``?search=`` filter (email / display name / role,
    server-side) — so a large tenant never ships its whole user list. POST:
    create a user; the optional ``manager`` UUID is resolved through the
    tenant-scoped manager (cross-tenant id → 404). A duplicate email or unknown
    role → 422.
    """

    _caps = {"GET": Capability.MANAGE_USERS_ROLES, "POST": Capability.MANAGE_USERS_ROLES}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        users = services.list_users(request.user, search=search or None)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(users, request, view=self)
        return paginator.get_paginated_response(
            UserAdminSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Headcount gate (PHASE2 L1.4): seats + the plan's employee limit.
        from apps.billing.services import can_add_user

        allowed, reason = can_add_user(request.user.tenant_id)
        if not allowed:
            return Response({"detail": reason}, status=status.HTTP_409_CONFLICT)
        manager = None
        if data.get("manager") is not None:
            manager = get_object_or_404(User.objects.all(), pk=data["manager"])
        user = services.create_user(
            request.user,
            email=data["email"],
            role=data["role"],
            manager=manager,
            password=data.get("password"),
            display_name=data.get("display_name"),
        )
        return Response(
            UserAdminSerializer(user).data, status=status.HTTP_201_CREATED
        )


class EmployeeImportView(RBACMixin, APIView):
    """``POST /api/admin/users/import`` (INVITE_USERS — HRBP+) — bulk-onboard
    employees from a CSV. Accepts EITHER a multipart ``file`` (CSV with a header
    row: ``name,email,role,department,designation,manager``) OR a JSON body
    ``{"rows": [{...}, ...]}``. Idempotent (upsert by email), per-row errors, seat
    +role-ceiling enforced. Returns ``{created,updated,skipped,total,errors}``."""

    required_capability = Capability.INVITE_USERS

    _MAX_ROWS = 5000
    _CANON = {  # tolerate common header spellings → our canonical keys
        "name": "name", "full name": "name", "employee name": "name",
        "email": "email", "email address": "email", "work email": "email",
        "role": "role",
        "department": "department", "dept": "department",
        "designation": "designation", "title": "designation", "job title": "designation",
        "manager": "manager", "manager email": "manager", "reports to": "manager",
    }

    def _rows_from_csv(self, file_obj) -> list[dict]:
        import csv
        import io

        raw = file_obj.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig", errors="replace")  # strip BOM
        reader = csv.DictReader(io.StringIO(raw))
        rows = []
        for r in reader:
            row = {}
            for k, v in r.items():
                if k is None:
                    continue
                key = self._CANON.get(str(k).strip().lower())
                if key:
                    row[key] = (v or "").strip()
            if any(row.values()):
                rows.append(row)
        return rows

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is not None:
            try:
                rows = self._rows_from_csv(upload)
            except Exception:  # noqa: BLE001 — a malformed file is a 400, not a 500
                return Response({"detail": "Could not parse the CSV file."},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            rows = request.data.get("rows")
            if not isinstance(rows, list):
                return Response(
                    {"detail": "Provide a CSV `file` upload or a JSON `rows` array."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if not rows:
            return Response({"detail": "No rows found to import."},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > self._MAX_ROWS:
            return Response(
                {"detail": f"Too many rows ({len(rows)}). Import in batches of "
                           f"{self._MAX_ROWS} or fewer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = services.bulk_import_employees(request.user, rows)
        return Response(result, status=status.HTTP_200_OK)


class UserStatsView(RBACMixin, APIView):
    """``GET /api/admin/users/stats`` (MANAGE_USERS_ROLES — Admin) — tenant user
    counts (active/inactive totals + active-by-role), aggregated in the DB so the
    dashboard never downloads the whole user list just to count it."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def get(self, request):
        return Response(services.user_stats(request.user))


class UserRoleView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/role`` (MANAGE_USERS_ROLES — Admin) — assign a
    role. The target user is resolved through the tenant-scoped manager
    (cross-tenant id → 404); an unknown role → 422."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = SetRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_role(request.user, user, serializer.validated_data["role"])
        return Response(UserAdminSerializer(user).data)


class UserDisplayNameView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/display-name`` (MANAGE_USERS_ROLES — Admin) —
    set/clear a user's display name. Blank/null clears it (→ email fallback)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = DisplayNameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_display_name(
            request.user, user, serializer.validated_data["display_name"]
        )
        return Response(UserAdminSerializer(user).data)


class UserOrgProfileView(RBACMixin, APIView):
    """``PATCH /api/admin/users/<pk>/profile`` (MANAGE_USERS_ROLES — Admin) — set
    the ORG-controlled profile fields (title/department/employee_id/phone). The
    self-service fields live on /api/auth/profile (PHASE2 L1.1). Audited."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def patch(self, request, pk):
        from apps.audit.services import record

        from .serializers import OrgProfileFieldsSerializer

        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = OrgProfileFieldsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = []
        for field, value in serializer.validated_data.items():
            setattr(user, field, value)
            changed.append(field)
        if changed:
            record(
                action="admin.user_profile_updated", actor=request.user,
                target_type="user", target_id=user.id,
                metadata={"fields": sorted(changed)}, tenant=request.user.tenant_id,
            )
            user.save(update_fields=changed)
        return Response(UserAdminSerializer(user).data)


class UserDeactivateView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/deactivate`` (MANAGE_USERS_ROLES — Admin) — set
    the user inactive. The target is resolved through the tenant-scoped manager
    (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        user = services.set_active(request.user, user, is_active=False)
        return Response(UserAdminSerializer(user).data)


class UserReactivateView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/reactivate`` (MANAGE_USERS_ROLES — Admin) — set
    the user active. The target is resolved through the tenant-scoped manager
    (cross-tenant id → 404)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        user = services.set_active(request.user, user, is_active=True)
        return Response(UserAdminSerializer(user).data)


class UserReportingLineView(RBACMixin, APIView):
    """``POST /api/admin/users/<pk>/reporting-line`` (MANAGE_USERS_ROLES — Admin) —
    reassign the user's manager. Both the user and the new ``manager`` are resolved
    through the tenant-scoped manager (cross-tenant id → 404). A cycle → 422
    (``ReportingCycle``, raised by the reused Module-7 reassignment)."""

    required_capability = Capability.MANAGE_USERS_ROLES

    def post(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        serializer = ReportingLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_manager = get_object_or_404(
            User.objects.all(), pk=serializer.validated_data["manager"]
        )
        user = services.set_reporting_line(request.user, user, new_manager)
        return Response(UserAdminSerializer(user).data)


# ── tenant config ────────────────────────────────────────────────────────────


#: Org-settings keys (PHASE2 L1.5) stored under TenantConfig.settings["org"].
_ORG_KEYS = ("name", "timezone", "language", "logo_url", "primary_color")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class OrgSettingsView(RBACMixin, APIView):
    """``GET, PATCH /api/admin/org-settings`` (MANAGE_TENANT — Admin).

    PHASE2 L1.5 — plain, typed org settings (name/timezone/language defaults) +
    the branding hooks (logo_url/primary_color), stored in the existing
    TenantConfig bag under ``org``. Branding fields are gated server-side by the
    plan's ``custom_branding`` feature. Served to every user via /me
    (``tenant_branding``) so the shell can theme. Custom domains are a designed
    future item (not built)."""

    _caps = {"GET": Capability.MANAGE_TENANT, "PATCH": Capability.MANAGE_TENANT}

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        config = services.get_tenant_config(request.user)
        return Response(config.settings.get("org", {}))

    def patch(self, request):
        import zoneinfo

        from apps.audit.services import record
        from apps.billing.services import feature_flags_for

        updates = {k: request.data[k] for k in _ORG_KEYS if k in request.data}
        if not updates:
            return Response({"detail": "Nothing to update."}, status=400)
        if "timezone" in updates:
            try:
                zoneinfo.ZoneInfo(str(updates["timezone"]))
            except Exception:
                return Response({"timezone": ["Unknown timezone."]}, status=400)
        if "primary_color" in updates and updates["primary_color"]:
            if not _HEX_COLOR_RE.match(str(updates["primary_color"])):
                return Response({"primary_color": ["Use a #RRGGBB hex color."]}, status=400)
        if ("logo_url" in updates or "primary_color" in updates) and not feature_flags_for(
            request.user.tenant
        ).get("custom_branding"):
            return Response(
                {"detail": "Custom branding is an Enterprise-plan feature."},
                status=status.HTTP_403_FORBIDDEN,
            )
        config = services.get_tenant_config(request.user)
        org = dict(config.settings.get("org", {}))
        org.update({k: str(v) for k, v in updates.items()})
        config.settings["org"] = org
        record(
            action="admin.org_settings_updated", actor=request.user,
            target_type="tenant_config", target_id=config.id,
            metadata={"keys": sorted(updates)}, tenant=request.user.tenant_id,
        )
        config.save(update_fields=["settings"])
        return Response(org)


class TenantConfigView(RBACMixin, APIView):
    """``GET, PUT /api/admin/tenant-config`` (MANAGE_TENANT_CONFIG — Admin).

    GET: the tenant's config (creating an empty row on first access). PUT: replace
    the ``settings`` bag (a JSON object); a non-object → 422 in the service.
    """

    _caps = {
        "GET": Capability.MANAGE_TENANT_CONFIG,
        "PUT": Capability.MANAGE_TENANT_CONFIG,
    }

    def get_permissions(self):
        self.required_capability = self._caps.get(self.request.method)
        return super().get_permissions()

    def get(self, request):
        config = services.get_tenant_config(request.user)
        return Response(TenantConfigSerializer(config).data)

    def put(self, request):
        # Optimistic lock: a stale `version` → 409 (two admins can't clobber).
        check_version(services.get_tenant_config(request.user), request.data)
        config = services.update_tenant_config(
            request.user, settings=request.data.get("settings", {})
        )
        return Response(TenantConfigSerializer(config).data)
