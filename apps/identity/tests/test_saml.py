"""
SAML 2.0 SP — proven against a self-signed MOCK IdP.

These tests stand up an in-memory IdP (a fresh RSA keypair + self-signed cert),
build a SAML Response, and sign the Assertion with a REAL enveloped XML signature
via xmlsec — exactly what a production IdP (Okta/Azure AD) does. The assertion is
then POSTed to our tenant-scoped ACS and we assert:

* happy path → our tenant-scoped JWT is minted with the right tenant + role;
* a tampered assertion, an unsigned assertion, and an expired assertion are rejected;
* a replayed assertion is rejected (consume-once guard);
* tenant isolation — tenant A's IdP cannot mint a tenant B session;
* attribute → role mapping (and the safe fallback to the provisioned DB role).

A real production IdP is the customer's to provide (docs/SSO.md); this proves the
SP end-to-end without one.
"""
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.core.cache import cache
from django.urls import reverse
from lxml import etree
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.identity.models import SamlIdpConfig, User
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAMLP_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
ACS_NAME = "identity:saml-acs"


# ─────────────────────────── mock IdP ───────────────────────────
class MockIdp:
    """A self-signed SAML IdP: holds a keypair + cert and signs assertions."""

    _counter = 0

    def __init__(self, entity_id="https://idp.mock/metadata"):
        self.entity_id = entity_id
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "mock-idp")]
        )
        now = datetime.now(timezone.utc)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .sign(self.key, hashes.SHA256())
        )

    @property
    def key_pem(self) -> bytes:
        return self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )

    @property
    def cert_pem(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.PEM)

    @property
    def cert_b64(self) -> str:
        """The cert body (no PEM headers) — the form an admin pastes into config."""
        body = self.cert_pem.decode()
        return "".join(
            line for line in body.splitlines() if "CERTIFICATE" not in line
        )

    @staticmethod
    def _uid(prefix):
        MockIdp._counter += 1
        return f"_{prefix}{MockIdp._counter:06d}"

    def response_xml(
        self,
        *,
        acs_url,
        sp_entity_id,
        email,
        attributes=None,
        not_before_delta=timedelta(minutes=-5),
        not_after_delta=timedelta(minutes=5),
        assertion_id=None,
    ):
        """Build an (unsigned) SAML Response element tree + the assertion id."""
        now = datetime.now(timezone.utc)
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        resp_id = self._uid("resp")
        assertion_id = assertion_id or self._uid("assert")
        not_before = (now + not_before_delta).strftime(fmt)
        not_after = (now + not_after_delta).strftime(fmt)
        issue_instant = now.strftime(fmt)

        attrs_xml = ""
        for name, values in (attributes or {}).items():
            vals = "".join(
                f'<saml:AttributeValue xmlns:xs="http://www.w3.org/2001/XMLSchema" '
                f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                f'xsi:type="xs:string">{v}</saml:AttributeValue>'
                for v in values
            )
            attrs_xml += f'<saml:Attribute Name="{name}" NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:basic">{vals}</saml:Attribute>'
        attr_statement = (
            f"<saml:AttributeStatement>{attrs_xml}</saml:AttributeStatement>"
            if attrs_xml
            else ""
        )

        xml = f"""<samlp:Response xmlns:samlp="{SAMLP_NS}" xmlns:saml="{SAML_NS}" ID="{resp_id}" Version="2.0" IssueInstant="{issue_instant}" Destination="{acs_url}">
  <saml:Issuer>{self.entity_id}</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  <saml:Assertion xmlns:saml="{SAML_NS}" ID="{assertion_id}" Version="2.0" IssueInstant="{issue_instant}">
    <saml:Issuer>{self.entity_id}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{email}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData NotOnOrAfter="{not_after}" Recipient="{acs_url}"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_after}">
      <saml:AudienceRestriction><saml:Audience>{sp_entity_id}</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="{issue_instant}" SessionIndex="{self._uid('sess')}">
      <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef></saml:AuthnContext>
    </saml:AuthnStatement>
    {attr_statement}
  </saml:Assertion>
</samlp:Response>"""
        root = etree.fromstring(xml.encode())
        return root, assertion_id

    def sign_assertion(self, root, assertion_id):
        """Apply a real enveloped XML signature to the Assertion node."""
        assertion = root.find(f"{{{SAML_NS}}}Assertion")
        signature = xmlsec.template.create(
            assertion,
            c14n_method=xmlsec.constants.TransformExclC14N,
            sign_method=xmlsec.constants.TransformRsaSha256,
        )
        # Schema order: Issuer, Signature, Subject, ... → insert right after Issuer.
        assertion.insert(1, signature)
        ref = xmlsec.template.add_reference(
            signature, xmlsec.constants.TransformSha256, uri="#" + assertion_id
        )
        xmlsec.template.add_transform(ref, xmlsec.constants.TransformEnveloped)
        xmlsec.template.add_transform(ref, xmlsec.constants.TransformExclC14N)
        key_info = xmlsec.template.ensure_key_info(signature)
        xmlsec.template.add_x509_data(key_info)

        ctx = xmlsec.SignatureContext()
        key = xmlsec.Key.from_memory(self.key_pem, xmlsec.constants.KeyDataFormatPem)
        key.load_cert_from_memory(self.cert_pem, xmlsec.constants.KeyDataFormatPem)
        ctx.key = key
        ctx.register_id(assertion, "ID", None)
        ctx.sign(signature)
        return root

    def signed_response_b64(self, *, acs_url, sp_entity_id, email, attributes=None, **kw):
        root, aid = self.response_xml(
            acs_url=acs_url, sp_entity_id=sp_entity_id, email=email,
            attributes=attributes, **kw,
        )
        self.sign_assertion(root, aid)
        return base64.b64encode(etree.tostring(root)).decode()

    def unsigned_response_b64(self, *, acs_url, sp_entity_id, email, **kw):
        root, _ = self.response_xml(
            acs_url=acs_url, sp_entity_id=sp_entity_id, email=email, **kw
        )
        return base64.b64encode(etree.tostring(root)).decode()


