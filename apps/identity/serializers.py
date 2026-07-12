from django.core import signing
from rest_framework import serializers

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from .exceptions import InvalidCredentials
from .mfa import read_mfa_token
from .models import User


class LoginSerializer(serializers.Serializer):
    """Tenant-qualified local login. Email is unique per tenant, so the tenant
    must be identified (slug) to disambiguate. All failure modes return the same
    401 to avoid leaking which of tenant/email/password was wrong."""

    tenant_slug = serializers.SlugField()
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    def validate(self, attrs):
        try:
            tenant = Tenant.objects.get(slug=attrs["tenant_slug"])
        except Tenant.DoesNotExist:
            raise InvalidCredentials()
        if tenant.status != Tenant.Status.ACTIVE:
            raise InvalidCredentials("Tenant is not active.", "tenant_inactive")

        email = User.objects.normalize_email(attrs["email"])
        with tenant_context(tenant):
            user = User.objects.filter(email=email).first()

        if user is None or not user.is_active or not user.check_password(attrs["password"]):
            raise InvalidCredentials()

        attrs["user"] = user
        attrs["tenant"] = tenant
        return attrs


class MfaChallengeSerializer(serializers.Serializer):
    """Second login step: validates the signed MFA token and loads the pending
    user within that user's tenant context."""

    mfa_token = serializers.CharField()
    code = serializers.CharField()

    def validate(self, attrs):
        try:
            payload = read_mfa_token(attrs["mfa_token"])
        except signing.SignatureExpired:
            raise InvalidCredentials("MFA session expired.", "mfa_expired")
        except signing.BadSignature:
            raise InvalidCredentials("Invalid MFA session.", "mfa_invalid")

        with tenant_context(payload["tid"]):
            user = User.objects.filter(id=payload["uid"]).first()

        if user is None or not user.is_active:
            raise InvalidCredentials("Invalid MFA session.", "mfa_invalid")

        attrs["user"] = user
        return attrs


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Self-service reset, step 1. Tenant-qualified like login (email is unique
    per tenant). The VIEW always answers 200 whether or not the account exists —
    no enumeration."""

    tenant_slug = serializers.SlugField()
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Self-service reset, step 2: the uid+token pair from the emailed link plus
    the new password (checked by the configured password validators in the view)."""

    tenant_slug = serializers.SlugField()
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
