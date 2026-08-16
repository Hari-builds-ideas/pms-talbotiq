# PROD_C_PAYMENTS.md — real subscription + payments pipeline (TEST MODE)

**Goal:** a plan change or seat increase requires REAL payment before the entitlement activates — built
and verified end to end against **Stripe + Razorpay TEST MODE**. The human flips to live keys later,
supervised. Follow the existing design in `docs/PHASE2/PAYMENTS_DESIGN.md` — this is that build.

## Absolute safety rules for this file
- **TEST MODE ONLY.** Use Stripe/Razorpay **test** API keys via env placeholders (`STRIPE_SECRET_KEY`,
  `STRIPE_WEBHOOK_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, etc. — all placeholders in
  `.env.example`). NEVER a live key, NEVER a real charge. Verify with test card numbers.
- **Server-side is the source of truth.** The entitlement activates ONLY when the server confirms payment
  via a **verified webhook** (signature-checked). NEVER trust the client/browser to say "paid". No secret
  keys in the SPA.
- Never commit any key. Never log into the human's Stripe/Razorpay dashboard — build + document the steps.

## 1. Build on the existing plan model
The internal Subscription/Plan model already exists (Starter/Professional/Enterprise, statuses trial/
active/past_due/grace/cancelled/expired). Extend it with the payment layer — don't rebuild it.

## 2. Checkout + activation flow
- When an admin changes plan or adds seats and `PAYMENTS_ENABLED=true`: create a checkout/order server-side
  (Stripe Checkout Session or Razorpay Order), return it to the client to complete payment in the
  provider's hosted UI (never handle card data yourself — PCI stays with the provider).
- The entitlement/plan/seat change stays PENDING until the provider confirms payment via webhook.
- On the verified webhook (payment succeeded): activate the plan/seats, record the invoice, update the
  Subscription status. On failure/cancel: leave the old entitlement unchanged and surface a clear state.

## 3. Webhooks (the trust boundary)
- Implement Stripe and Razorpay webhook endpoints with **signature verification** (reject unsigned/invalid).
- Idempotent: the same event delivered twice does not double-activate or double-charge.
- Handle: payment succeeded, payment failed, subscription renewed, subscription cancelled, refund. Update
  the Subscription state machine accordingly (past_due → grace → expired etc. per PAYMENTS_DESIGN).
- Audit every payment state change (append-only audit log).

## 4. Invoices + billing surfaces
- Generate/store an invoice record per successful payment; expose a billing history to the tenant admin.
- Seat-based pricing: charge per seat; enforce the seat/employee limit server-side; adding seats beyond
  the plan requires payment.

## 5. The PAYMENTS_ENABLED flag
- `PAYMENTS_ENABLED=false` (default): the internal plan flip still works for testing/QA (current behavior),
  clearly marked as "no payment (test)".
- `PAYMENTS_ENABLED=true`: the real checkout+webhook flow is required before any paid entitlement activates.
- Document both, and that production sets it true with live keys (human step).

## 6. Verify end to end (test mode)
- With Stripe test keys + test cards: run the full path — upgrade → checkout → webhook (use the provider's
  test webhook / CLI) → entitlement activates → invoice recorded. Same for Razorpay test mode.
- Add automated tests: webhook signature verification (valid activates, invalid rejected), idempotency,
  pending-until-webhook, no client-trusted activation, cross-tenant (a webhook for tenant A never touches
  tenant B).

## Rules
- Test mode only; server-verified; never client-trusted; idempotent webhooks; audit everything; tenant-
  isolated; tests green. Placeholders only in `.env.example`.
- Document the exact human steps to go live later (add live keys, register the live webhook URL, flip
  PAYMENTS_ENABLED) — do NOT do them.

## Done when
- Real checkout + verified-webhook activation works in Stripe AND Razorpay test mode; entitlement never
  activates without a verified payment; invoices recorded; PAYMENTS_ENABLED gates it; full tests green.
  Logged in PROD_PROGRESS.md with the go-live steps for the human.
