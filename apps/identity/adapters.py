"""
OIDC -> tenant-user mapping (django-allauth).

The IdP authenticates; it never provisions accounts (``is_open_for_signup`` is
False). On a social login we resolve the target tenant (from an explicit
``?tenant=<slug>`` hint, a session hint, or the configured default slug), then
bind the verified identity to an existing active user in that tenant — denying
with 403 if no such user exists. This keeps OIDC inside the tenant boundary.
"""
import logging

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import JsonResponse

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from .models import User

logger = logging.getLogger("pms.identity")


def _deny(message):
    raise ImmediateHttpResponse(JsonResponse({"detail": message}, status=403))


class TenantSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        # IdP-driven self-signup is disabled: admins provision users, the IdP
        # only authenticates them.
        return False

    def pre_social_login(self, request, sociallogin):
        # Always resolve+map (idempotent for returning users). We don't short-
        # circuit on sociallogin.is_existing because UUID pks are assigned before
        # save, which makes that flag unreliable for this user model.
        email = (
            getattr(sociallogin.user, "email", "")
            or sociallogin.account.extra_data.get("email", "")
            or ""
        ).strip().lower()
        tenant = self.resolve_tenant(request, sociallogin)
        if not email or tenant is None:
            _deny("OIDC identity could not be mapped to a tenant.")

        with tenant_context(tenant):
            user = User.objects.filter(email=email, is_active=True).first()
        if user is None:
            _deny("No active user for this identity in the resolved tenant.")

        # Connect the verified identity to the existing tenant user rather than
        # creating a brand-new account.
        sociallogin.user = user
        sociallogin.state["process"] = "connect"

    def resolve_tenant(self, request, sociallogin):
        slug = None
        if request is not None:
            slug = request.GET.get("tenant")
            if not slug and hasattr(request, "session"):
                slug = request.session.get("oidc_tenant_slug")
        if not slug:
            slug = getattr(settings, "OIDC_DEFAULT_TENANT_SLUG", "") or None
        if not slug:
            return None
        return Tenant.objects.filter(slug=slug, status=Tenant.Status.ACTIVE).first()
