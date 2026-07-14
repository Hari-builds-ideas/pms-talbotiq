# PAYMENTS_VERIFIED — Stripe + Razorpay (TEST MODE) build

Implements `docs/PHASE2/PAYMENTS_DESIGN.md` against the existing
`apps/billing` Plan/Subscription model. **Test-mode only** — placeholders in
`.env.example`; the human adds live keys at go-live (steps below).

## What was built
- **Models** (additive, tenant-scoped): `BillingProfile` (1:1 provider/currency/
  customer id), `PaymentEvent` (append-only, `(provider,event_id)` UNIQUE →
  idempotency), `Payment`, `Invoice` (sequential number per tenant). Migration
  `billing/0004_*`.
- **Provider port** `apps/billing/payments/providers.py` — `PaymentProvider` ABC +
  `StripeProvider` + `RazorpayProvider`. Signature verification is **real and
  self-contained** (HMAC-SHA256; Stripe `t=…,v1=…`, Razorpay `X-Razorpay-Signature`).
  `create_checkout` is SDK-optional (returns a deterministic test descriptor; the
  live SDK call is a marked TODO for go-live — the trust boundary is the webhook,
  not the checkout).
- **Service** `apps/billing/payments/service.py` — `start_checkout` (server-side
  price from `catalog.py`, never the client) and `process_webhook` (verify →
  idempotent record → drive the EXISTING `set_plan`/`set_subscription_status` →
  record `Payment` + `Invoice` → audit).
- **Endpoints** (under `/api/billing/`): `payments-config`, `checkout`, `invoices`
  (all MANAGE_TENANT/admin), and PUBLIC signature-verified `webhooks/stripe` +
  `webhooks/razorpay`.
- **PAYMENTS_ENABLED** gate: off (default) → the internal admin plan flip still
  works (QA/dev), clearly marked `paid=false`; on → a paid plan stays PENDING
  until the verified webhook.
- **Frontend**: plan-picker (monthly/annual) → `checkout` → redirect to the hosted
  URL when pending, toast when applied; a "Billing history" invoices list. No price
  or entitlement logic client-side.

## Verified (automated, `apps/billing/tests/test_payments.py`, 9/9)
- Paid plan **pending until** a signature-verified webhook, which activates it +
  records an invoice.
- **Invalid signature → 401**, nothing mutated, no PaymentEvent/Invoice written.
- **Idempotent**: the same event twice → one activation, one invoice
  (`duplicate_ignored` on the second).
- **Cross-tenant**: a webhook carrying tenant A's metadata never touches tenant B.
- **No client-trusted activation**: the client's `amount`/`paid` are ignored; the
  server price is used and the plan stays pending.
- **Failed** payment → `PAST_DUE`; **Razorpay** signature + activation; free
  STARTER + payments-off → immediate apply.
- Live: `payments-config` 200 (admin), `invoices` 200, employee → 403, unsigned
  webhook → 401.

## Go-live steps (human, supervised)
1. Create Stripe (and/or Razorpay) accounts; get **test** keys first.
2. Set env (secret manager, never committed):
   `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
3. Register the webhook URLs at each provider:
   `https://<domain>/api/billing/webhooks/stripe` and `…/razorpay`; copy the
   signing secret into `*_WEBHOOK_SECRET`.
4. Implement the `create_checkout` SDK call (marked TODO in `providers.py`) using
   the provider SDK + test key, and map the catalogue prices to real provider
   Prices/Plans.
5. Set `PAYMENTS_ENABLED=true`. Test with the provider's **test cards** +
   webhook/CLI: upgrade → checkout → webhook → activation → invoice.
6. Only after test-mode passes end to end, swap in **live** keys during go-live.

## Known-staged
- `create_checkout` returns a test descriptor until the SDK call is added (step 4).
- Reconciliation Celery beat job (design §5) and refund admin endpoint are
  follow-ups; refunds are recorded from webhooks (entitlement change stays a human
  decision, per design).
