"""
Admin AI configuration endpoints (B2).

The properties worth guarding, in order:
  1. RBAC — only an Admin reaches these at all.
  2. The key is never returned, in any response, ever.
  3. Every key set/rotate/clear is audited with the ACTOR and the ACTION, and the
     audit row does not contain the key either.
  4. A missing FIELD_ENCRYPTION_KEY is an explainable 409, not a 500.
  5. Test-connection reports a SPECIFIC state, not a boolean.
"""
import pytest
from cryptography.fernet import Fernet
from django.test import override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()
SAMPLE = "provider-token-abcdefghij9xyz"
PW = "pw12345!"

CONFIG_URL = "/api/ai/admin/config"
TEST_URL = "/api/ai/admin/test-connection"


@pytest.fixture
def api():
    return APIClient()


def _login(api, email, slug="acme"):
    resp = api.post(
        "/api/auth/login",
        {"tenant_slug": slug, "email": email, "password": PW},
        format="json",
    ).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp['access']}")
    return resp


@pytest.fixture
def tenant_and_admin():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        admin = UserFactory(tenant=t, email="admin@acme.test", password=PW, role="ADMIN")
    return t, admin


# ── RBAC ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["EMPLOYEE", "MANAGER", "HRBP"])
def test_non_admins_cannot_read_or_write_ai_config(api, role):
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        UserFactory(tenant=t, email=f"{role.lower()}@acme.test", password=PW, role=role)
    _login(api, f"{role.lower()}@acme.test")
    assert api.get(CONFIG_URL).status_code == 403
    assert api.patch(CONFIG_URL, {"enabled": False}, format="json").status_code == 403
    assert api.post(TEST_URL, {}, format="json").status_code == 403


def test_unauthenticated_is_rejected(api):
    assert api.get(CONFIG_URL).status_code == 401


# ── read ──────────────────────────────────────────────────────────────────────

@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_get_reports_state_without_the_key(api, tenant_and_admin):
    t, _admin = tenant_and_admin
    _login(api, "admin@acme.test")
    api.patch(CONFIG_URL, {"provider": "gemini", "api_key": SAMPLE}, format="json")

    body = api.get(CONFIG_URL).json()
    assert body["tenant_key_set"] is True
    assert body["key_hint"] == f"••••{SAMPLE[-4:]}"
    assert body["provider"] == "gemini"
    # The whole point:
    assert SAMPLE not in str(body)
    assert "api_key" not in body
    assert "api_key_encrypted" not in body


@override_settings(FIELD_ENCRYPTION_KEY="")
def test_get_tells_the_admin_encryption_is_unavailable(api, tenant_and_admin):
    _login(api, "admin@acme.test")
    body = api.get(CONFIG_URL).json()
    # So the UI can explain the state instead of offering a form that always fails.
    assert body["encryption_available"] is False


# ── write ─────────────────────────────────────────────────────────────────────

@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_setting_a_key_is_audited_without_the_value(api, tenant_and_admin):
    t, admin = tenant_and_admin
    _login(api, "admin@acme.test")
    resp = api.patch(CONFIG_URL, {"api_key": SAMPLE}, format="json")
    assert resp.status_code == 200

    with tenant_context(t.id):
        row = AuditLog.objects.filter(action="ai.key.set").first()
        assert row is not None
        assert row.actor_id == admin.id
        # The key must not be anywhere in the audit row.
        assert SAMPLE not in str(row.metadata)
        assert row.metadata.get("key_last4") == SAMPLE[-4:]


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_replacing_a_key_is_audited_as_a_rotation(api, tenant_and_admin):
    t, _admin = tenant_and_admin
    _login(api, "admin@acme.test")
    api.patch(CONFIG_URL, {"api_key": SAMPLE}, format="json")
    api.patch(CONFIG_URL, {"api_key": "provider-token-zzzzzzzzz1234"}, format="json")

    with tenant_context(t.id):
        assert AuditLog.objects.filter(action="ai.key.rotated").exists()


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_clearing_a_key_is_audited(api, tenant_and_admin):
    t, _admin = tenant_and_admin
    _login(api, "admin@acme.test")
    api.patch(CONFIG_URL, {"api_key": SAMPLE}, format="json")
    body = api.patch(CONFIG_URL, {"clear_api_key": True}, format="json").json()
    assert body["tenant_key_set"] is False

    with tenant_context(t.id):
        assert AuditLog.objects.filter(action="ai.key.cleared").exists()


