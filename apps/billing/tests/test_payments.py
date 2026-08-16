"""
PROD_C — payments (Stripe + Razorpay, TEST MODE). Proofs of the trust boundary:
a paid plan stays PENDING until a SIGNATURE-VERIFIED webhook activates it; an
invalid signature is rejected; duplicate webhooks are idempotent; the client can
never self-activate; a webhook for tenant A never touches tenant B; and the
internal flip still works when payments are off.
"""
import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.billing.models import Invoice, Payment, PaymentEvent, Subscription
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

CHECKOUT = "/api/billing/checkout"
STRIPE_HOOK = "/api/billing/webhooks/stripe"
RZP_HOOK = "/api/billing/webhooks/razorpay"
WH_SECRET = "whsec_test_123"
RZP_SECRET = "rzp_whsec_test_123"

PAY_ON = {"PAYMENTS_ENABLED": True, "STRIPE_WEBHOOK_SECRET": WH_SECRET,
          "RAZORPAY_WEBHOOK_SECRET": RZP_SECRET}


def _admin_client(tenant):
    admin = UserFactory(tenant=tenant, email="admin@acme.test", role="ADMIN")
    access, _ = issue_tokens_for_user(admin)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


def _stripe_body(tenant_id, plan="PROFESSIONAL", cycle="MONTHLY", event_id="evt_1",
                 rtype="checkout.session.completed", amount=4900):
    return json.dumps({
        "id": event_id, "type": rtype,
        "data": {"object": {
            "metadata": {"tenant_id": str(tenant_id), "plan": plan, "cycle": cycle},
            "amount_total": amount, "currency": "usd", "payment_intent": "pi_1",
        }},
    }).encode()


def _stripe_sig(body: bytes, secret=WH_SECRET, ts="1700000000"):
    signed = f"{ts}.".encode() + body
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def _post_stripe(body, sig):
    return APIClient().post(STRIPE_HOOK, data=body, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE=sig)


@override_settings(**PAY_ON)
def test_paid_plan_pending_until_verified_webhook_activates():
    t = TenantFactory(slug="acme")
    client = _admin_client(t)

    # 1) Checkout cannot take money (C8), so it refuses rather than handing back a
    #    fabricated session. Either way the plan does not change here — which is
    #    the half of this test that matters and is unchanged.
    r = client.post(CHECKOUT, {"plan": "PROFESSIONAL", "cycle": "MONTHLY"}, format="json")
    assert r.status_code == 501, r.content
    with tenant_context(t.id):
        # Not activated — no paid subscription exists until the webhook.
        assert not Subscription.objects.filter(plan="PROFESSIONAL").exists()

    # 2) The verified webhook activates it + records an invoice.
    body = _stripe_body(t.id)
    resp = _post_stripe(body, _stripe_sig(body))
    assert resp.status_code == 200, resp.content
    with tenant_context(t.id):
        assert Subscription.objects.get().plan == "PROFESSIONAL"
        inv = Invoice.objects.get()
        assert inv.total == 4900 and inv.currency == "USD"
        assert Payment.objects.get().status == Payment.Status.SUCCEEDED


@override_settings(**PAY_ON)
def test_invalid_signature_is_rejected_and_changes_nothing():
    t = TenantFactory(slug="acme")
    body = _stripe_body(t.id)
    resp = _post_stripe(body, "t=1700000000,v1=deadbeef")  # forged
    assert resp.status_code == 401
    with tenant_context(t.id):
        assert not Subscription.objects.filter(plan="PROFESSIONAL").exists()
        assert PaymentEvent.objects.count() == 0
        assert Invoice.objects.count() == 0


@override_settings(**PAY_ON)
def test_duplicate_webhook_is_idempotent():
    t = TenantFactory(slug="acme")
    body = _stripe_body(t.id, event_id="evt_dup")
    sig = _stripe_sig(body)
    first = _post_stripe(body, sig)
    second = _post_stripe(body, sig)
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate_ignored"
    with tenant_context(t.id):
        assert Invoice.objects.count() == 1
        assert Payment.objects.count() == 1


