import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from apps.core.throttling import AtomicAnonThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import record
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from .exceptions import InvalidCredentials
from .mfa import (
    base32_secret,
    confirmed_device,
    make_mfa_token,
    rotate_unconfirmed_device,
    unconfirmed_device,
)
from .models import User
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    MfaChallengeSerializer,
    MfaCodeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from apps.rbac.matrix import capabilities_for_role

from .services import establish_session
from .tokens import issue_tokens_for_user

logger = logging.getLogger("pms.identity")


class LoginView(APIView):
    """Step 1 of login. Validates tenant-scoped credentials. If MFA is enabled,
    returns an mfa_required marker + short-lived MFA token instead of issuing
    JWTs (the caller then hits /mfa/challenge). 401 on bad credentials."""

    permission_classes = [AllowAny]
    authentication_classes = []
    # IP-throttle the unauthenticated login surface via the "anon" scope: the
    # global Tenant/User throttles no-op for anonymous callers, so this view
    # needs its own anon throttle to cap credential-stuffing bursts.
    throttle_classes = [AtomicAnonThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        if user.mfa_enabled:
            return Response({"mfa_required": True, "mfa_token": make_mfa_token(user)})

        access, refresh = issue_tokens_for_user(user)
        establish_session(request, user)
        return Response({"mfa_required": False, "access": access, "refresh": refresh})


class MfaChallengeView(APIView):
    """Step 2 of login (only when MFA is enabled). Verifies the TOTP code and
    issues the tenant-scoped JWTs."""

    permission_classes = [AllowAny]
    authentication_classes = []
    # Same IP-based anon throttle as LoginView: this is the other half of the
    # unauthenticated auth surface, so cap MFA-code guessing bursts per IP.
    throttle_classes = [AtomicAnonThrottle]

    def post(self, request):
        serializer = MfaChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        device = confirmed_device(user)
        if device is None or not device.verify_token(serializer.validated_data["code"]):
            raise InvalidCredentials("Invalid MFA code.", "mfa_invalid")

        access, refresh = issue_tokens_for_user(user)
        establish_session(request, user)
        return Response({"access": access, "refresh": refresh})


class MfaEnrollView(APIView):
    """Begin TOTP enrollment for the authenticated user. Returns the shared
    secret + provisioning URI; the device stays unconfirmed until /mfa/enroll/
    confirm succeeds."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        device = rotate_unconfirmed_device(request.user)
        return Response({"secret": base32_secret(device), "config_url": device.config_url})


class MfaEnrollConfirmView(APIView):
    """Confirm enrollment with a current TOTP code; flips mfa_enabled on."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device = unconfirmed_device(request.user)
        if device is None:
            return Response(
                {"detail": "No pending MFA enrollment. Call enroll first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not device.verify_token(serializer.validated_data["code"]):
            return Response(
                {"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST
            )

        device.confirmed = True
        device.save(update_fields=["confirmed"])

        user = request.user
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled", "updated_at"])
        return Response({"mfa_enabled": True})


class LogoutView(APIView):
    """Blacklist the refresh token and drop the server-side session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.session.flush()
        return Response(status=status.HTTP_205_RESET_CONTENT)


class PasswordResetRequestView(APIView):
    """``POST /api/auth/password-reset`` — self-service reset, step 1.

    ALWAYS answers 200 ``{"ok": true}`` (no account enumeration — same posture as
    login's uniform 401). When tenant + email resolve to an active local account,
    a single-use, time-limited link (Django's ``PasswordResetTokenGenerator``) is
    emailed; the email send is best-effort and never changes the response.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AtomicAnonThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenant = Tenant.objects.filter(
            slug=data["tenant_slug"], status=Tenant.Status.ACTIVE
        ).first()
        if tenant is not None:
            email = User.objects.normalize_email(data["email"])
            with tenant_context(tenant):
                user = User.objects.filter(email=email, is_active=True).first()
            if user is not None:
                self._send_reset_email(user, tenant)
        return Response({"ok": True})

    @staticmethod
    def _send_reset_email(user, tenant):
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        link = (
            f"{settings.PUBLIC_APP_URL.rstrip('/')}/reset-password"
            f"?tenant={tenant.slug}&uid={uid}&token={token}"
        )
        try:
            send_mail(
                subject="Reset your TalbotIQ PMS password",
                message=(
                    f"A password reset was requested for your {tenant.name} account.\n\n"
                    f"Reset it here: {link}\n\n"
                    "The link is single-use and expires. If you didn't request this, "
                    "ignore this email — your password is unchanged."
                ),
                from_email=None,  # DEFAULT_FROM_EMAIL
                recipient_list=[user.email],
            )
        except Exception:  # noqa: BLE001 — a mail outage must not 500 (or leak existence)
            logger.exception("password-reset email send failed")


class PasswordResetConfirmView(APIView):
    """``POST /api/auth/password-reset/confirm`` — self-service reset, step 2.

    Validates the uid+token pair, runs the configured password validators, sets
    the password (audited), and REVOKES every outstanding refresh token for the
    user — a reset kills any stolen session. Every failure mode returns the same
    generic 400 (no oracle for which part was wrong).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AtomicAnonThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        generic = Response(
            {"detail": "Invalid or expired reset link."}, status=status.HTTP_400_BAD_REQUEST
        )
        tenant = Tenant.objects.filter(
            slug=data["tenant_slug"], status=Tenant.Status.ACTIVE
        ).first()
        if tenant is None:
            return generic
        try:
            uid = force_str(urlsafe_base64_decode(data["uid"]))
            with tenant_context(tenant):
                user = User.objects.filter(pk=uid, is_active=True).first()
        except (ValueError, DjangoValidationError):
            return generic
        if user is None or not default_token_generator.check_token(user, data["token"]):
            return generic
        try:
            validate_password(data["new_password"], user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        # Audit BEFORE the write (append-only trail; metadata carries no secrets).
        record(
            action="auth.password_reset",
            actor=user,
            target_type="user",
            target_id=user.id,
            metadata={"via": "self_service_reset"},
            tenant=user.tenant_id,
        )
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        # Token-generator invalidation is inherent (it hashes the password), and
        # every outstanding refresh token is blacklisted: a reset ends all sessions.
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        return Response({"ok": True})


class MeView(APIView):
    """The caller's own identity — proves end-to-end JWT auth + tenant scoping."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response(
            {
                "id": str(u.id),
                "email": u.email,
                "display_name": u.display_name,   # raw (may be null) — for editing
                "display": u.display,             # effective name (falls back to email)
                "role": u.role,
                "tenant_id": str(u.tenant_id),
                # The tenant's own identity — so the shell shows the REAL tenant
                # (not a hardcoded name) and a demo can switch between acme/globex.
                "tenant_name": u.tenant.name,
                "tenant_slug": u.tenant.slug,
                "mfa_enabled": u.mfa_enabled,
                "manager_id": str(u.manager_id) if u.manager_id else None,
                # The caller's capability grants, from the SAME matrix the server
                # enforces (apps/rbac/matrix.py) — the client's single source of
                # truth for hiding controls a role can't use (FINAL D2).
                "capabilities": capabilities_for_role(u.role),
            }
        )


class OidcCompleteView(APIView):
    """Landing endpoint after a successful OIDC/allauth login. The identity has
    been verified and mapped to a tenant user (see adapters.py) and logged into a
    Django session; here we mint the tenant-scoped JWTs for the SPA to use."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        uid = request.session.get("_auth_user_id")
        if not uid:
            return Response(
                {"detail": "No authenticated session."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            user = User.objects.get_by_natural_id_unscoped(uid)
        except User.DoesNotExist:
            return Response(
                {"detail": "Session user not found."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        access, refresh = issue_tokens_for_user(user)
        establish_session(request, user)
        return Response(
            {
                "access": access,
                "refresh": refresh,
                "tenant_id": str(user.tenant_id),
                "role": user.role,
            }
        )