@override_settings(FIELD_ENCRYPTION_KEY="")
def test_setting_a_key_without_encryption_is_an_explained_409(api, tenant_and_admin):
    _login(api, "admin@acme.test")
    resp = api.patch(CONFIG_URL, {"api_key": SAMPLE}, format="json")
    # Not a 500. The admin is told which variable is missing.
    assert resp.status_code == 409
    assert resp.json()["code"] == "encryption_unavailable"
    assert "FIELD_ENCRYPTION_KEY" in resp.json()["detail"]


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_an_unknown_provider_is_rejected(api, tenant_and_admin):
    _login(api, "admin@acme.test")
    resp = api.patch(CONFIG_URL, {"provider": "evil.module.Path"}, format="json")
    assert resp.status_code == 400
    assert resp.json()["code"] == "unknown_provider"


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_toggling_the_switch_does_not_drop_the_stored_key(api, tenant_and_admin):
    """PATCH, not PUT, precisely so an unrelated edit cannot clear the key."""
    _login(api, "admin@acme.test")
    api.patch(CONFIG_URL, {"api_key": SAMPLE}, format="json")
    body = api.patch(CONFIG_URL, {"enabled": False}, format="json").json()
    assert body["enabled"] is False
    assert body["tenant_key_set"] is True


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_switching_ai_off_is_audited(api, tenant_and_admin):
    t, _admin = tenant_and_admin
    _login(api, "admin@acme.test")
    api.patch(CONFIG_URL, {"enabled": False}, format="json")
    with tenant_context(t.id):
        row = AuditLog.objects.filter(action="ai.config.switch").first()
        assert row is not None and row.metadata.get("enabled") is False


# ── test connection ───────────────────────────────────────────────────────────

@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.NotConfiguredProvider"
)
def test_test_connection_reports_not_configured_rather_than_failing(api, tenant_and_admin):
    _login(api, "admin@acme.test")
    body = api.post(TEST_URL, {}, format="json").json()
    assert body["ok"] is False
    assert body["state"] == "not_configured"


@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.FakeLLMProvider"
)
def test_test_connection_succeeds_against_a_configured_provider(api, tenant_and_admin):
    """Uses the deterministic in-repo provider — NEVER a live model call."""
    _login(api, "admin@acme.test")
    body = api.post(TEST_URL, {}, format="json").json()
    assert body["ok"] is True
    assert body["state"] == "ok"
    assert body["key_source"] == "environment"


@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.FakeLLMProvider"
)
def test_test_connection_distinguishes_ai_switched_off(api, tenant_and_admin):
    _login(api, "admin@acme.test")
    api.patch(CONFIG_URL, {"enabled": False}, format="json")
    body = api.post(TEST_URL, {}, format="json").json()
    assert body["ok"] is False
    # Not a generic error: "your admin turned this off" is a different thing to
    # fix than "the key is wrong".
    assert body["state"] == "ai_disabled"


@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.FakeLLMProvider"
)
def test_test_connection_is_audited(api, tenant_and_admin):
    t, _admin = tenant_and_admin
    _login(api, "admin@acme.test")
    api.post(TEST_URL, {}, format="json")
    with tenant_context(t.id):
        assert AuditLog.objects.filter(action="ai.connection.tested").exists()


# ── tenant isolation ──────────────────────────────────────────────────────────

@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_one_tenants_key_is_invisible_to_another(api):
    a = TenantFactory(slug="acme")
    b = TenantFactory(slug="globex")
    with tenant_context(a.id):
        UserFactory(tenant=a, email="admin@acme.test", password=PW, role="ADMIN")
    with tenant_context(b.id):
        UserFactory(tenant=b, email="admin@globex.test", password=PW, role="ADMIN")

    _login(api, "admin@acme.test", slug="acme")
    api.patch(CONFIG_URL, {"api_key": SAMPLE, "provider": "gemini"}, format="json")

    other = APIClient()
    _login(other, "admin@globex.test", slug="globex")
    body = other.get(CONFIG_URL).json()
    assert body["tenant_key_set"] is False
    assert body["provider"] == ""
    assert SAMPLE not in str(body)
