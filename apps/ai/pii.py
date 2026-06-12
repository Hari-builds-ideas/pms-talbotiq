"""
PII scrubbing applied by the LLM gateway to EVERY input before it reaches a
provider (Doc 3 §5 safeguard pipeline). Deterministic + conservative: it redacts
any email-like token (the same class of identifier the Module-4 anonymiser guards),
recursively through dicts/lists/strings. (Users have no name fields today; when
profiles gain names, extend the patterns here — the single scrub point.)
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_REDACTION = "[REDACTED-EMAIL]"


def scrub_text(text: str) -> str:
    """Redact email-like tokens from a string."""
    if not isinstance(text, str):
        return text
    return _EMAIL_RE.sub(_REDACTION, text)


def scrub(value):
    """Recursively scrub PII from a string / dict / list (returns a scrubbed copy;
    other types pass through unchanged)."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def contains_pii(value) -> bool:
    """True iff ``value`` (after stringify) still contains an email-like token —
    used by Agent 3's post-LLM anonymity-breach check."""
    return bool(_EMAIL_RE.search(value if isinstance(value, str) else str(value)))