# ─────────────────────────── fixtures ───────────────────────────
@pytest.fixture(autouse=True)
def _clear_replay_cache():
    cache.clear()
    yield
    cache.clear()


def _sp_urls(slug):
    base = "http://testserver"
    return (
        f"{base}{reverse('identity:saml-metadata', args=[slug])}",  # SP entityId
        f"{base}{reverse(ACS_NAME, args=[slug])}",                  # ACS url
    )


def _configure_tenant(slug, idp, *, role_attribute="role", role_map=None, email="u@acme.test", role=None):
    tenant = TenantFactory(slug=slug)
    with tenant_context(tenant):
        user = UserFactory(tenant=tenant, email=email, role=role or User.Role.EMPLOYEE)
        SamlIdpConfig.objects.create(
            tenant=tenant,
            enabled=True,
            idp_entity_id=idp.entity_id,
            idp_sso_url="https://idp.mock/sso",
            idp_x509_cert=idp.cert_b64,
            email_attribute="email",
            role_attribute=role_attribute,
            role_map=role_map or {},
        )
    return tenant, user


def _post_acs(slug, saml_response_b64):
    # base64 contains +/= — must be percent-encoded so the urlencoded body survives.
    return APIClient().post(
        reverse(ACS_NAME, args=[slug]),
        data=urlencode({"SAMLResponse": saml_response_b64}),
        content_type="application/x-www-form-urlencoded",
    )


# ─────────────────────────── tests ───────────────────────────
def test_saml_acs_happy_path_mints_tenant_scoped_jwt():
    idp = MockIdp()
    tenant, user = _configure_tenant("acme", idp, email="person@acme.test")
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="person@acme.test"
    )
    resp = _post_acs("acme", b64)
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert data["tenant_id"] == str(tenant.id)
    assert AccessToken(data["access"])["tenant_id"] == str(tenant.id)
    assert AccessToken(data["access"])["role"] == User.Role.EMPLOYEE


