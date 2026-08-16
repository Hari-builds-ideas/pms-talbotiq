"""
PROD_B — self-serve new-organization signup (PUBLIC, hardened).

A brand-new company arrives at the app, creates its workspace (a new TENANT),
becomes that tenant's first ADMIN, and is logged straight in. Everything is
tenant-isolated from the first row: the Tenant row is created first, then every
other write happens inside ``tenant_context`` through the scoped managers, so a
new tenant can NEVER see or touch another tenant's data.

Hardening: public endpoint → IP-throttled (``AtomicAnonThrottle``), hard input
validation, password run through Django's validators, unique-slug handling, and
role is forced to ADMIN server-side (never trusted from the client). A best-effort
verification/welcome email is sent; the account is usable immediately (the common
SaaS "you're in, verify later" pattern — see docs/CUSTOMER_ONBOARDING.md).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.throttling import AtomicAnonThrottle
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from . import security
from .models import LoginEvent, User
from .services import establish_session
from .tokens import issue_tokens_for_user

logger = logging.getLogger("pms.identity")

#: Reserved slugs that must never become a tenant workspace (collide with routes
#: or are confusing). A signup asking for one falls through to a suffixed slug.
_RESERVED_SLUGS = {"api", "admin", "www", "app", "auth", "accounts", "static",
                   "media", "healthz", "readyz", "metrics", "acme", "globex"}


class SignupSerializer(serializers.Serializer):
    org_name = serializers.CharField(max_length=255, trim_whitespace=True)
    display_name = serializers.CharField(max_length=255, trim_whitespace=True)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)
    # Optional explicit workspace slug; otherwise derived from org_name.
    workspace_slug = serializers.SlugField(max_length=64, required=False, allow_blank=True)

    def validate_org_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Enter your organization name.")
        return value.strip()

    def validate_display_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Enter your name.")
        return value.strip()

    def validate_password(self, value):
        # Same validators as the invite-accept + reset flows (AUTH_PASSWORD_VALIDATORS).
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


def _unique_slug(preferred: str) -> str | None:
    """Slugify ``preferred`` and make it globally unique among tenants. Returns
    None if nothing usable can be derived (e.g. an all-symbol org name)."""
    base = slugify(preferred)[:56]  # leave room for a numeric suffix
    if not base:
        return None
    candidate = base
    if candidate in _RESERVED_SLUGS or Tenant.objects.filter(slug=candidate).exists():
        for n in range(2, 1000):
            candidate = f"{base}-{n}"
            if candidate not in _RESERVED_SLUGS and not Tenant.objects.filter(slug=candidate).exists():
                break
        else:
            return None
    return candidate


def _send_welcome_email(admin: User, tenant: Tenant) -> bool:
    """Best-effort welcome / verify-your-email. Never blocks signup."""
    try:
        login_url = f"{settings.PUBLIC_APP_URL.rstrip('/')}/login"
        send_mail(
            subject=f"Welcome to {settings.APP_NAME} — your workspace is ready",
            message=(
                f"Hi {admin.display},\n\n"
                f"Your {settings.APP_NAME} workspace \"{tenant.name}\" is ready.\n"
                f"Workspace ID: {tenant.slug}\n\n"
                f"Sign in any time at {login_url} using this workspace ID and your email.\n\n"
                "You can now invite your team or bulk-import employees from Admin → Users.\n"
            ),
            from_email=None,
            recipient_list=[admin.email],
        )
        return True
    except Exception:  # noqa: BLE001 — email is best-effort; signup already succeeded
        logger.exception("signup welcome email send failed")
        return False


class PublicConfigView(APIView):
    """``GET /api/auth/public-config`` (PUBLIC) — the handful of facts the SPA
    needs BEFORE anyone is signed in.

    Served from the server rather than baked in at build time so flipping
    ``SIGNUP_MODE`` takes effect on reload instead of requiring a rebuild and
    redeploy of the frontend — which is the difference between "one env var" and
    "one env var and a release".

    Deliberately tiny, and deliberately contains nothing that is not already
    visible to an anonymous visitor: whether signup is open, who to contact, and
    which SSO buttons to render. No tenant data, no version, no build info.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AtomicAnonThrottle]

    def get(self, request):
        return Response({
            "signup_open": getattr(settings, "SIGNUP_MODE", "invite_only") == "open",
            "support_email": getattr(settings, "SUPPORT_EMAIL", "") or None,
            "google_sso": bool(getattr(settings, "GOOGLE_SSO_ENABLED", False)),
            "app_name": getattr(settings, "APP_NAME", "Axiom"),
        })


