"""
HTTP tests for the integration-config API (Admin-only). Configuring is audited and
admin-gated; the response NEVER carries a secret value; config is tenant-isolated.
"""
import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db

INT = "/api/integrations"


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_admin_upserts_and_lists_integrations(org):
    admin = _client_for(org.admin)
    resp = admin.put(
        f"{INT}/SLACK",
        {"enabled": True, "config": {"channel": "#perf"}, "secret_ref": "SLACK_WEBHOOK_ACME"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["kind"] == "SLACK" and body["enabled"] is True
    assert body["config"]["channel"] == "#perf"
    assert body["secret_ref"] == "SLACK_WEBHOOK_ACME"

    admin.put(f"{INT}/JIRA", {"enabled": True, "config": {"base_url": "https://j"}}, format="json")
    listing = admin.get(f"{INT}/").json()
    kinds = {row["kind"] for row in listing}
    assert kinds == {"SLACK", "JIRA"}
    with tenant_context(org.tenant):
        assert AuditLog.objects.filter(action="integration.configured").count() >= 2


def test_response_never_contains_a_secret_value(org):
    admin = _client_for(org.admin)
    resp = admin.put(
        f"{INT}/SLACK",
        {"enabled": True, "config": {"channel": "#x"}, "secret_ref": "SLACK_WEBHOOK_ACME"},
        format="json",
    )
    body = resp.json()
    # Only the env-var NAME is present — there is no token/secret field at all.
    assert "token" not in body and "secret" not in body
    assert set(body) == {"id", "kind", "enabled", "config", "secret_ref", "updated_at"}


def test_get_unconfigured_kind_is_404(org):
    admin = _client_for(org.admin)
    assert admin.get(f"{INT}/JIRA").status_code == 404


def test_non_admin_is_forbidden(org):
    for user in (org.hrbp, org.manager, org.report):
        client = _client_for(user)
        assert client.get(f"{INT}/").status_code == 403
        assert client.put(f"{INT}/SLACK", {"enabled": True}, format="json").status_code == 403


def test_unknown_kind_is_rejected(org):
    # An unknown integration kind in the path is a bad request (DRF ValidationError).
    admin = _client_for(org.admin)
    assert admin.put(f"{INT}/EMAIL", {"enabled": True}, format="json").status_code == 400


def test_config_is_tenant_isolated(org, other_tenant):
    _client_for(org.admin).put(
        f"{INT}/SLACK", {"enabled": True, "config": {"channel": "#acme"}}, format="json"
    )
    other_admin = UserFactory(tenant=other_tenant, role="ADMIN", email="oadmin@other.test")
    listing = _client_for(other_admin).get(f"{INT}/").json()
    assert listing == []  # the other tenant sees none of org's integrations


def test_unauthenticated_is_401(org):
    assert APIClient().get(f"{INT}/").status_code == 401
