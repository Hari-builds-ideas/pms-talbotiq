"""
Symmetric field encryption for secrets we must store and read back.

Used for the per-tenant LLM API key (B1). A provider key is a *credential we have
to present later*, so it cannot be hashed — it has to be reversible. That makes
key management the whole security story:

* The encryption key lives in ``FIELD_ENCRYPTION_KEY`` (env only, never in code
  or a fixture). It is a urlsafe-base64 32-byte Fernet key.
* With it unset, encryption is UNAVAILABLE and every write path refuses. Storing
  a provider key in plaintext because the deployment forgot a variable is
  strictly worse than refusing, so this fails closed.
* Fernet gives authenticated encryption (AES-128-CBC + HMAC-SHA256), so a
  tampered ciphertext is rejected rather than silently decrypting to garbage.

Rotation: ``FIELD_ENCRYPTION_KEY`` accepts a comma-separated list. The FIRST key
encrypts; all of them are tried for decryption (``MultiFernet``). So a rotation is
"prepend the new key, deploy, re-save the affected rows, drop the old key" with no
window where existing ciphertext is unreadable.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

logger = logging.getLogger("pms.ai.crypto")


class EncryptionUnavailable(RuntimeError):
    """No usable FIELD_ENCRYPTION_KEY. Raised on WRITE so a secret is never
    persisted in the clear; reads degrade to "not configured" instead."""


def _fernet() -> MultiFernet | None:
    """Build the cipher from ``FIELD_ENCRYPTION_KEY``, or None when unusable.

    Returns None rather than raising so read paths can treat "cannot decrypt" as
    "no key configured" and fall through to the environment key.
    """
    raw = (getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        return None
    keys = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            keys.append(Fernet(part.encode()))
        except (ValueError, TypeError):
            # A malformed key is a deployment error. Log WITHOUT the value.
            logger.error(
                "FIELD_ENCRYPTION_KEY contains an entry that is not a valid Fernet "
                "key; ignoring that entry."
            )
    if not keys:
        return None
    return MultiFernet(keys)


def encryption_available() -> bool:
    """True iff a secret can be stored. Surfaced to admins so "you must set
    FIELD_ENCRYPTION_KEY first" is an explainable state, not a mystery 500."""
    return _fernet() is not None


def encrypt(plaintext: str) -> str:
    """Encrypt with the FIRST configured key. Raises when unavailable."""
    f = _fernet()
    if f is None:
        raise EncryptionUnavailable(
            "FIELD_ENCRYPTION_KEY is not set, so secrets cannot be stored. Set it "
            "in the environment and retry; nothing was saved."
        )
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """Decrypt, trying every configured key. None when the value cannot be read.

    None is deliberate rather than an exception: a rotated-away key or a tampered
    row must degrade to "this tenant has no usable key" (so the gateway falls
    through to the environment key or reports NOT_CONFIGURED), not take down every
    AI request with a 500.
    """
    if not ciphertext:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        logger.error(
            "A stored secret could not be decrypted with any configured "
            "FIELD_ENCRYPTION_KEY — it was written under a key that is no longer "
            "present, or the row was tampered with."
        )
        return None


def last4(secret: str) -> str:
    """The only part of a secret we ever store in the clear or return over the
    API — enough for an admin to recognise which key is installed, useless to
    anyone who steals it."""
    return (secret or "")[-4:]
