"""
PHASE2 L1.1 — the self-service profile & account-security surface.

Everything here is SELF-scoped (`request.user`) except the avatar read, which is
scope-checked with the same `actor_can_access` rule as every other person-read.
Org-controlled fields (title/department/employee_id) are edited by Admin via
`apps/administration`, not here.
"""
from __future__ import annotations

import logging
import uuid
import zoneinfo

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.utils import timezone as dj_timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.audit.services import record
from apps.core.mail import send_templated_email
from apps.rbac.scope import actor_can_access

from . import security
from .models import DeviceSession, LoginEvent, User
from .tokens import issue_tokens_for_user

logger = logging.getLogger("pms.identity")

_EMAIL_CHANGE_SALT = "pms.email-change"
_EMAIL_CHANGE_MAX_AGE = 3600  # 1h single-purpose token

#: Accepted avatar types by MAGIC BYTES (never trust the client content-type).
_IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),          # JPEG
    (b"\x89PNG\r\n\x1a\n", ".png"),    # PNG
    (b"RIFF", ".webp"),                 # WebP (RIFF....WEBP — checked below)
)
_MAX_PHOTO_BYTES = 2 * 1024 * 1024  # 2 MB


def _sniff_image(head: bytes) -> str | None:
    """Return the canonical extension when ``head`` starts like a real image."""
    for sig, ext in _IMAGE_SIGNATURES:
        if head.startswith(sig):
            if ext == ".webp" and head[8:12] != b"WEBP":
                continue
            return ext
    return None


class ProfileSerializer(serializers.ModelSerializer):
    """The caller's own profile (read shape)."""

    has_photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "display_name", "display", "role", "manager_id",
            "phone", "title", "department", "employee_id", "timezone", "language",
            "preferences", "mfa_enabled", "has_photo",
        ]
        read_only_fields = fields

    def get_has_photo(self, obj) -> bool:
        return bool(obj.photo)


class ProfileUpdateSerializer(serializers.Serializer):
    """SELF-editable fields only. Org-controlled fields (title/department/
    employee_id) and identity fields (email/role) are NOT accepted here."""

    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64, required=False)
    language = serializers.CharField(max_length=16, required=False)
    preferences = serializers.JSONField(required=False)

    def validate_timezone(self, value):
        try:
            zoneinfo.ZoneInfo(value)
        except Exception:
            raise serializers.ValidationError("Unknown timezone.")
        return value

    def validate_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Preferences must be an object.")
        return value


