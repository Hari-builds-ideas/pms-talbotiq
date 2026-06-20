"""
Optimistic locking for contended writes (BUILD_4 4.3).

Plain-field PATCH/PUT is last-writer-wins: two editors who both load v0 and save
silently clobber each other. For the genuinely contended entities (justified in
DECISIONS.md) we add an integer ``version``: a client sends the version it read,
and a mismatch means someone else saved first → HTTP 409 (the existing "reload,
your copy is stale" convention), so no edit is silently lost.

``version`` is server-controlled: serializers expose it READ-ONLY (the client
reads it and echoes it back for the check, but can never set the stored value);
the update view bumps it via ``serializer.save(version=instance.version + 1)``.
"""
from __future__ import annotations

from rest_framework.exceptions import APIException


class StaleVersion(APIException):
    """409 — the row changed since the client read it (optimistic-lock miss)."""

    status_code = 409
    default_code = "stale_version"

    def __init__(self, current_version: int):
        super().__init__(
            {
                "detail": "This record was changed by someone else. Reload and try again.",
                "code": "STALE_VERSION",
                "current_version": current_version,
            }
        )


def check_version(instance, data) -> None:
    """Raise :class:`StaleVersion` if ``data`` carries a ``version`` that no longer
    matches ``instance.version``. A request that omits ``version`` is allowed
    through (back-compat / non-form callers) — only an explicit STALE version is
    rejected."""
    sent = data.get("version") if hasattr(data, "get") else None
    if sent is None:
        return
    try:
        sent = int(sent)
    except (TypeError, ValueError):
        return
    if sent != instance.version:
        raise StaleVersion(instance.version)
