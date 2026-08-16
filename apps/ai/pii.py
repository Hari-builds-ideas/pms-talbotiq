"""
PII scrubbing applied by the LLM gateway to EVERY input before it reaches a
provider (Doc 3 §5 safeguard pipeline).

## What IS redacted, always

* **Email addresses** — any email-like token, anywhere, at any nesting depth.
* **Phone numbers** — 7–15 digit sequences in phone shape, including
  international prefixes and the usual separators. Digit-count bounded at both
  ends so an order value, a year, or a score is not mangled.
* **Employee / payroll / staff IDs** — but only in *labelled* form
  (``employee id: A-1234``, ``EMP #99812``). A bare alphanumeric token cannot be
  told apart from a goal title or a KPI unit, and redacting every one of those
  would destroy the grounding the agent needs.

## What is NOT redacted by default

* **Names.** `apps/ai/evidence.py` puts the subject's first name into a review
  prompt *on purpose* — "write a review of Priya" grounds far better than "write
  a review of the employee", and the reviewer is going to read the output with
  that person's name at the top anyway. Blanket-redacting names would degrade
  every human-read agent to serve a threat model most tenants have not asked for.

  Tenants who HAVE asked for it set ``PII_SCRUB_NAMES=True``, which replaces the
  display names of that tenant's users with role tokens (``[EMPLOYEE]``,
  ``[MANAGER]``, ``[HRBP]``, ``[ADMIN]``). That needs the tenant to look the
  names up, so pass one: ``scrub(value, tenant=...)``.

* **Job titles, departments, performance content.** These are the substance of
  what the agents reason about. A tenant that does not want them leaving the
  system switches AI off (``apps/ai/tenant_switch.py``) rather than sending a
  redacted prompt that produces a useless answer.

That distinction is the honest one, and it is the answer to give a customer who
asks what leaves their tenant: identifiers are stripped, the performance content
the feature exists to reason about is not, and there is a switch that stops all
of it.
"""
from __future__ import annotations

import logging
import re

from django.conf import settings

logger = logging.getLogger("pms.ai.pii")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_EMAIL_REDACTION = "[REDACTED-EMAIL]"

# Phone-shaped runs: optional +country, optional (area), then groups of digits
# separated by space / dot / hyphen. Deliberately loose here and tightened by the
# digit-count check in `_redact_phone` — a regex alone either misses formats or
# eats every number in the prompt.
_PHONE_RE = re.compile(
    r"(?<![\w.])"          # not mid-word, and not the tail of a decimal
    r"\+?\d[\d\s().\-]{5,18}\d"
    r"(?![\w.])"
)
_PHONE_REDACTION = "[REDACTED-PHONE]"
#: E.164 allows up to 15 digits; 7 is the shortest real subscriber number. Outside
#: that range it is much more likely a KPI value, a year range or an id.
_PHONE_MIN_DIGITS = 7
_PHONE_MAX_DIGITS = 15

# LABELLED employee identifiers only — see the module docstring for why a bare
# token is left alone.
_EMPLOYEE_ID_RE = re.compile(
    r"(?i)\b(employee|emp|staff|payroll|personnel)\s*[_\-]?\s*"
    r"(id|ids|no|number|num|#)\s*[:=#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9\-/]{1,31})"
)
_EMPLOYEE_ID_REDACTION = "[REDACTED-EMPLOYEE-ID]"

#: Role → the token a name is replaced with when PII_SCRUB_NAMES is on.
_ROLE_TOKENS = {
    "EMPLOYEE": "[EMPLOYEE]",
    "MANAGER": "[MANAGER]",
    "HRBP": "[HRBP]",
    "ADMIN": "[ADMIN]",
}
_DEFAULT_NAME_TOKEN = "[PERSON]"


def _redact_phone(match: re.Match) -> str:
    """Redact only if the run really is a phone number by digit count."""
    text = match.group(0)
    digits = sum(c.isdigit() for c in text)
    if _PHONE_MIN_DIGITS <= digits <= _PHONE_MAX_DIGITS:
        return _PHONE_REDACTION
    return text