@override_settings(**PAY_ON)
def test_webhook_for_tenant_a_never_touches_tenant_b():
    a = TenantFactory(slug="acme")
    b = TenantFactory(slug="globex")
    body = _stripe_body(a.id, plan="ENTERPRISE", event_id="evt_a", amount=19900)
    _post_stripe(body, _stripe_sig(body))
    with tenant_context(a.id):
        assert Subscription.objects.get().plan == "ENTERPRISE"
    with tenant_context(b.id):
        # b was never provisioned by a's webhook.
        assert not Subscription.objects.filter(plan="ENTERPRISE").exists()
        assert Invoice.objects.count() == 0


@override_settings(**PAY_ON)
def test_client_cannot_self_activate_via_checkout():
    """The property under test is unchanged: a client cannot talk itself onto a
    paid plan. Only the mechanism moved — checkout used to answer "pending" with a
    fabricated session id, and now answers 501 because no payment can be taken
    (C8). Either way the subscription does not change without a signed webhook."""
    t = TenantFactory(slug="acme")
    client = _admin_client(t)
    r = client.post(CHECKOUT, {"plan": "ENTERPRISE", "cycle": "MONTHLY",
                               "amount": 1, "paid": True}, format="json")
    assert r.status_code == 501
    assert r.json()["code"] == "payments_not_implemented"
    with tenant_context(t.id):
        assert not Subscription.objects.filter(plan="ENTERPRISE").exists()


@override_settings(**PAY_ON)
def test_checkout_does_not_hand_back_a_fake_session():
    """The regression this guards: create_checkout used to return a plausible
    `cs_test_...` id and a checkout URL that went nowhere, with no signal that no
    money had moved. A fake that looks real is the shape of bug that reaches a
    customer."""
    t = TenantFactory(slug="acme")
    r = _admin_client(t).post(
        CHECKOUT, {"plan": "ENTERPRISE", "cycle": "MONTHLY"}, format="json"
    )
    body = r.json()
    assert r.status_code == 501
    assert "session_id" not in body
    assert "checkout_url" not in body
    # And it says what to do instead.
    assert "administrator" in body["detail"].lower()


@override_settings(**PAY_ON)
def test_failed_payment_moves_to_past_due():
    t = TenantFactory(slug="acme")
    # First activate so ACTIVE → PAST_DUE is a legal transition.
    ok = _stripe_body(t.id, event_id="evt_ok")
    _post_stripe(ok, _stripe_sig(ok))
    fail = _stripe_body(t.id, event_id="evt_fail", rtype="invoice.payment_failed")
    _post_stripe(fail, _stripe_sig(fail))
    with tenant_context(t.id):
        assert Subscription.objects.get().status == Subscription.Status.PAST_DUE


@override_settings(**PAY_ON)
def test_razorpay_signature_and_activation():
    t = TenantFactory(slug="acme")
    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": "pay_rzp_1", "amount": 399000, "currency": "INR",
            "notes": {"tenant_id": str(t.id), "plan": "PROFESSIONAL", "cycle": "MONTHLY"},
        }}},
    }).encode()
    sig = hmac.new(RZP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    resp = APIClient().post(RZP_HOOK, data=body, content_type="application/json",
                            HTTP_X_RAZORPAY_SIGNATURE=sig)
    assert resp.status_code == 200, resp.content
    with tenant_context(t.id):
        assert Subscription.objects.get().plan == "PROFESSIONAL"
        assert Payment.objects.get().currency == "INR"


def test_payments_disabled_activates_immediately():
    # Default settings: PAYMENTS_ENABLED False → internal flip still works.
    t = TenantFactory(slug="acme")
    client = _admin_client(t)
    r = client.post(CHECKOUT, {"plan": "PROFESSIONAL"}, format="json")
    assert r.json()["status"] == "activated" and r.json()["paid"] is False
    with tenant_context(t.id):
        assert Subscription.objects.get().plan == "PROFESSIONAL"


@override_settings(**PAY_ON)
def test_free_starter_plan_needs_no_payment():
    t = TenantFactory(slug="acme")
    client = _admin_client(t)
    r = client.post(CHECKOUT, {"plan": "STARTER"}, format="json")
    assert r.json()["status"] == "activated" and r.json()["paid"] is False
