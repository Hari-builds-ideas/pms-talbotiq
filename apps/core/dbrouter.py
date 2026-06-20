"""
Primary/replica DB router (BUILD_3) — read/write split, replica-ready.

Reads go to the ``replica`` alias, writes to ``default``. It is active and tested
NOW against the single existing database (the ``replica`` alias falls back to the
same connection as ``default`` when no replica DSN is configured — see
``config/settings``), so provisioning a real read replica later is a config
change (set the replica env DSN), never a code change.

READ-AFTER-WRITE correctness: a replica lags the primary, so once a request (or
unit of work) has WRITTEN, its subsequent reads MUST hit the primary or they'd
risk serving stale data. Two rules enforce this:

  * a per-thread "has written" flag, set on the first write and cleared at the
    start of each request (middleware) and each Celery task (``task_prerun``);
  * any read taken while inside a transaction (``in_atomic_block``) — which
    includes every ``select_for_update`` — goes to the primary.

The audit log and every other write naturally route to ``default`` via
``db_for_write``. Migrations only ever run on ``default``.
"""
from __future__ import annotations

import threading

from django.db import connections

_state = threading.local()

#: The alias names. ``replica`` may be a real replica or a fallback copy of
#: ``default`` — the router doesn't care; the config wires the fallback.
PRIMARY = "default"
REPLICA = "replica"


def reset_write_state() -> None:
    """Clear the per-thread write flag — called at the start of each request and
    each Celery task so read-after-write pinning never bleeds across units."""
    _state.writing = False


def _has_written() -> bool:
    return getattr(_state, "writing", False)


def _in_transaction() -> bool:
    # A read inside an open transaction (incl. select_for_update) must hit the
    # primary; the replica could be behind the uncommitted/just-committed write.
    return connections[PRIMARY].in_atomic_block


class PrimaryReplicaRouter:
    """Route reads → replica, writes → primary, with read-after-write pinning."""

    def db_for_read(self, model, **hints):
        if _has_written() or _in_transaction():
            return PRIMARY
        return REPLICA

    def db_for_write(self, model, **hints):
        _state.writing = True
        return PRIMARY

    def allow_relation(self, obj1, obj2, **hints):
        # The replica is a copy of the primary — relations span the two freely.
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Never migrate the replica; schema changes apply to the primary only.
        return db == PRIMARY


class DBRoutingResetMiddleware:
    """Clear the read-after-write flag at the START of every request, so a write
    in one request can't pin reads to the primary in the next (reused worker
    thread). Placed early in MIDDLEWARE, before any view/DB access."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reset_write_state()
        return self.get_response(request)