def test_saml_rejects_tampered_assertion():
    idp = MockIdp()
    _configure_tenant("acme", idp, email="person@acme.test")
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="person@acme.test"
    )
    # Flip the signed email after signing → digest mismatch → signature invalid.
    raw = base64.b64decode(b64).replace(b"person@acme.test", b"attacker@acme.test")
    tampered = base64.b64encode(raw).decode()
    resp = _post_acs("acme", tampered)
    assert resp.status_code == 401


def test_saml_rejects_unsigned_assertion():
    idp = MockIdp()
    _configure_tenant("acme", idp, email="person@acme.test")
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.unsigned_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="person@acme.test"
    )
    resp = _post_acs("acme", b64)
    assert resp.status_code == 401


def test_saml_rejects_expired_assertion():
    idp = MockIdp()
    _configure_tenant("acme", idp, email="person@acme.test")
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="person@acme.test",
        not_before_delta=timedelta(minutes=-30),
        not_after_delta=timedelta(minutes=-10),  # already expired
    )
    resp = _post_acs("acme", b64)
    assert resp.status_code == 401


def test_saml_rejects_replayed_assertion():
    idp = MockIdp()
    _configure_tenant("acme", idp, email="person@acme.test")
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="person@acme.test"
    )
    first = _post_acs("acme", b64)
    assert first.status_code == 200, first.content
    second = _post_acs("acme", b64)  # same assertion id again
    assert second.status_code == 401
    assert second.json()["code"] == "saml_replay"


def test_saml_tenant_isolation_idp_a_cannot_mint_tenant_b_session():
    """Tenant A's IdP signs an assertion; posting it to tenant B's ACS is rejected
    because B verifies against ITS OWN configured cert (different key)."""
    idp_a = MockIdp(entity_id="https://idp-a.mock/metadata")
    idp_b = MockIdp(entity_id="https://idp-b.mock/metadata")
    _configure_tenant("acme", idp_a, email="shared@corp.test")
    # Tenant B exists with the SAME email user, but trusts idp_b's cert only.
    _configure_tenant("globex", idp_b, email="shared@corp.test")

    sp_entity_b, acs_url_b = _sp_urls("globex")
    # idp_a signs an assertion aimed at tenant B's ACS/audience.
    b64 = idp_a.signed_response_b64(
        acs_url=acs_url_b, sp_entity_id=sp_entity_b, email="shared@corp.test"
    )
    resp = _post_acs("globex", b64)
    assert resp.status_code == 401  # signature fails against idp_b's cert


def test_saml_unknown_identity_denied():
    idp = MockIdp()
    _configure_tenant("acme", idp, email="person@acme.test")
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="ghost@acme.test"
    )
    resp = _post_acs("acme", b64)
    assert resp.status_code == 401
    assert resp.json()["code"] == "saml_unknown_user"


def test_saml_role_mapping_cannot_escalate_above_provisioned():
    """Rank cap: an IdP that maps the user to a HIGHER role than admin-provisioned is
    REFUSED — the session + DB role stay at the provisioned role, no escalation, no
    role-sync audit (no IdP-driven privilege escalation)."""
    idp = MockIdp()
    tenant, user = _configure_tenant(
        "acme", idp, email="grunt@acme.test", role=User.Role.EMPLOYEE,
        role_attribute="role", role_map={"pms-admins": "ADMIN"},
    )
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="grunt@acme.test",
        attributes={"role": ["pms-admins"]},
    )
    resp = _post_acs("acme", b64)
    assert resp.status_code == 200, resp.content
    assert resp.json()["role"] == "EMPLOYEE"  # capped — NOT elevated to ADMIN
    assert AccessToken(resp.json()["access"])["role"] == "EMPLOYEE"
    from apps.audit.models import AuditLog
    with tenant_context(tenant):
        assert User.objects.get(pk=user.pk).role == User.Role.EMPLOYEE  # unchanged
        assert not AuditLog.objects.filter(action="identity.saml.role_synced").exists()


