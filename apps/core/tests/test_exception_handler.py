"""
The custom DRF exception handler (BUILD_6 6.5 stabilization sweep).

A malformed UUID in a query param that filters a ``UUIDField`` made the ORM raise
Django's ``ValidationError`` during queryset evaluation, which the default DRF
handler doesn't recognise → a 500. These hit the REAL routes that exhibited it
(reviews/goals filtered by ``?cycle=``, audit by ``?actor=``) and assert a clean
400 — never a 500 that would leak a stack trace.
"""
import pytest
from rest_framework.test import APIClient

from apps.identity.tokens import issue_tokens_for_user

pytestmark = pytest.mark.django_db


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.mark.parametrize(
    "actor_attr, path",
    [
        ("manager", "/api/reviews/?cycle=notauuid"),
        ("manager", "/api/goals/?cycle=notauuid"),
        ("hrbp", "/api/audit/logs?actor=notauuid"),
        ("hrbp", "/api/analytics/calibration?cycle=notauuid"),
    ],
)
def test_malformed_uuid_query_param_is_400_not_500(org, actor_attr, path):
    actor = getattr(org, actor_attr)
    resp = _client_for(actor).get(path)
    assert resp.status_code == 400, f"{path} → {resp.status_code} (want 400, not a 500)"
    assert resp.json().get("code") == "INVALID_INPUT"


def test_wellformed_uuid_query_param_still_works(org):
    """A syntactically valid (if non-existent) cycle uuid is NOT a 400 — it filters
    normally and returns an (empty) list, proving the handler only catches the
    malformed case."""
    resp = _client_for(org.manager).get(
        "/api/reviews/?cycle=00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 200
