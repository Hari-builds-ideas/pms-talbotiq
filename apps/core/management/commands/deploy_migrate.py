"""
deploy_migrate (E2) — race-safe, one-shot migrations for multi-replica deploys.

Running ``manage.py migrate`` on every replica boot RACES: N replicas can enter the
migration executor at once (Django's ``django_migrations`` table isn't guarded
against N racers). This command wraps ``migrate`` in a MySQL ADVISORY LOCK
(``GET_LOCK``): the first caller migrates; any concurrent caller finds the lock held,
prints a message, and exits 0 (a no-op). Idempotent — once the schema is current a
repeat run applies nothing.

Deploy flow (see ``docker-compose.prod.yml`` + ``docs/RUNBOOK.md``): run ONE
``deploy_migrate`` job to completion, then boot N web/worker replicas WITHOUT
migrating (they just serve — that's the ``--no-migrate`` boot posture; the app serves
fine even with the migrate job still in flight). This command is that one job.
"""
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

#: A stable, app-wide advisory-lock name — every deploy_migrate contends on it.
LOCK_NAME = "pms_deploy_migrate"
#: Seconds to wait for the lock before yielding. Short: a concurrent racer should
#: bail fast and let the holder migrate, not queue behind it.
DEFAULT_TIMEOUT = 1


def acquire_advisory_lock(name: str, timeout: int) -> bool:
    """Try to take the MySQL advisory lock ``name`` (``GET_LOCK``). Returns True if
    acquired, False if another session holds it (timed out). Non-MySQL backends have
    no ``GET_LOCK`` — the lock is a MySQL-specific safety net, so they return True."""
    if connection.vendor != "mysql":
        return True
    with connection.cursor() as cur:
        cur.execute("SELECT GET_LOCK(%s, %s)", [name, timeout])
        row = cur.fetchone()
    return bool(row and row[0] == 1)


def release_advisory_lock(name: str) -> None:
    """Release the MySQL advisory lock (no-op on non-MySQL / if not held)."""
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cur:
        cur.execute("SELECT RELEASE_LOCK(%s)", [name])
        cur.fetchone()


class Command(BaseCommand):
    help = "Run migrations under a DB advisory lock (race-safe for multi-replica deploys)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lock-timeout",
            type=int,
            default=DEFAULT_TIMEOUT,
            help="Seconds to wait for the advisory lock before yielding (default 1).",
        )

    def handle(self, *args, lock_timeout=DEFAULT_TIMEOUT, verbosity=1, **opts):
        if not acquire_advisory_lock(LOCK_NAME, lock_timeout):
            # Another instance owns the migrate window — yield cleanly (exit 0).
            self.stdout.write("Another instance is migrating; skipping (advisory lock held).")
            return
        try:
            call_command("migrate", "--noinput", verbosity=verbosity)
        finally:
            # Always release, even if migrate raised — never strand the lock.
            release_advisory_lock(LOCK_NAME)

        # C6 — prove the audit log is still immutable at the DATABASE.
        #
        # Migration audit/0002 creates BEFORE UPDATE / BEFORE DELETE triggers on
        # audit_log. Creating a trigger needs log_bin_trust_function_creators=1 or
        # TRIGGER+SUPER grants, and a managed MySQL grants neither by default — so
        # the migration can report success while the triggers were never created,
        # silently dropping a layer of immutability with no signal anywhere.
        #
        # Raising here fails the deploy rather than letting it proceed. That is the
        # right way round: an audit log you believe is tamper-proof and is not is
        # worse than a deploy that stopped and told you why.
        call_command("verify_audit_triggers")
        self.stdout.write(self.style.SUCCESS("Migrations applied; advisory lock released."))
