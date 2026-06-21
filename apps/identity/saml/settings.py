"""
python3-saml settings + request adapters for our per-tenant SP.

The OneLogin settings dict is built per request from the tenant's
``SamlIdpConfig``. The SP entity-id and ACS URL are derived from the *live*
request (``build_absolute_uri``), so strict-mode Destination/Audience checks
always agree with the URL the IdP actually posted to — no hardcoded host. Any SP
private key is resolved from the env var *named* by the config's secret_ref; the
key bytes never live in the DB or the repo (see DECISIONS D25, docs/SSO.md).
"""
import os

from django.urls import reverse

# rsa-sha1 / sha1 are rejected; we require SHA-256 on both signature + digest.
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
NAMEID_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"


def resolve_sp_private_key(config) -> str:
    """Resolve the SP private key from the env var the config names, or "".

    Returns the PEM string only when the tenant configured a ``secret_ref`` AND
    that env var is set. Never reads a key from the DB or the filesystem.
    """
    ref = (config.sp_private_key_secret_ref or "").strip()
    if not ref:
        return ""
    return os.environ.get(ref, "") or ""


def sp_urls(request, tenant_slug):
    """(entity_id, acs_url) for this tenant's SP, from the live request."""
    entity_id = request.build_absolute_uri(
        reverse("identity:saml-metadata", args=[tenant_slug])
    )
    acs_url = request.build_absolute_uri(
        reverse("identity:saml-acs", args=[tenant_slug])
    )
    return entity_id, acs_url


def build_saml_settings(config, request, tenant_slug) -> dict:
    """Build the OneLogin settings dict for ``config`` on this request."""
    entity_id, acs_url = sp_urls(request, tenant_slug)
    return {
        "strict": True,  # enforce conditions (NotBefore/NotOnOrAfter), audience, destination
        "debug": False,
        "sp": {
            "entityId": entity_id,
            "assertionConsumerService": {"url": acs_url, "binding": BINDING_POST},
            "NameIDFormat": NAMEID_EMAIL,
            "x509cert": "",
            "privateKey": resolve_sp_private_key(config),
        },
        "idp": {
            "entityId": config.idp_entity_id,
            "singleSignOnService": {
                "url": config.idp_sso_url,
                "binding": BINDING_REDIRECT,
            },
            "x509cert": config.idp_x509_cert,
        },
        "security": {
            # The assertion MUST be signed — unsigned/tampered assertions are rejected.
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "wantNameId": True,
            "wantAttributeStatement": False,
            "requestedAuthnContext": False,
            "rejectUnsolicitedResponsesWithInResponseTo": False,
            # SP/IdP URLs come from our own request host + tenant config, so URL
            # validation can accept single-label hosts (real prod hosts have dots;
            # this only keeps single-label dev/test hosts like "testserver" valid).
            "allowSingleLabelDomains": True,
            "signatureAlgorithm": RSA_SHA256,
            "digestAlgorithm": SHA256,
        },
    }


def prepare_django_request(request) -> dict:
    """Adapt a Django/DRF request into the dict python3-saml expects."""
    return {
        "https": "on" if request.is_secure() else "off",
        "http_host": request.get_host(),
        "script_name": request.path,
        "get_data": request.GET.copy(),
        "post_data": request.POST.copy(),
    }
