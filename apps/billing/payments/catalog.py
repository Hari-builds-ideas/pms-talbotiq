"""Server-side price catalogue. The client NEVER sends a price — checkout looks
it up here by (plan, cycle, currency). Amounts are in MINOR units (cents/paise).

Prices are illustrative test-mode defaults; the human maps them to real provider
Prices/Plans at go-live. STARTER is free (no checkout needed)."""
from __future__ import annotations

BILLING_CYCLES = ("MONTHLY", "ANNUAL")

# plan → cycle → currency → amount in minor units.
PRICES: dict[str, dict[str, dict[str, int]]] = {
    "STARTER": {
        "MONTHLY": {"USD": 0, "INR": 0},
        "ANNUAL": {"USD": 0, "INR": 0},
    },
    "PROFESSIONAL": {
        "MONTHLY": {"USD": 4900, "INR": 399000},     # $49 / ₹3,990
        "ANNUAL": {"USD": 49000, "INR": 3990000},    # $490 / ₹39,900 (2 months free)
    },
    "ENTERPRISE": {
        "MONTHLY": {"USD": 19900, "INR": 1599000},   # $199 / ₹15,990
        "ANNUAL": {"USD": 199000, "INR": 15990000},
    },
}


def price_for(plan: str, cycle: str, currency: str) -> int | None:
    """Minor-unit price, or None if the (plan, cycle, currency) isn't sold."""
    try:
        return PRICES[plan][cycle][currency.upper()]
    except KeyError:
        return None


def is_paid(plan: str, cycle: str, currency: str) -> bool:
    amount = price_for(plan, cycle, currency)
    return bool(amount and amount > 0)
