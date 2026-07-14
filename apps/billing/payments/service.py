"""Payments orchestration: start a checkout, and process a verified webhook by
driving the EXISTING Subscription state machine (set_plan / set_subscription_status).
The webhook is the single source of truth — nothing here trusts the client."""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from ..models import BillingProfile, Invoice, Payment, PaymentEvent, Subscription
from ..services import (
    get_or_create_subscription,
    set_plan,
    set_subscription_status,
)
from . import catalog
from .providers import NormalizedEvent, get_provider

logger = logging.getLogger("pms.billing.payments")


def get_or_create_billing_profile(tenant_id: str) -> BillingProfile:
    with tenant_context(tenant_id):
        profile = BillingProfile.objects.filter(tenant_id=tenant_id).first()
        if profile is None:
            profile = BillingProfile.objects.create(tenant_id=tenant_id)
        return profile


def _next_invoice_number(tenant_id: str) -> str:
    n = Invoice.objects.filter(tenant_id=tenant_id).count() + 1
    return f"INV-{n:05d}"


class CheckoutError(Exception):
    """A checkout could not be started (unknown plan/price)."""


def start_checkout(*, tenant, actor, plan: str, cycle: str) -> dict:
    """Begin a plan change. Behaviour depends on PAYMENTS_ENABLED + whether the
    plan is paid:

    * PAYMENTS_ENABLED False, or a FREE plan  → activate immediately (the internal
      admin flip; clearly marked ``paid=False``). This preserves QA/dev behaviour.
    * PAYMENTS_ENABLED True and a PAID plan    → create a provider checkout and
      return its URL; the subscription stays PENDING until the webhook confirms.
    """
    tid = str(tenant.id if hasattr(tenant, "id") else tenant)
    plan = (plan or "").upper()
    cycle = (cycle or "MONTHLY").upper()
    if plan not in catalog.PRICES:
        raise CheckoutError(f"Unknown plan: {plan}")
    if cycle not in catalog.BILLING_CYCLES:
        raise CheckoutError(f"Unknown billing cycle: {cycle}")

    profile = get_or_create_billing_profile(tid)
    currency = profile.currency
    amount = catalog.price_for(plan, cycle, currency)
    if amount is None:
        raise CheckoutError(f"No price for {plan}/{cycle}/{currency}.")

    # Free plan, or payments turned off → activate immediately (no money movement).
    if not settings.PAYMENTS_ENABLED or amount == 0:
        set_plan(tid, plan, actor=actor)
        record(
            action="billing.plan_activated_no_payment", actor=actor,
            target_type="subscription", target_id="",
            metadata={"plan": plan, "cycle": cycle, "reason": (
                "free_plan" if amount == 0 else "payments_disabled")},
            tenant=tid,
        )
        return {"status": "activated", "paid": False, "plan": plan}

    # Paid plan with payments on → create the checkout; DO NOT change the plan yet.
    provider = get_provider(profile.provider)
    if provider is None:
        raise CheckoutError(f"No payment provider configured: {profile.provider}")
    session = provider.create_checkout(
        tenant_id=tid, plan=plan, cycle=cycle, amount=amount, currency=currency,
        metadata={"tenant_id": tid, "plan": plan, "cycle": cycle},
    )
    record(
        action="billing.checkout_started", actor=actor, target_type="subscription",
        target_id="", metadata={"plan": plan, "cycle": cycle, "provider": profile.provider,
                                "session_id": session.get("session_id")},
        tenant=tid,
    )
    return {
        "status": "pending", "paid": True, "plan": plan, "cycle": cycle,
        "provider": profile.provider, "amount": amount, "currency": currency,
        "checkout_url": session.get("checkout_url"), "session_id": session.get("session_id"),
    }


def _redact(event: NormalizedEvent) -> dict:
    return {
        "type": event.raw_type, "normalized": event.type, "plan": event.plan,
        "cycle": event.cycle, "amount": event.amount, "currency": event.currency,
        "payment_id": event.payment_id,
    }


