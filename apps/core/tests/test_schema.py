"""
The OpenAPI schema endpoint (F6).

Two things are being pinned. That the schema is **authenticated** — it is a
complete map of every endpoint, parameter and payload shape, which is exactly
what someone probing the API would like handed to them, and there is no reason
an anonymous caller needs it. And that it **generates at all**: it is produced
from the live URLconf, so a view that breaks introspection breaks the schema, and
without a test that failure surfaces the first time somebody opens the docs page
rather than in CI.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

SCHEMA = "/api/schema/"
SCHEMA_UI = "/api/schema/ui/"


@pytest.fixture
def user(db):
    return UserFactory(tenant=TenantFactory(slug="acme", name="Acme"), role="EMPLOYEE")


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_the_schema_requires_authentication():
    """A full map of the API is not secret, but it is not an invitation either."""
    assert APIClient().get(SCHEMA).status_code == 401


def test_the_docs_page_requires_authentication():
    assert APIClient().get(SCHEMA_UI).status_code == 401


def test_an_authenticated_user_gets_a_valid_schema(user):
    import yaml

    resp = _client_for(user).get(SCHEMA)
    assert resp.status_code == 200, resp.content
    document = yaml.safe_load(resp.content)
    assert document["openapi"].startswith("3.")
    assert document["info"]["title"]
    # A real API surface, not an empty document that technically parses.
    assert len(document["paths"]) > 100


def test_it_covers_the_endpoints_it_should(user):
    import yaml

    document = yaml.safe_load(_client_for(user).get(SCHEMA).content)
    for path in (
        "/api/auth/login",
        "/api/goals/",
        "/api/admin/users/{id}/export",
        "/api/admin/users/{id}/erase",
    ):
        assert path in document["paths"], f"{path} is missing from the schema"


def test_the_schema_does_not_document_itself(user):
    """Noise: the endpoint that serves the map is not part of the API the map
    describes."""
    import yaml

    document = yaml.safe_load(_client_for(user).get(SCHEMA).content)
    assert SCHEMA not in document["paths"]


def test_ops_probes_are_not_in_the_product_api(user):
    """`/healthz` and `/readyz` are for the load balancer. Listing them invites a
    client to depend on them, and they are not covered by any API contract."""
    import yaml

    document = yaml.safe_load(_client_for(user).get(SCHEMA).content)
    assert "/healthz" not in document["paths"]
    assert "/readyz" not in document["paths"]


def test_an_annotated_endpoint_carries_its_documentation(user):
    """The two data-rights endpoints are annotated as the worked example of the
    @extend_schema pattern. If this breaks, the example stopped being one."""
    import yaml

    document = yaml.safe_load(_client_for(user).get(SCHEMA).content)
    erase = document["paths"]["/api/admin/users/{id}/erase"]["post"]
    assert "irreversibly" in erase["summary"]
    assert "requestBody" in erase
