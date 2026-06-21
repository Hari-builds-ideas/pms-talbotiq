"""
OIDC -> tenant-user mapping.

The mapping logic in the adapter is unit-tested directly with a lightweight
social-login stand-in (the adapter only touches ``.user``, ``.account.extra_data``
and ``.state``). The post-login token mint is tested end-to-end through the
complete endpoint with a real Django session. A live IdP round-trip is out of
scope here — the generic OIDC provider is wired and configured from env, and
its presence is validated by ``manage.py check`` / app loading.
"""
from types import SimpleNamespace

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from django.test import RequestFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.identity.adapters import TenantSocialAccountAdapter
from apps.identity.models import User
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _sociallogin(email, email_verified=True):
    extra_data = {"email": email}
    # Only include the claim when explicitly provided; passing None lets a test
    # simulate an IdP that omits ``email_verified`` entirely.
    if email_verified is not None:
        extra_data["email_verified"] = email_verified
    return SimpleNamespace(
        user=User(email=email),
        account=SimpleNamespace(extra_data=extra_data, provider="openid_connect", uid="x"),
        state={},
    )


def _request(tenant_slug=None):
    rf = RequestFactory()
    path = "/accounts/oidc/login/callback/"
    if tenant_slug:
        path += f"?tenant={tenant_slug}"
    req = rf.get(path)
    req.session = {}
    return req


def test_adapter_maps_identity_to_existing_tenant_user():
    t = TenantFactory(slug="acme")
    existing = UserFactory(tenant=t, email="person@acme.test")
    adapter = TenantSocialAccountAdapter()
    sl = _sociallogin("person@acme.test")
    adapter.pre_social_login(_request("acme"), sl)
    assert sl.user.pk == existing.pk
    assert sl.user.tenant_id == t.id
    assert sl.state["process"] == "connect"


def test_adapter_rejects_unknown_identity():
    TenantFactory(slug="acme")
    adapter = TenantSocialAccountAdapter()
    sl = _sociallogin("ghost@acme.test")
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request("acme"), sl)


def test_adapter_rejects_when_tenant_cannot_be_resolved():
    adapter = TenantSocialAccountAdapter()
    sl = _sociallogin("person@acme.test")
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request(tenant_slug=None), sl)


def test_adapter_does_not_cross_tenant():
    # A user with the same email exists, but in a DIFFERENT tenant than resolved.
    other = TenantFactory(slug="other")
    UserFactory(tenant=other, email="person@acme.test")
    TenantFactory(slug="acme")  # resolved tenant, no such user
    adapter = TenantSocialAccountAdapter()
    sl = _sociallogin("person@acme.test")
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request("acme"), sl)


def test_adapter_denies_unverified_email():
    # A matching active tenant user exists, so the ONLY reason to deny is the
    # unverified email claim — proving the flag is the deciding factor.
    t = TenantFactory(slug="acme")
    existing = UserFactory(tenant=t, email="person@acme.test")
    adapter = TenantSocialAccountAdapter()

    # email_verified omitted -> denied.
    sl_missing = _sociallogin("person@acme.test", email_verified=None)
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request("acme"), sl_missing)

    # email_verified False -> denied.
    sl_false = _sociallogin("person@acme.test", email_verified=False)
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request("acme"), sl_false)

    # Same identity, email_verified True -> maps to the existing user.
    sl_verified = _sociallogin("person@acme.test", email_verified=True)
    adapter.pre_social_login(_request("acme"), sl_verified)
    assert sl_verified.user.pk == existing.pk
    assert sl_verified.state["process"] == "connect"


def test_oidc_complete_mints_tenant_scoped_jwt():
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="person@acme.test", password="pw12345!")
    client = APIClient()
    client.force_login(user)  # establishes the Django session allauth would create
    resp = client.get("/api/auth/oidc/complete")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == str(t.id)
    assert AccessToken(data["access"])["tenant_id"] == str(t.id)


def test_oidc_complete_without_session_is_401():
    resp = APIClient().get("/api/auth/oidc/complete")
    assert resp.status_code == 401


def test_adapter_resolves_tenant_from_session_hint():
    # The other resolve_tenant branch: no ?tenant= query, the slug is read from the
    # session (set by the login handoff). Proves the handoff→callback tenant binding.
    t = TenantFactory(slug="acme")
    existing = UserFactory(tenant=t, email="person@acme.test")
    adapter = TenantSocialAccountAdapter()
    rf = RequestFactory()
    req = rf.get("/accounts/oidc/login/callback/")  # no ?tenant= hint
    req.session = {"oidc_tenant_slug": "acme"}
    sl = _sociallogin("person@acme.test")
    adapter.pre_social_login(req, sl)
    assert sl.user.pk == existing.pk
    assert sl.user.tenant_id == t.id


def test_oidc_complete_role_claim_matches_user_role():
    # OIDC keeps the provisioned DB role (no IdP role override on this path) — the
    # minted JWT's role claim equals the user's role.
    t = TenantFactory(slug="acme")
    user = UserFactory(tenant=t, email="hrbp@acme.test", role=User.Role.HRBP)
    client = APIClient()
    client.force_login(user)
    data = client.get("/api/auth/oidc/complete").json()
    assert AccessToken(data["access"])["role"] == User.Role.HRBP
    assert data["role"] == User.Role.HRBP
