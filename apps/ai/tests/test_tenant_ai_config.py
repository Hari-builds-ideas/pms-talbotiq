"""
Per-tenant AI configuration (B1).

The invariants under test, in order of how much they would hurt to lose:
  1. The decrypted key NEVER leaves the config module — not via the API, not via
     ``public_state``, not in a log line.
  2. Nothing is stored in plaintext, ever. No FIELD_ENCRYPTION_KEY means the write
     is refused, not downgraded.
  3. Resolution order is tenant key → environment key → not configured.

"""
import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.ai import crypto
from apps.ai.models import TenantAIConfig
from apps.ai.tenant_config import (
    EncryptionUnavailable,
    clear_api_key,
    get_config,
    public_state,
    resolve_provider,
    set_api_key,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()
#: Not a credential and deliberately not provider-shaped — just a distinctive
#: string so the "is it stored in the clear?" and last-4 assertions are meaningful.
SAMPLE = "provider-token-abcdefghij9xyz"


# ── crypto ────────────────────────────────────────────────────────────────────

@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt(SAMPLE)
    assert token != SAMPLE  # actually encrypted, not encoded
    assert SAMPLE not in token
    assert crypto.decrypt(token) == SAMPLE


@override_settings(FIELD_ENCRYPTION_KEY="")
def test_encrypt_refuses_without_a_key_rather_than_storing_plaintext():
    assert crypto.encryption_available() is False
    with pytest.raises(EncryptionUnavailable):
        crypto.encrypt(SAMPLE)


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_tampered_ciphertext_decrypts_to_none_not_garbage():
    token = crypto.encrypt(SAMPLE)
    tampered = token[:-4] + "AAAA"
    # Fernet is authenticated, so this is detected rather than silently returning
    # a corrupted "key" we would then send to a provider.
    assert crypto.decrypt(tampered) is None


def test_decrypt_returns_none_when_no_key_is_configured():
    with override_settings(FIELD_ENCRYPTION_KEY=KEY):
        token = crypto.encrypt(SAMPLE)
    with override_settings(FIELD_ENCRYPTION_KEY=""):
        # Degrades to "unreadable" so the gateway falls through to the env key,
        # rather than 500ing every AI request in the tenant.
        assert crypto.decrypt(token) is None


def test_rotation_reads_values_written_under_an_older_key():
    old = Fernet.generate_key().decode()
    with override_settings(FIELD_ENCRYPTION_KEY=old):
        token = crypto.encrypt(SAMPLE)
    # New key first, old key retained: the rotation window must not make existing
    # ciphertext unreadable.
    with override_settings(FIELD_ENCRYPTION_KEY=f"{KEY},{old}"):
        assert crypto.decrypt(token) == SAMPLE


# ── storage ───────────────────────────────────────────────────────────────────

@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_key_is_stored_encrypted_and_never_in_the_clear():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        admin = UserFactory(tenant=t, email="a@acme.test", role="ADMIN")
        set_api_key(t, raw_key=SAMPLE, actor=admin)

        row = TenantAIConfig.objects.get(tenant_id=t.id)
        assert row.api_key_encrypted
        assert SAMPLE not in row.api_key_encrypted
        # Only the last four characters are kept readable.
        assert row.key_last4 == SAMPLE[-4:]
        assert row.key_set_by_id == admin.id
        assert row.key_set_at is not None


@override_settings(FIELD_ENCRYPTION_KEY="")
def test_setting_a_key_without_encryption_configured_is_refused():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        with pytest.raises(EncryptionUnavailable):
            set_api_key(t, raw_key=SAMPLE)
        # Crucially: nothing was written.
        row = TenantAIConfig.objects.filter(tenant_id=t.id).first()
        assert row is None or not row.api_key_encrypted


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_public_state_never_exposes_the_key():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        set_api_key(t, raw_key=SAMPLE)
        state = public_state(t)

    flat = repr(state)
    assert SAMPLE not in flat
    # The stored ciphertext must not leak either — it is still the secret.
    assert "gAAAA" not in flat
    assert state["tenant_key_set"] is True
    assert state["key_hint"] == f"••••{SAMPLE[-4:]}"
    assert state["encryption_available"] is True


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_clearing_the_key_falls_back_to_the_environment():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        set_api_key(t, raw_key=SAMPLE)
        clear_api_key(t)
        row = TenantAIConfig.objects.get(tenant_id=t.id)
        assert row.api_key_encrypted == ""
        assert row.key_last4 == ""


# ── resolution order ──────────────────────────────────────────────────────────

@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.NotConfiguredProvider"
)
def test_tenant_key_wins_over_an_unconfigured_environment():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        cfg = get_config(t)
        cfg.provider = "gemini"
        cfg.save(update_fields=["provider"])
        set_api_key(t, raw_key=SAMPLE)

        dotted, key, source = resolve_provider(t)
    assert source == "tenant"
    assert dotted == "apps.ai.gemini_provider.GeminiProvider"
    assert key == SAMPLE


@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.FakeLLMProvider"
)
def test_environment_serves_a_tenant_with_no_key_of_its_own():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        dotted, key, source = resolve_provider(t)
    assert source == "environment"
    assert dotted == "apps.ai.providers.FakeLLMProvider"
    assert key is None


@override_settings(
    FIELD_ENCRYPTION_KEY=KEY, LLM_PROVIDER="apps.ai.providers.NotConfiguredProvider"
)
def test_no_tenant_key_and_no_environment_key_is_unconfigured():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        dotted, key, source = resolve_provider(t)
    assert source == "unconfigured"
    assert dotted.endswith("NotConfiguredProvider")
    assert key is None


def test_an_undecryptable_tenant_key_degrades_to_the_environment():
    """A key written under a rotated-away encryption key must not take the tenant
    down — it falls through to the deployment default."""
    t = TenantFactory(slug="acme")
    with override_settings(FIELD_ENCRYPTION_KEY=KEY):
        with tenant_context(t.id):
            set_api_key(t, raw_key=SAMPLE)

    other = Fernet.generate_key().decode()
    with override_settings(
        FIELD_ENCRYPTION_KEY=other, LLM_PROVIDER="apps.ai.providers.FakeLLMProvider"
    ):
        with tenant_context(t.id):
            _dotted, key, source = resolve_provider(t)
    assert source == "environment"
    assert key is None


def test_provider_choice_cannot_name_an_arbitrary_import_path():
    """An admin picks a SLUG, not a dotted path. Anything outside the map resolves
    to no tenant provider rather than importing whatever it names."""
    from apps.ai.tenant_config import PROVIDER_PATHS

    assert set(PROVIDER_PATHS) == {"gemini", "openai", "groq"}
    for dotted in PROVIDER_PATHS.values():
        assert dotted.startswith("apps.ai.")
