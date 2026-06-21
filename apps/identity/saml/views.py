"""
SAML 2.0 SP endpoints, per tenant by slug:

* ``GET  /api/auth/saml/<slug>/metadata`` — SP metadata XML for the IdP admin.
* ``GET  /api/auth/saml/<slug>/login``    — SP-initiated AuthnRequest → redirect to IdP.
* ``POST /api/auth/saml/<slug>/acs``      — Assertion Consumer Service; validates the
                                            signed assertion, then mints our normal
                                            tenant-scoped JWT (SSO → our JWT model).

All three are unauthenticated (the user isn't logged in yet) and AllowAny; the
tenant is bound from the URL slug, and the SAML config is read inside that
tenant's context. No SessionAuthentication is used, so DRF applies no CSRF check
to the cross-site IdP POST.
"""
import logging

from django.http import HttpResponse, HttpResponseRedirect
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from ..models import SamlIdpConfig
from ..services import establish_session
from ..tokens import issue_tokens_for_user
from .service import SamlAuthError, process_saml_response
from .settings import build_saml_settings, prepare_django_request

logger = logging.getLogger("pms.identity")


def _resolve_tenant_and_config(tenant_slug):
    """(tenant, config) for an active tenant with SAML enabled, else (tenant?, None)."""
    tenant = Tenant.objects.filter(
        slug=tenant_slug, status=Tenant.Status.ACTIVE
    ).first()
    if tenant is None:
        return None, None
    with tenant_context(tenant):
        config = SamlIdpConfig.objects.filter(enabled=True).first()
    return tenant, config


class _SamlSpView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def _not_configured(self):
        return Response(
            {"detail": "SAML SSO is not configured for this tenant."},
            status=status.HTTP_404_NOT_FOUND,
        )


class SamlMetadataView(_SamlSpView):
    def get(self, request, tenant_slug):
        tenant, config = _resolve_tenant_and_config(tenant_slug)
        if config is None:
            return self._not_configured()
        settings = OneLogin_Saml2_Settings(
            build_saml_settings(config, request, tenant_slug), sp_validation_only=True
        )
        metadata = settings.get_sp_metadata()
        errors = settings.validate_metadata(metadata)
        if errors:
            logger.error("Invalid SP metadata for tenant %s: %s", tenant_slug, errors)
            return Response(
                {"detail": "Invalid SP metadata.", "errors": errors},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return HttpResponse(metadata, content_type="text/xml")


class SamlLoginView(_SamlSpView):
    """SP-initiated login: redirect the browser to the tenant's IdP with an AuthnRequest."""

    def get(self, request, tenant_slug):
        tenant, config = _resolve_tenant_and_config(tenant_slug)
        if config is None:
            return self._not_configured()
        auth = OneLogin_Saml2_Auth(
            prepare_django_request(request),
            old_settings=build_saml_settings(config, request, tenant_slug),
        )
        return HttpResponseRedirect(auth.login())


class SamlAcsView(_SamlSpView):
    """Assertion Consumer Service: validate the signed assertion → mint our JWT."""

    def post(self, request, tenant_slug):
        tenant, config = _resolve_tenant_and_config(tenant_slug)
        if config is None:
            return self._not_configured()
        try:
            user, role = process_saml_response(tenant, config, request)
        except SamlAuthError as exc:
            logger.warning("SAML ACS rejected for tenant %s: %s", tenant_slug, exc)
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        access, refresh = issue_tokens_for_user(user, role=role)
        establish_session(request, user)
        return Response(
            {
                "access": access,
                "refresh": refresh,
                "tenant_id": str(user.tenant_id),
                "role": role,
            }
        )
