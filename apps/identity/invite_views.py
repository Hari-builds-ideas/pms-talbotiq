"""
PHASE2 L1.2 — invitation-based onboarding (B2B; no self-signup).

Admin/HRBP (``invite_users``) creates an invite → the invitee opens a signed,
time-limited link → sets a password → joins THIS tenant with the assigned role.
The link is returned to the inviter as well (copy-paste UX), so onboarding never
blocks on email delivery. Seats are enforced at ACCEPT time.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models as dj_models
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.mail import send_templated_email
from apps.core.throttling import AtomicAnonThrottle
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin
from apps.tenancy.context import tenant_context

from .models import Invitation, User

logger = logging.getLogger("pms.identity")

_INVITE_SALT = "pms.invite"
_INVITE_MAX_AGE = 7 * 24 * 3600  # 7 days

# Role ordering for the invite privilege-escalation ceiling (increasing breadth).
# Mirrors the SAML rank cap (apps/identity/saml/service.py): an inviter may assign
# a role AT OR BELOW their own, never above it. Without this an HRBP — who holds
# INVITE_USERS but NOT the Admin-only MANAGE_USERS_ROLES — could mint a full ADMIN
# account via the invite flow, bypassing the Admin-only user/role-management gate.
_ROLE_RANK = {
    User.Role.EMPLOYEE: 0,
    User.Role.MANAGER: 1,
    User.Role.HRBP: 2,
    User.Role.ADMIN: 3,
}


def _invite_token(invitation: Invitation) -> str:
    return signing.dumps({"inv": str(invitation.id)}, salt=_INVITE_SALT)


def _invite_url(invitation: Invitation) -> str:
    return f"{settings.PUBLIC_APP_URL.rstrip('/')}/accept-invite?token={_invite_token(invitation)}"


def _load_pending(token: str) -> Invitation | None:
    """Resolve a signed token → the PENDING invitation row, or None. The row is
    fetched by its unguessable UUID via a raw queryset (bootstrap pattern — the
    caller is unauthenticated, so no tenant is bound); status is re-checked so a
    REVOKED invite is dead even if the link was already delivered."""
    try:
        payload = signing.loads(token, salt=_INVITE_SALT, max_age=_INVITE_MAX_AGE)
    except signing.BadSignature:
        return None
    row = (
        dj_models.QuerySet(Invitation)
        .filter(id=payload.get("inv"), deleted_at__isnull=True)
        .select_related("tenant", "manager")
        .first()
    )
    if row is None or row.status != Invitation.Status.PENDING:
        return None
    return row


def _send_invite_email(request, invitation: Invitation, url: str) -> bool:
    """Best-effort invite email; the link is always returned to the inviter."""
    return send_templated_email(
        "invitation",
        to=invitation.email,
        subject=f"You're invited to {request.user.tenant.name} on {settings.APP_NAME}",
        context={
            "inviter": request.user.display,
            "tenant_name": request.user.tenant.name,
            "role": invitation.get_role_display(),
            "url": url,
        },
    )


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=User.Role.choices, default=User.Role.EMPLOYEE)
    manager = serializers.UUIDField(required=False, allow_null=True)


class InvitationAdminView(RBACMixin, APIView):
    """``GET, POST /api/admin/invitations`` (INVITE_USERS — HRBP+)."""

    required_capability = Capability.INVITE_USERS

    def get(self, request):
        rows = Invitation.objects.order_by("-created_at")[:100]
        return Response([
            {
                "id": str(i.id), "email": i.email, "role": i.role, "status": i.status,
                "invited_by": str(i.invited_by_id), "created_at": i.created_at,
                "invite_url": _invite_url(i) if i.status == Invitation.Status.PENDING else None,
            }
            for i in rows
        ])

    def post(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Role ceiling — an inviter may never grant a role above their own. INVITE_USERS
        # is HRBP+, but ADMIN role assignment is an Admin-only power (MANAGE_USERS_ROLES);
        # without this an HRBP could self-issue an ADMIN account through the invite flow.
        if _ROLE_RANK.get(data["role"], 0) > _ROLE_RANK.get(request.user.role, 0):
            return Response(
                {"role": ["You can't invite someone at a higher role than your own."]},
                status=status.HTTP_403_FORBIDDEN,
            )
        email = User.objects.normalize_email(data["email"])
        if User.objects.filter(email=email).exists():
            return Response({"email": ["A user with this email already exists."]}, status=422)
        if Invitation.objects.filter(email=email, status=Invitation.Status.PENDING).exists():
            return Response({"email": ["A pending invitation already exists for this email."]}, status=422)
        manager = None
        if data.get("manager"):
            manager = User.objects.filter(pk=data["manager"]).first()  # tenant-scoped
            if manager is None:
                return Response({"manager": ["Unknown manager."]}, status=422)
        invitation = Invitation.objects.create(
            tenant_id=request.user.tenant_id,
            email=email,
            role=data["role"],
            manager=manager,
            invited_by=request.user,
        )
        record(
            action="admin.user_invited", actor=request.user, target_type="invitation",
            target_id=invitation.id, metadata={"email": email, "role": data["role"]},
            tenant=request.user.tenant_id,
        )
        url = _invite_url(invitation)
        emailed = _send_invite_email(request, invitation, url)
        return Response(
            {"id": str(invitation.id), "email": email, "role": invitation.role,
             "status": invitation.status, "invite_url": url, "emailed": emailed},
            status=status.HTTP_201_CREATED,
        )


class InvitationRevokeView(RBACMixin, APIView):
    """``POST /api/admin/invitations/<pk>/revoke`` (INVITE_USERS — HRBP+)."""

    required_capability = Capability.INVITE_USERS

    def post(self, request, pk):
        invitation = Invitation.objects.filter(pk=pk).first()
        if invitation is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if invitation.status == Invitation.Status.PENDING:
            invitation.status = Invitation.Status.REVOKED
            invitation.save(update_fields=["status"])
            record(
                action="admin.invitation_revoked", actor=request.user,
                target_type="invitation", target_id=invitation.id,
                metadata={"email": invitation.email}, tenant=request.user.tenant_id,
            )
        return Response({"ok": True, "status": invitation.status})


class InvitationResendView(RBACMixin, APIView):
    """``POST /api/admin/invitations/<pk>/resend`` (INVITE_USERS — HRBP+).

    Re-sends the invite email with a FRESHLY signed link (a new 7-day window —
    the signature timestamp is the expiry clock) and returns the new URL for
    copy-paste. Only a PENDING invite can be resent; anything else is a 409 so
    a revoked/accepted invite can never be revived."""

    required_capability = Capability.INVITE_USERS

    def post(self, request, pk):
        invitation = Invitation.objects.filter(pk=pk).first()
        if invitation is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if invitation.status != Invitation.Status.PENDING:
            return Response(
                {"detail": f"Only a pending invitation can be resent (status: {invitation.status})."},
                status=status.HTTP_409_CONFLICT,
            )
        url = _invite_url(invitation)
        emailed = _send_invite_email(request, invitation, url)
        record(
            action="admin.invitation_resent", actor=request.user,
            target_type="invitation", target_id=invitation.id,
            metadata={"email": invitation.email, "emailed": emailed},
            tenant=request.user.tenant_id,
        )
        return Response(
            {"id": str(invitation.id), "email": invitation.email,
             "status": invitation.status, "invite_url": url, "emailed": emailed}
        )


class InvitationDetailView(APIView):
    """``GET /api/auth/invitations/<token>`` — public: what the invitee is joining
    (email/tenant/role) IF the link is valid+pending; else a generic 404."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AtomicAnonThrottle]

    def get(self, request, token):
        row = _load_pending(token)
        if row is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({"email": row.email, "tenant_name": row.tenant.name, "role": row.role})