def test_saml_role_mapping_can_deescalate_and_audits():
    """The cap is a ceiling, not a freeze: a mapped role AT OR BELOW the provisioned
    role is applied — here an ADMIN mapped down to EMPLOYEE is synced + audited."""
    idp = MockIdp()
    tenant, user = _configure_tenant(
        "acme", idp, email="boss@acme.test", role=User.Role.ADMIN,
        role_attribute="role", role_map={"pms-grunts": "EMPLOYEE"},
    )
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="boss@acme.test",
        attributes={"role": ["pms-grunts"]},
    )
    resp = _post_acs("acme", b64)
    assert resp.status_code == 200, resp.content
    assert resp.json()["role"] == "EMPLOYEE"  # de-escalated (<= provisioned)
    assert AccessToken(resp.json()["access"])["role"] == "EMPLOYEE"
    from apps.audit.models import AuditLog
    with tenant_context(tenant):
        assert User.objects.get(pk=user.pk).role == User.Role.EMPLOYEE
        entry = AuditLog.objects.filter(action="identity.saml.role_synced").first()
        assert entry is not None
        assert entry.metadata == {"from": "ADMIN", "to": "EMPLOYEE", "source": "saml"}


def test_saml_role_mapping_falls_back_to_db_role_when_attribute_absent():
    idp = MockIdp()
    _configure_tenant(
        "acme", idp, email="mgr@acme.test", role=User.Role.MANAGER,
        role_attribute="role", role_map={"pms-admins": "ADMIN"},
    )
    sp_entity, acs_url = _sp_urls("acme")
    b64 = idp.signed_response_b64(
        acs_url=acs_url, sp_entity_id=sp_entity, email="mgr@acme.test"
    )  # no role attribute in the assertion
    resp = _post_acs("acme", b64)
    assert resp.status_code == 200, resp.content
    assert resp.json()["role"] == "MANAGER"  # provisioned DB role, not escalated


def test_saml_acs_404_when_tenant_not_configured():
    TenantFactory(slug="acme")  # active tenant, but no SamlIdpConfig
    resp = _post_acs("acme", "ignored")
    assert resp.status_code == 404


def test_saml_metadata_endpoint_serves_sp_xml():
    idp = MockIdp()
    _configure_tenant("acme", idp)
    resp = APIClient().get(reverse("identity:saml-metadata", args=["acme"]))
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/xml")
    body = resp.content.decode()
    assert "AssertionConsumerService" in body
    assert reverse(ACS_NAME, args=["acme"]) in body


def test_saml_login_redirects_to_idp():
    idp = MockIdp()
    _configure_tenant("acme", idp)
    resp = APIClient().get(reverse("identity:saml-login", args=["acme"]))
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://idp.mock/sso")


def test_saml_modules_do_not_import_onelogin_at_top_level():
    """Regression guard (worker hang): python3-saml (``onelogin``) must be imported
    LAZILY inside the request handlers, never at module top-level. These SAML modules
    are pulled in when Django loads the URLconf — which ALSO happens in the Celery
    worker/beat (they import the Django app). A top-level import of this HTTP-only SSO
    dependency crashed the worker on startup when its image lacked python3-saml,
    silently stranding every async AI job (the "Request AI Draft" infinite spinner).

    We assert the invariant two ways: the onelogin symbols are not bound in the module
    namespaces (so the import is deferred), and no ``import onelogin`` appears at
    column 0 in the source. The metadata/login/acs tests above prove the lazy imports
    still work end-to-end."""
    import inspect

    from apps.identity.saml import service as saml_service
    from apps.identity.saml import views as saml_views

    for mod in (saml_views, saml_service):
        g = vars(mod)
        assert "onelogin" not in g
        assert "OneLogin_Saml2_Auth" not in g
        assert "OneLogin_Saml2_Settings" not in g
        for line in inspect.getsource(mod).splitlines():
            assert not (line.startswith("import onelogin") or line.startswith("from onelogin")), (
                f"{mod.__name__} imports onelogin at top level: {line!r}"
            )
