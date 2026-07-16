"""Payments (PROD_C) — Stripe + Razorpay in TEST MODE.

The trust boundary is the signature-verified webhook: a paid plan/seat change
only activates when the provider confirms payment. The server owns the price
catalogue; the client never sends a price. See docs/PHASE2/PAYMENTS_DESIGN.md.
"""