def process_webhook(provider_name: str, *, headers, raw_body: bytes) -> tuple[int, dict]:
    """Verify + process a provider webhook. Returns ``(http_status, body)``.

    401 on a missing/invalid signature (no mutation). 200 for everything else,
    including duplicates (idempotent) and events for unknown tenants (ignored) —
    a non-2xx would make the provider retry a fundamentally un-actionable event."""
    provider = get_provider(provider_name)
    if provider is None:
        return 404, {"detail": "Unknown provider."}

    event = provider.verify_and_parse(headers=headers, raw_body=raw_body)
    if event is None:
        return 401, {"detail": "Invalid or missing signature."}

    if not event.tenant_id or not event.event_id:
        logger.warning("payment webhook without tenant/event id (%s)", event.raw_type)
        return 200, {"status": "ignored_no_tenant"}

    tenant = Tenant.objects.filter(id=event.tenant_id).first()
    if tenant is None:
        logger.warning("payment webhook for unknown tenant %s", event.tenant_id)
        return 200, {"status": "ignored_unknown_tenant"}

    with tenant_context(tenant.id):
        # Idempotency: (provider, event_id) is unique. A second delivery finds the
        # existing row and no-ops.
        pe, created = PaymentEvent.objects.get_or_create(
            provider=event.provider, event_id=event.event_id,
            defaults={"type": event.raw_type, "payload": _redact(event),
                      "status": PaymentEvent.Status.PENDING, "tenant_id": tenant.id},
        )
        if not created:
            return 200, {"status": "duplicate_ignored"}

        try:
            with transaction.atomic():
                self_status = _apply_event(tenant, event)
                pe.status = self_status
                pe.processed_at = timezone.now()
                pe.save(update_fields=["status", "processed_at"])
        except Exception:  # noqa: BLE001 — never 500 to the provider; record + move on
            logger.exception("payment webhook processing failed for %s", event.event_id)
            pe.status = PaymentEvent.Status.ERROR
            pe.save(update_fields=["status"])
            return 200, {"status": "error_recorded"}

    return 200, {"status": "processed", "event": event.type}


def _apply_event(tenant, event: NormalizedEvent) -> str:
    """Map a normalized event onto the subscription state machine + money records.
    Returns the PaymentEvent.Status to persist. Runs inside tenant_context + atomic."""
    tid = str(tenant.id)
    if event.type == "paid":
        if event.plan:
            set_plan(tid, event.plan.upper(), actor=None)  # entitlement flips
        _ensure_active(tid)
        payment = Payment.objects.create(
            tenant_id=tid, provider=event.provider, provider_payment_id=event.payment_id,
            amount=event.amount, currency=event.currency, status=Payment.Status.SUCCEEDED,
            subscription=get_or_create_subscription(tid),
        )
        invoice = Invoice.objects.create(
            tenant_id=tid, number=_next_invoice_number(tid), payment=payment,
            line_items=[{"plan": event.plan, "cycle": event.cycle, "amount": event.amount}],
            total=event.amount, currency=event.currency,
        )
        record(
            action="billing.payment_succeeded", actor=None, target_type="invoice",
            target_id=invoice.id, metadata={"plan": event.plan, "amount": event.amount,
                                            "currency": event.currency, "number": invoice.number},
            tenant=tid,
        )
        return PaymentEvent.Status.PROCESSED

    if event.type == "failed":
        _safe_status(tid, Subscription.Status.PAST_DUE)
        Payment.objects.create(
            tenant_id=tid, provider=event.provider, provider_payment_id=event.payment_id,
            amount=event.amount, currency=event.currency, status=Payment.Status.FAILED,
            subscription=get_or_create_subscription(tid),
        )
        record(action="billing.payment_failed", actor=None, target_type="subscription",
               target_id="", metadata={"amount": event.amount}, tenant=tid)
        return PaymentEvent.Status.PROCESSED

    if event.type == "cancelled":
        _safe_status(tid, Subscription.Status.CANCELLED)
        record(action="billing.subscription_cancelled", actor=None,
               target_type="subscription", target_id="", metadata={}, tenant=tid)
        return PaymentEvent.Status.PROCESSED

    if event.type == "refunded":
        Payment.objects.create(
            tenant_id=tid, provider=event.provider, provider_payment_id=event.payment_id,
            amount=event.amount, currency=event.currency, status=Payment.Status.REFUNDED,
            subscription=get_or_create_subscription(tid),
        )
        # Entitlement change on refund is a HUMAN decision (per design) — audit only.
        record(action="billing.refund_recorded", actor=None, target_type="subscription",
               target_id="", metadata={"amount": event.amount}, tenant=tid)
        return PaymentEvent.Status.PROCESSED

    return PaymentEvent.Status.IGNORED


def _ensure_active(tid: str):
    sub = get_or_create_subscription(tid)
    if sub.status != Subscription.Status.ACTIVE:
        _safe_status(tid, Subscription.Status.ACTIVE)


def _safe_status(tid: str, status: str):
    """Move status if the transition is allowed; otherwise leave it (never raise —
    a webhook must not fail because the local state machine forbids the move)."""
    from ..services import InvalidSubscriptionTransition

    try:
        set_subscription_status(tid, status, actor=None)
    except InvalidSubscriptionTransition:
        logger.info("skipped disallowed webhook-driven transition → %s (tenant=%s)", status, tid)