class SignupView(APIView):
    """``POST /api/auth/signup`` (PUBLIC) — create a workspace + first admin and
    log them in. Body: ``{org_name, display_name, email, password, workspace_slug?}``.
    Returns ``{access, refresh, tenant_slug}`` (201)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AtomicAnonThrottle]

    def post(self, request):
        # C7 — self-serve signup is CLOSED by default.
        #
        # Anyone signing up today gets a real workspace on a real plan that no
        # invoice will ever follow, because checkout cannot take money yet (C8).
        # A product that hands out accounts it cannot bill is not "growing", it is
        # accumulating support obligations. The invitation flow is unaffected:
        # existing customers still onboard their own people.
        #
        # One env var flips it back the moment billing works.
        if getattr(settings, "SIGNUP_MODE", "invite_only") != "open":
            return Response(
                {
                    "detail": (
                        "New workspaces are by invitation at the moment. Get in "
                        "touch and we'll set you up."
                    ),
                    "code": "signup_invite_only",
                    "support_email": getattr(settings, "SUPPORT_EMAIL", "") or None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        slug = _unique_slug(data.get("workspace_slug") or data["org_name"])
        if slug is None:
            return Response(
                {"workspace_slug": ["Couldn't derive a workspace ID from that name — "
                                    "pick a workspace ID with letters or numbers."]},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        email = User.objects.normalize_email(data["email"])

        # Tenant is the scope boundary itself (not tenant-scoped) — create it first.
        tenant = Tenant.objects.create(
            name=data["org_name"], slug=slug, status=Tenant.Status.ACTIVE
        )
        # Everything else is scoped: bind the new tenant, then all writes go
        # through the fail-closed managers — cross-tenant leakage is impossible.
        with tenant_context(tenant.id):
            admin = User.objects.create_user(
                email=email,
                password=data["password"],
                tenant=tenant,
                role=User.Role.ADMIN,  # forced server-side; never from the client
                display_name=data["display_name"],
            )
            # Provision a default plan (Starter) + seats so entitlements resolve.
            from apps.billing.services import (
                get_or_create_entitlement,
                get_or_create_subscription,
                set_seats,
            )

            get_or_create_entitlement(tenant.id)
            set_seats(tenant, settings.SIGNUP_DEFAULT_SEATS, actor=admin)
            get_or_create_subscription(tenant)  # STARTER / ACTIVE by default
            record(
                action="tenant.signed_up", actor=admin, target_type="tenant",
                target_id=tenant.id,
                metadata={"slug": slug, "org_name": tenant.name},
                tenant=tenant.id,
            )

        emailed = _send_welcome_email(admin, tenant)

        # Log them straight in (device session + tenant-scoped JWTs), exactly like
        # a successful password login.
        session = security.start_device_session(request, admin)
        access, refresh = issue_tokens_for_user(admin, device_id=session.id)
        establish_session(request, admin)
        security.log_event(
            tenant_id=admin.tenant_id, email=admin.email,
            event=LoginEvent.Event.LOGIN_OK, user=admin, request=request,
        )
        logger.info("new tenant signed up: slug=%s", slug)
        return Response(
            {"access": access, "refresh": refresh, "tenant_slug": slug,
             "workspace_name": tenant.name, "emailed": emailed},
            status=status.HTTP_201_CREATED,
        )
