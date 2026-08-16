"""
Idempotency keys on the operations you must not do twice (F7).

The realistic caller is not malicious: it is a phone on a train that lost the
connection after the request reached the server, a browser retrying a POST, or a
second click on a button whose spinner has not appeared yet. In every case the
client genuinely does not know whether the first attempt landed, and the only
safe thing it can do is retry.

What must hold:

  * a retry with the same key returns the FIRST response and changes nothing;
  * a *different* request under the same key is refused, not silently answered
    with somebody else's result;
  * a key from one user, or one tenant, never replays to another;
  * failures are not stored — a 4xx must not pin a client to its own mistake;
  * no key at all behaves exactly as before.
"""
import uuid

import pytest
from rest_framework.test import APIClient

from apps.core.models import IdempotencyRecord
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _client_for(user):
    access, _ = issue_tokens_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def org(db):
    from types import SimpleNamespace

    t = TenantFactory(slug="acme", name="Acme")
    return SimpleNamespace(
        tenant=t,
        admin=UserFactory(tenant=t, email="admin@acme.test", role="ADMIN"),
        other_admin=UserFactory(tenant=t, email="admin2@acme.test", role="ADMIN"),
    )


CHECKOUT = "/api/billing/checkout"


def _post(user, key=None, body=None):
    """`body is None` means "use the default" — NOT `not body`. An empty dict is
    falsy, and the version that wrote `body or {...}` silently replaced the
    deliberately-invalid empty body with a valid one, so the test that was meant
    to prove failures are not stored never sent a failing request."""
    client = _client_for(user)
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    payload = {"plan": "STARTER"} if body is None else body
    return client.post(CHECKOUT, payload, format="json", **headers)


# ── the replay ────────────────────────────────────────────────────────────────


def test_a_retry_with_the_same_key_replays_the_first_response(org):
    key = str(uuid.uuid4())
    first = _post(org.admin, key)
    second = _post(org.admin, key)

    assert second.status_code == first.status_code
    assert second.json() == first.json()
    assert second["Idempotency-Replayed"] == "true"
    # The first response is not marked as a replay, because it was not one.
    assert "Idempotency-Replayed" not in first


def test_the_work_is_only_done_once(org):
    """The point of the whole mechanism. Checkout is the clearest case — a second
    execution is a second charge — but the same holds for approve, which would
    otherwise write two approval records for one human decision."""
    key = str(uuid.uuid4())
    _post(org.admin, key)
    _post(org.admin, key)
    _post(org.admin, key)

    with tenant_context(org.tenant):
        assert IdempotencyRecord.objects.filter(key=key).count() == 1


def test_field_order_in_the_body_does_not_defeat_the_key(org):
    """A JSON object serialised in a different order is the same request. If the
    fingerprint disagreed, a client that rebuilt its payload between attempts
    would get a 409 for a retry that was entirely correct."""
    key = str(uuid.uuid4())
    first = _post(org.admin, key, {"plan": "STARTER", "cycle": "MONTHLY"})
    second = _post(org.admin, key, {"cycle": "MONTHLY", "plan": "STARTER"})

    assert second.status_code == first.status_code
    assert second.get("Idempotency-Replayed") == "true"


# ── the refusals ──────────────────────────────────────────────────────────────


def test_reusing_a_key_for_a_different_request_is_a_409(org):
    """Answering it with the stored response would answer a question the client
    did not ask — and the client, believing it succeeded, would never notice the
    second operation never happened."""
    key = str(uuid.uuid4())
    _post(org.admin, key, {"plan": "STARTER"})
    clash = _post(org.admin, key, {"plan": "ENTERPRISE"})

    assert clash.status_code == 409
    assert clash.json()["code"] == "idempotency_key_reused"


def test_a_key_does_not_cross_users(org):
    """A replayed response is a response body about somebody's records. Sharing
    it across users because they happened to pick the same key would be a
    disclosure, not just a bug."""
    key = str(uuid.uuid4())
    _post(org.admin, key)
    other = _post(org.other_admin, key)

    assert other.get("Idempotency-Replayed") is None
    with tenant_context(org.tenant):
        assert IdempotencyRecord.objects.filter(key=key).count() == 2


def test_a_key_does_not_cross_tenants(org):
    """Two tenants can generate the same UUID. Nothing about that may connect
    them."""
    other_tenant = TenantFactory(slug="globex", name="Globex")
    stranger = UserFactory(tenant=other_tenant, email="admin@globex.test", role="ADMIN")

    key = str(uuid.uuid4())
    _post(org.admin, key)
    theirs = _post(stranger, key)

    assert theirs.get("Idempotency-Replayed") is None


# ── what is NOT stored ────────────────────────────────────────────────────────


def test_a_failed_request_is_not_stored(org):
    """A 4xx must not pin the client to its own mistake. A client that gets a
    validation error fixes the body and retries — usually with the same key,
    because from its point of view the operation never happened."""
    key = str(uuid.uuid4())
    bad = _post(org.admin, key, {})           # no plan → 400
    assert bad.status_code == 400

    with tenant_context(org.tenant):
        assert IdempotencyRecord.objects.filter(key=key).count() == 0

    # And the corrected retry under the same key goes through rather than 409ing.
    fixed = _post(org.admin, key, {"plan": "STARTER"})
    assert fixed.status_code != 409


def test_without_a_key_the_endpoint_is_unchanged(org):
    """Opt-in. A required header would have broken every existing client the
    moment it shipped."""
    first = _post(org.admin)
    second = _post(org.admin)

    assert first.status_code == second.status_code
    assert "Idempotency-Replayed" not in second
    with tenant_context(org.tenant):
        assert IdempotencyRecord.objects.count() == 0


# ── coverage ──────────────────────────────────────────────────────────────────


def test_the_four_named_operations_all_support_a_key():
    """Named rather than inferred, so that dropping the decorator from one of them
    fails here rather than silently reopening the double-submit."""
    from apps.billing.views import CheckoutView
    from apps.core.idempotency import IDEMPOTENT_ATTR
    from apps.reviews.views import ReviewApproveView, ReviewFinalizeView, ReviewSubmitView

    for view in (CheckoutView, ReviewSubmitView, ReviewApproveView, ReviewFinalizeView):
        assert getattr(view, IDEMPOTENT_ATTR, False), (
            f"{view.__name__} is no longer idempotent"
        )


def test_it_works_on_a_view_that_defines_its_own_post():
    """The bug this replaced. A MIXIN cannot intercept a method the class defines
    itself — Python resolves ``self.post`` to the class attribute before it looks
    at any base, however early in the MRO that base sits. ``CheckoutView`` defines
    ``post``, so the mixin version accepted the header, ignored it entirely, and
    executed the work twice while looking perfectly wired.

    This asserts the property directly on that view rather than trusting the MRO.
    """
    from apps.billing.views import CheckoutView

    assert "post" in vars(CheckoutView)
    assert CheckoutView.post.__wrapped__ is not None


def test_it_works_on_a_view_that_inherits_post_from_a_base():
    """The other shape: ``_TransitionView`` owns ``post`` and the three review
    endpoints inherit it. The wrapper must land on the SUBCLASS, so the base and
    its other subclasses (start-edit, reject) are untouched."""
    from apps.core.idempotency import IDEMPOTENT_ATTR
    from apps.reviews.views import ReviewApproveView, ReviewRejectView

    assert "post" in vars(ReviewApproveView)
    assert not getattr(ReviewRejectView, IDEMPOTENT_ATTR, False)