class InvitationAcceptView(APIView):
    """``POST /api/auth/invitations/<token>/accept`` {display_name?, password} —
    creates the user IN THE INVITE'S TENANT with the invite's role/manager. Seats
    enforced here (409 when the tenant is full). Single-use: the row flips to
    ACCEPTED atomically-enough that a duplicate create 409s on the unique email."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AtomicAnonThrottle]

    def post(self, request, token):
        row = _load_pending(token)
        if row is None:
            return Response(
                {"detail": "This invitation is invalid, expired or revoked."},
                status=status.HTTP_404_NOT_FOUND,
            )
        password = str(request.data.get("password") or "")
        display_name = str(request.data.get("display_name") or "").strip() or None
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response({"password": exc.messages}, status=400)

        with tenant_context(row.tenant):
            # Headcount enforcement (server-side, at join time): seats AND the
            # plan's employee limit (PHASE2 L1.4).
            from apps.billing.services import can_add_user

            allowed, reason = can_add_user(row.tenant_id)
            if not allowed:
                return Response({"detail": reason}, status=status.HTTP_409_CONFLICT)
            try:
                user = User.objects.create_user(
                    row.email,
                    password=password,
                    tenant=row.tenant,
                    role=row.role,
                    manager=row.manager,
                    display_name=display_name,
                )
            except IntegrityError:
                return Response(
                    {"detail": "An account with this email already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            row.status = Invitation.Status.ACCEPTED
            row.accepted_at = timezone.now()
            row.save(update_fields=["status", "accepted_at"])
            record(
                action="auth.invitation_accepted", actor=user, target_type="invitation",
                target_id=row.id, metadata={"role": row.role}, tenant=row.tenant_id,
            )
        return Response(
            {"ok": True, "email": row.email, "tenant_slug": row.tenant.slug},
            status=status.HTTP_201_CREATED,
        )
