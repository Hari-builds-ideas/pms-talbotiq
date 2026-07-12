# PAYMENTS_DESIGN — Stripe (global) + Razorpay (India) · **DESIGN ONLY, DO NOT BUILD**

> ⚠ **Deliberately NOT implemented in the unattended run.** Payments touch real money; this design is
> for human review, then a daylight build using the prompt at the end. The internal
> subscription/plan model it plugs into IS built (LANE 1 item 4 — `apps/billing`).

## 0. What already exists (the seam this plugs into)
- `apps/billing`: per-tenant `Entitlement` + packs, feature flags served by
  `GET /api/billing/my-features`, seat logic (atomic), `requires_entitlement` server gates.
- LANE 1 adds `Plan` (STARTER/PROFESSIONAL/ENTERPRISE) + `Subscription`
  (tenant → plan; `trial|active|past_due|grace|cancelled|expired`) with **internal, admin-driven**
  transitions. Payments' ONLY job later: drive those same transitions from verified money events.
  **The entitlement/feature system never talks to a gateway directly.**

## 1. Providers & why two
- **Stripe** — global cards/wallets, strong subscription primitives (Products/Prices, Customer,
  Subscription, webhooks). Primary for non-India tenants.
- **Razorpay** — India (INR pricing, UPI/netbanking/cards, e-mandates for recurring). Primary for
  India-billing tenants.
- One **`PaymentProvider` port** (mirror the LLM gateway pattern): `create_checkout(tenant, plan,
  cycle)`, `verify_webhook(headers, body)`, `parse_event(raw) → NormalizedEvent`,
  `cancel(subscription)`, `refund(payment, amount)`. Concrete adapters `stripe_provider.py`,
  `razorpay_provider.py`. Tenant's provider chosen by billing country (stored on the tenant's billing
  profile).

## 2. Data model (additive)
```
BillingProfile(tenant 1:1): provider, currency, country, tax_id?, billing_email,
                            provider_customer_id (Stripe customer / Razorpay customer)
PaymentEvent(append-only): provider, event_id (UNIQUE — idempotency), type, payload(redacted),
                           received_at, processed_at, status(pending|processed|ignored|error)
Payment: tenant, subscription, provider, provider_payment_id, amount, currency,
         status(succeeded|failed|refunded|partially_refunded), created_at
Invoice: tenant, number(seq per tenant), payment?, period, line_items(json), total, currency,
         pdf_object_key?, issued_at
```
All tenant-scoped (`TenantScopedModel`), additive migrations, audit `record()` on every state change.

## 3. The money flow (end-to-end)
1. Admin picks a plan in the UI → `POST /api/billing/checkout {plan, cycle}` (server looks up the
   PRICE — **never from the client**).
2. Server creates the provider checkout (Stripe Checkout Session / Razorpay Subscription+Order) with
   `tenant_id` + `plan` in provider metadata; returns only the redirect URL/session id.
3. User pays on the PROVIDER'S page (PCI stays with the provider — card data never touches us).
4. **Webhook is the single source of truth**: `POST /api/billing/webhooks/{stripe|razorpay}` →
   verify signature (Stripe `Stripe-Signature` HMAC w/ endpoint secret; Razorpay
   `X-Razorpay-Signature` HMAC-SHA256 w/ webhook secret) → store `PaymentEvent` (unique `event_id` →
   **idempotent replay-safe**) → enqueue a Celery task to process.
5. Processing maps normalized events → the LANE-1 subscription state machine:
   `checkout.completed/subscription.activated` → `Subscription.activate(plan)` (entitlements flip
   server-side, effective immediately) · `invoice.paid` → extend period + generate `Invoice` ·
   `invoice.payment_failed` → `past_due` (+ provider retry schedule; ours: 3 retries over 7 days) →
   `grace` (configurable, e.g. 7 days, features degrade to read-only) → `expired` ·
   `subscription.cancelled` → `cancelled` at period end · `charge.refunded` → record refund + audit
   (entitlement change is a HUMAN decision, not automatic).
6. The frontend NEVER decides anything: after checkout it polls `GET /api/billing/my-features` /
   subscription status, which reflect only webhook-verified truth.

## 4. What must NEVER happen on the frontend (hard rules)
- No prices, plan contents, or entitlements trusted from the client — server catalogue only.
- No secret keys in the SPA (publishable/checkout keys only); webhook secrets server-side only.
- No browser-side "mark paid": success-redirect pages are cosmetic; ONLY a signature-verified webhook
  mutates a subscription.
- No card data on our servers, ever (provider-hosted fields/pages only).
- No entitlement change from an unverified or replayed event (signature + unique event_id + audit).

## 5. Security & ops checklist
Webhook endpoints: no auth-session required but signature-verified + IP-logged + rate-limited;
secrets in the secrets manager (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `RAZORPAY_KEY_ID/SECRET`,
`RAZORPAY_WEBHOOK_SECRET` — placeholders already sketched in D5); clock-skew tolerance on signatures;
Celery processing with retry + dead-letter status; reconciliation job (daily: compare provider
subscriptions ↔ ours, alert on drift); refunds only via an admin endpoint (capability
`manage_tenant`) that calls the provider — never free-form; taxes: design for Stripe Tax /
Razorpay GST fields later (store tax lines on Invoice from day one); invoices numbered sequentially
per tenant, PDF to object storage; every transition `record()`-audited.

## 6. Rollout order
Sandbox keys → Stripe first (test-mode e2e: checkout → webhook → activation → my-features flip) →
invoice generation → failure/grace path → Razorpay adapter → reconciliation job → go-live behind a
per-tenant `billing_live` flag.

---

## Ready-to-paste implementation prompt (for the human-supervised build)

```
Read docs/PHASE2/PAYMENTS_DESIGN.md and implement it exactly, in this order, committing per step and
keeping all tests green. Ground everything in the existing code: the LANE-1 Plan/Subscription model in
apps/billing (drive ITS transitions — do not create a parallel state), TenantScopedModel for every new
model, the audit record() on every state change, and the PaymentProvider port pattern mirroring
apps/ai/providers.py.

1. Models + additive migrations: BillingProfile, PaymentEvent (unique event_id), Payment, Invoice.
2. The PaymentProvider ABC + StripeProvider (test mode): create_checkout, verify_webhook, parse_event.
3. POST /api/billing/checkout (capability manage_tenant; server-side price catalogue) and
   POST /api/billing/webhooks/stripe (signature verify → store event idempotently → Celery task).
4. The processing task: normalized events → Subscription transitions (activate / invoice.paid+Invoice /
   payment_failed → past_due → grace → expired / cancelled / refund recorded). Tests for EVERY
   transition including replayed and forged webhooks (must be rejected + audited).
5. Frontend: plan-picker → checkout redirect → post-checkout polling of my-features; a billing page
   showing subscription status + invoices. No price or entitlement logic client-side.
6. RazorpayProvider behind the same port + its webhook route + tests.
7. Reconciliation Celery beat task + drift alert metric.
Never: client-trusted prices, secrets in the SPA, entitlement changes without a verified webhook,
destructive migrations. Extend .env.example with the new placeholders. Finish with an end-to-end
test-mode walkthrough documented in docs/PHASE2/PAYMENTS_VERIFIED.md.
```