def _redact_employee_id(match: re.Match) -> str:
    """Keep the label, drop the value: "employee id: [REDACTED-EMPLOYEE-ID]".

    Keeping the label matters — the model still knows an identifier was present
    and referred to, it just cannot read it.
    """
    return f"{match.group(1)} {match.group(2)}: {_EMPLOYEE_ID_REDACTION}"


def scrub_text(text: str, name_map: dict[str, str] | None = None) -> str:
    """Redact identifiers from a string. Order matters.

    Emails first (they contain characters the phone pattern would otherwise walk
    into), then labelled employee ids, then phone numbers, then — only when a
    name map is supplied — display names.
    """
    if not isinstance(text, str):
        return text
    out = _EMAIL_RE.sub(_EMAIL_REDACTION, text)
    out = _EMPLOYEE_ID_RE.sub(_redact_employee_id, out)
    out = _PHONE_RE.sub(_redact_phone, out)
    if name_map:
        for name, token in name_map.items():
            # Whole-word, case-insensitive. Longest names were substituted first
            # by the caller so "Ana" cannot pre-empt "Ana Maria".
            out = re.sub(rf"\b{re.escape(name)}\b", token, out, flags=re.IGNORECASE)
    return out


def _name_map_for(tenant) -> dict[str, str]:
    """Display name → role token for every user in ``tenant``.

    Only built when ``PII_SCRUB_NAMES`` is on, because it costs a query. Longest
    names first so a full name is replaced before one of its parts can be.
    """
    if tenant is None:
        return {}
    try:
        from apps.identity.models import User
        from apps.tenancy.context import tenant_context

        tenant_id = getattr(tenant, "id", tenant)
        with tenant_context(tenant_id):
            rows = list(User.objects.values_list("display_name", "role"))
    except Exception:  # noqa: BLE001 — scrubbing must never break a request
        logger.exception("Could not build the name map for PII scrubbing")
        return {}

    pairs: list[tuple[str, str]] = []
    for display_name, role in rows:
        if not display_name:
            continue
        token = _ROLE_TOKENS.get(role, _DEFAULT_NAME_TOKEN)
        pairs.append((display_name, token))
        # Also map the bare first name: evidence.py deliberately passes one.
        first = display_name.split()[0]
        if len(first) > 2:
            pairs.append((first, token))
    # Longest first: "Ana Maria" must be replaced before "Ana".
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return dict(pairs)


def scrub(value, tenant=None):
    """Recursively scrub PII from a string / dict / list.

    Returns a scrubbed copy; other types pass through unchanged. ``tenant`` is
    only needed when ``PII_SCRUB_NAMES`` is on — without it names cannot be
    resolved and are left alone (with a warning), because silently doing nothing
    when a tenant asked for name scrubbing would be the worst outcome.
    """
    name_map: dict[str, str] = {}
    if getattr(settings, "PII_SCRUB_NAMES", False):
        if tenant is None:
            logger.warning(
                "PII_SCRUB_NAMES is on but scrub() was called without a tenant, so "
                "names were NOT redacted."
            )
        else:
            name_map = _name_map_for(tenant)
    return _scrub_value(value, name_map)


def _scrub_value(value, name_map: dict[str, str]):
    if isinstance(value, str):
        return scrub_text(value, name_map)
    if isinstance(value, dict):
        return {k: _scrub_value(v, name_map) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v, name_map) for v in value]
    return value


def contains_pii(value) -> bool:
    """True iff ``value`` still contains an identifier we redact — used by Agent
    3's post-LLM anonymity-breach check.

    Scoped to email/phone deliberately: a name is not a breach for an agent whose
    output is *about* that person, but a contact detail always is.
    """
    text = value if isinstance(value, str) else str(value)
    if _EMAIL_RE.search(text):
        return True
    for m in _PHONE_RE.finditer(text):
        digits = sum(c.isdigit() for c in m.group(0))
        if _PHONE_MIN_DIGITS <= digits <= _PHONE_MAX_DIGITS:
            return True
    return False
