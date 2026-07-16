"""Payment provider port + Stripe/Razorpay adapters (mirrors apps/ai/providers.py).

The signature verification is REAL, self-contained (no SDK needed) and is the
security boundary the tests exercise. ``create_checkout`` is SDK-optional: with
the provider SDK + a test key it would call the live-test API; without it, it
returns a deterministic test descriptor so the flow is exercisable end to end and
the human wires the real SDK call at go-live (marked TODO below)."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings


@dataclass
class NormalizedEvent:
    """A provider-agnostic view of a webhook event, after signature verification."""
    provider: str
    event_id: str
    type: str            # one of: paid | failed | cancelled | refunded | ignored
    tenant_id: str | None
    plan: str | None
    cycle: str | None
    amount: int          # minor units
    currency: str
    payment_id: str
    raw_type: str        # the provider's own event type (for the audit trail)


def _ct_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


class PaymentProvider(ABC):
    name: str = ""

    @abstractmethod
    def create_checkout(self, *, tenant_id, plan, cycle, amount, currency, metadata) -> dict:
        """Create a provider checkout/order server-side. Returns
        ``{provider, session_id, checkout_url, amount, currency}``. NEVER trusts a
        client-supplied price — ``amount`` comes from the server catalogue."""

    @abstractmethod
    def verify_and_parse(self, *, headers, raw_body: bytes) -> NormalizedEvent | None:
        """Verify the webhook signature and parse it. Returns a NormalizedEvent, or
        None if the signature is missing/invalid/expired (caller → 400, no mutation)."""


# ── Stripe ───────────────────────────────────────────────────────────────────
class StripeProvider(PaymentProvider):
    name = "STRIPE"

    def _secret(self) -> str:
        return settings.STRIPE_WEBHOOK_SECRET or ""

    def create_checkout(self, *, tenant_id, plan, cycle, amount, currency, metadata) -> dict:
        # TODO(go-live): with the `stripe` SDK + STRIPE_SECRET_KEY (test), call
        # stripe.checkout.Session.create(mode="subscription", line_items=[...],
        # metadata={tenant_id, plan, cycle}, success_url/cancel_url) and return its
        # id + url. Until then we return a deterministic test descriptor; the
        # trust boundary (the signed webhook) is unchanged either way.
        session_id = f"cs_test_{uuid.uuid4().hex}"
        return {
            "provider": self.name,
            "session_id": session_id,
            "checkout_url": f"https://checkout.stripe.com/test/{session_id}",
            "amount": amount,
            "currency": currency,
        }

    def verify_and_parse(self, *, headers, raw_body: bytes) -> NormalizedEvent | None:
        secret = self._secret()
        sig_header = headers.get("HTTP_STRIPE_SIGNATURE") or headers.get("Stripe-Signature")
        if not secret or not sig_header:
            return None
        # Header: "t=<ts>,v1=<hex>[,v1=<hex>...]"
        parts = dict(
            p.split("=", 1) for p in sig_header.split(",") if "=" in p
        )
        ts = parts.get("t")
        given = parts.get("v1")
        if not ts or not given:
            return None
        signed_payload = f"{ts}.".encode() + raw_body
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not _ct_eq(expected, given):
            return None
        try:
            body = json.loads(raw_body.decode())
        except (ValueError, UnicodeDecodeError):
            return None
        return self._normalize(body)

    def _normalize(self, body: dict) -> NormalizedEvent:
        raw_type = body.get("type", "")
        obj = (body.get("data") or {}).get("object") or {}
        meta = obj.get("metadata") or {}
        type_map = {
            "checkout.session.completed": "paid",
            "invoice.paid": "paid",
            "invoice.payment_failed": "failed",
            "customer.subscription.deleted": "cancelled",
            "charge.refunded": "refunded",
        }
        return NormalizedEvent(
            provider=self.name,
            event_id=str(body.get("id", "")),
            type=type_map.get(raw_type, "ignored"),
            tenant_id=meta.get("tenant_id"),
            plan=meta.get("plan"),
            cycle=meta.get("cycle"),
            amount=int(obj.get("amount_total") or obj.get("amount") or 0),
            currency=str(obj.get("currency") or "usd").upper(),
            payment_id=str(obj.get("payment_intent") or obj.get("id") or ""),
            raw_type=raw_type,
        )


# ── Razorpay ─────────────────────────────────────────────────────────────────
class RazorpayProvider(PaymentProvider):
    name = "RAZORPAY"

    def _secret(self) -> str:
        return settings.RAZORPAY_WEBHOOK_SECRET or ""

    def create_checkout(self, *, tenant_id, plan, cycle, amount, currency, metadata) -> dict:
        # TODO(go-live): with the `razorpay` SDK + RAZORPAY_KEY_ID/SECRET (test),
        # create an Order (notes={tenant_id, plan, cycle}) and return its id; the
        # SPA opens Razorpay Checkout with it. Deterministic test descriptor below.
        order_id = f"order_test_{uuid.uuid4().hex[:18]}"
        return {
            "provider": self.name,
            "session_id": order_id,
            "checkout_url": f"https://api.razorpay.com/test/checkout/{order_id}",
            "amount": amount,
            "currency": currency,
        }

    def verify_and_parse(self, *, headers, raw_body: bytes) -> NormalizedEvent | None:
        secret = self._secret()
        given = headers.get("HTTP_X_RAZORPAY_SIGNATURE") or headers.get("X-Razorpay-Signature")
        if not secret or not given:
            return None
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not _ct_eq(expected, given):
            return None
        try:
            body = json.loads(raw_body.decode())
        except (ValueError, UnicodeDecodeError):
            return None
        return self._normalize(body)

    def _normalize(self, body: dict) -> NormalizedEvent:
        raw_type = body.get("event", "")
        entity = (
            ((body.get("payload") or {}).get("payment") or {}).get("entity") or {}
        )
        notes = entity.get("notes") or {}
        type_map = {
            "payment.captured": "paid",
            "order.paid": "paid",
            "payment.failed": "failed",
            "subscription.cancelled": "cancelled",
            "refund.processed": "refunded",
        }
        return NormalizedEvent(
            provider=self.name,
            # Razorpay events have no top-level id; use the payment id (unique).
            event_id=str(entity.get("id") or body.get("id") or ""),
            type=type_map.get(raw_type, "ignored"),
            tenant_id=notes.get("tenant_id"),
            plan=notes.get("plan"),
            cycle=notes.get("cycle"),
            amount=int(entity.get("amount") or 0),
            currency=str(entity.get("currency") or "INR").upper(),
            payment_id=str(entity.get("id") or ""),
            raw_type=raw_type,
        )


_PROVIDERS = {"STRIPE": StripeProvider(), "RAZORPAY": RazorpayProvider()}


def get_provider(name: str) -> PaymentProvider | None:
    return _PROVIDERS.get((name or "").upper())
