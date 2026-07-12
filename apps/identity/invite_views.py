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
from django.core.mail import send_mail
from django.db import IntegrityError, models as dj_models
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.throttling import AtomicAnonThrottle
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin
from apps.tenancy.context import tenant_context

from .models import Invitation, User

logger = logging.getLogger("pms.identity")

_INVITE_SALT = "pms.invite"
_INVITE_MAX_AGE = 7 * 24 * 3600  # 7 days


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
        try:
            send_mail(
                subject=f"You're invited to {request.user.tenant.name} on TalbotIQ PMS",
                message=(
                    f"{request.user.display} invited you to join {request.user.tenant.name} "
                    f"as {invitation.get_role_display()}.\n\nAccept here: {url}\n\n"
                    "The link expires in 7 days."
                ),
                from_email=None,
                recipient_list=[email],
            )
            emailed = True
        except Exception:  # noqa: BLE001 — email is best-effort; the link is returned
            logger.exception("invitation email send failed")
            emailed = False
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
            # Seat enforcement (server-side, at join time).
            from apps.billing.services import get_or_create_entitlement

            entitlement = get_or_create_entitlement(row.tenant_id)
            active = User.objects.filter(is_active=True).count()
            if active >= entitlement.seat_count:
                return Response(
                    {"detail": "No seats available — ask your admin to add seats."},
                    status=status.HTTP_409_CONFLICT,
                )
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