class ProfileView(APIView):
    """``GET/PATCH /api/auth/profile`` — the caller's own profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        changed = []
        for field, value in serializer.validated_data.items():
            if field == "display_name":
                value = value.strip() or None
            setattr(user, field, value)
            changed.append(field)
        if changed:
            record(
                action="profile.updated", actor=user, target_type="user",
                target_id=user.id, metadata={"fields": sorted(changed)},
                tenant=user.tenant_id,
            )
            user.save(update_fields=changed)
        return Response(ProfileSerializer(user).data)


class ProfilePhotoView(APIView):
    """``PUT/DELETE /api/auth/profile/photo`` — upload (multipart ``photo``) or
    remove the caller's avatar. Magic-byte + size validation; stored under
    MEDIA_ROOT/avatars/, tenant-prefixed filename; never static-served."""

    permission_classes = [IsAuthenticated]

    def put(self, request):
        upload = request.FILES.get("photo")
        if upload is None:
            return Response({"photo": ["This field is required."]}, status=400)
        if upload.size > _MAX_PHOTO_BYTES:
            return Response({"photo": ["Max size is 2 MB."]}, status=400)
        head = upload.read(16)
        upload.seek(0)
        ext = _sniff_image(head)
        if ext is None:
            return Response({"photo": ["Only JPEG, PNG or WebP images are accepted."]}, status=400)
        user = request.user
        if user.photo:
            user.photo.delete(save=False)
        # Random, tenant-prefixed name — never the client filename.
        user.photo.save(f"{user.tenant_id}/{uuid.uuid4().hex}{ext}", upload, save=False)
        record(
            action="profile.photo_updated", actor=user, target_type="user",
            target_id=user.id, metadata={}, tenant=user.tenant_id,
        )
        user.save(update_fields=["photo"])
        return Response({"ok": True})

    def delete(self, request):
        user = request.user
        if user.photo:
            user.photo.delete(save=False)
            user.photo = None
            user.save(update_fields=["photo"])
        return Response({"ok": True})


class UserPhotoView(APIView):
    """``GET /api/auth/users/<pk>/photo`` — stream a user's avatar, gated by the
    SAME data-scope rule as any person-read (`actor_can_access`); out-of-scope or
    missing → 404 (no existence leak)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        subject = User.objects.filter(pk=pk).first()  # tenant-scoped
        if subject is None or not actor_can_access(request.user, subject) or not subject.photo:
            raise Http404
        try:
            return FileResponse(subject.photo.open("rb"), content_type="application/octet-stream")
        except FileNotFoundError:
            raise Http404


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordChangeView(APIView):
    """``POST /api/auth/password-change`` — authenticated change. Verifies the
    current password, runs the validators, then REVOKES every other session
    (device sessions + outstanding refresh tokens) and returns a fresh token
    pair for THIS device — a stolen session dies with the old password."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"current_password": ["Incorrect password."]}, status=400)
        try:
            validate_password(serializer.validated_data["new_password"], user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": exc.messages}, status=400)
        record(
            action="auth.password_changed", actor=user, target_type="user",
            target_id=user.id, metadata={}, tenant=user.tenant_id,
        )
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        security.log_event(
            tenant_id=user.tenant_id, email=user.email,
            event=LoginEvent.Event.PASSWORD_CHANGED, user=user, request=request,
        )
        # Kill everything else: all refresh tokens + all device sessions…
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        DeviceSession.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=dj_timezone.now()
        )
        # …then hand THIS device a fresh session + pair.
        session = security.start_device_session(request, user)
        access, refresh = issue_tokens_for_user(user, device_id=session.id)
        return Response({"ok": True, "access": access, "refresh": refresh})


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)


class EmailChangeRequestView(APIView):
    """``POST /api/auth/email-change`` — step 1: verify the password, mail a
    single-use confirm link to the NEW address. The address only changes after
    the link is confirmed (proves control of the new mailbox)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"current_password": ["Incorrect password."]}, status=400)
        new_email = User.objects.normalize_email(serializer.validated_data["new_email"])
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return Response({"new_email": ["That email is already in use."]}, status=400)
        token = signing.dumps(
            {"uid": str(user.pk), "tid": str(user.tenant_id), "new_email": new_email},
            salt=_EMAIL_CHANGE_SALT,
        )
        link = f"{settings.PUBLIC_APP_URL.rstrip('/')}/settings?email_change_token={token}"
        send_templated_email(
            "email_change",
            to=new_email,
            subject=f"Confirm your new {settings.APP_NAME} email address",
            context={"new_email": new_email, "url": link},
        )
        return Response({"ok": True})


class EmailChangeConfirmView(APIView):
    """``POST /api/auth/email-change/confirm`` — step 2: apply the change from the
    signed token (must belong to the CALLING user)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = str(request.data.get("token") or "")
        try:
            payload = signing.loads(token, salt=_EMAIL_CHANGE_SALT, max_age=_EMAIL_CHANGE_MAX_AGE)
        except signing.BadSignature:
            return Response({"detail": "Invalid or expired confirmation link."}, status=400)
        user = request.user
        if payload.get("uid") != str(user.pk) or payload.get("tid") != str(user.tenant_id):
            return Response({"detail": "Invalid or expired confirmation link."}, status=400)
        new_email = payload["new_email"]
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return Response({"new_email": ["That email is already in use."]}, status=400)
        record(
            action="auth.email_changed", actor=user, target_type="user",
            target_id=user.id, metadata={"from": user.email, "to": new_email},
            tenant=user.tenant_id,
        )
        user.email = new_email
        user.save(update_fields=["email"])
        return Response({"ok": True, "email": new_email})


class MfaDisableView(APIView):
    """``POST /api/auth/mfa/disable`` — turn TOTP off (password-confirmed, audited)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.check_password(str(request.data.get("current_password") or "")):
            return Response({"current_password": ["Incorrect password."]}, status=400)
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.filter(user=user).delete()
        if user.mfa_enabled:
            record(
                action="auth.mfa_disabled", actor=user, target_type="user",
                target_id=user.id, metadata={}, tenant=user.tenant_id,
            )
            user.mfa_enabled = False
            user.save(update_fields=["mfa_enabled"])
        return Response({"ok": True})


class MyActivityView(APIView):
    """``GET /api/auth/my-activity`` — the caller's recent audited actions (their
    own slice of the append-only audit log; tenant-scoped, self-only)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.audit.models import AuditLog

        rows = (
            AuditLog.objects.filter(actor=request.user, tenant=request.user.tenant_id)
            .order_by("-created_at")[:50]
        )
        return Response([
            {
                "action": r.action,
                "target_type": r.target_type,
                "target_id": str(r.target_id) if r.target_id else None,
                "created_at": r.created_at,
            }
            for r in rows
        ])
