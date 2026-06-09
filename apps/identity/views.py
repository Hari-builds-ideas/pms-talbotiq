import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

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
)
from .services import establish_session
from .tokens import issue_tokens_for_user

logger = logging.getLogger("pms.identity")


class LoginView(APIView):
    """Step 1 of login. Validates tenant-scoped credentials. If MFA is enabled,
    returns an mfa_required marker + short-lived MFA token instead of issuing
    JWTs (the caller then hits /mfa/challenge). 401 on bad credentials."""

    permission_classes = [AllowAny]
    authentication_classes = []

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


class MeView(APIView):
    """The caller's own identity — proves end-to-end JWT auth + tenant scoping."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response(
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "tenant_id": str(u.tenant_id),
                "mfa_enabled": u.mfa_enabled,
                "manager_id": str(u.manager_id) if u.manager_id else None,
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
