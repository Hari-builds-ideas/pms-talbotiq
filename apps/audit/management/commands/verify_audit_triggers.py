"""
verify_audit_triggers (C6) — prove the audit log is still immutable at the DB.

``AuditLog`` immutability is defended at three layers: ``save()`` refuses to
rewrite a row, the manager forbids ``update()``/``delete()``, and MySQL
``BEFORE UPDATE`` / ``BEFORE DELETE`` triggers reject mutation even against raw
SQL. Only the third survives someone with a database client.

Those triggers are created by migration ``audit/0002``, and creating a trigger
requires either ``log_bin_trust_function_creators=1`` or ``TRIGGER``+``SUPER``
grants. On a managed MySQL (Cloud SQL, RDS) neither is on by default — which is
the failure this command exists for: the migration can be reported as applied
while the triggers were never created, and nothing anywhere says so. The audit log
then quietly falls back to application-level immutability, which is exactly the
guarantee the triggers exist to not depend on.

Exit codes:
    0  both triggers present
    1  one or both missing (or the backend cannot be checked)
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

#: The trigger names created by apps/audit/migrations/0002. Kept here as the
#: assertion, so a rename in the migration without a matching change here fails
#: loudly rather than silently checking for something that no longer exists.
REQUIRED_TRIGGERS = ("audit_log_block_update", "audit_log_block_delete")
TABLE = "audit_log"


def existing_triggers() -> set[str]:
    """Trigger names currently defined on ``audit_log`` in this schema."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT TRIGGER_NAME
              FROM information_schema.TRIGGERS
             WHERE TRIGGER_SCHEMA = DATABASE()
               AND EVENT_OBJECT_TABLE = %s
            """,
            [TABLE],
        )
        return {row[0] for row in cur.fetchall()}


class Command(BaseCommand):
    help = "Assert the audit_log immutability triggers exist; exit non-zero if not."

    def handle(self, *args, **options):
        if connection.vendor != "mysql":
            # Not a pass. The triggers are MySQL DDL; on any other backend the
            # third layer of immutability simply does not exist, and saying "OK"
            # would be a lie in the one place that must not lie.
            raise CommandError(
                f"Audit triggers can only be verified on MySQL (backend is "
                f"'{connection.vendor}'). The audit log's database-level "
                f"immutability is NOT in force."
            )

        found = existing_triggers()
        missing = [name for name in REQUIRED_TRIGGERS if name not in found]

        if missing:
            raise CommandError(
                "Audit-log immutability triggers are MISSING: "
                + ", ".join(missing)
                + ".\n\n"
                "The audit log is currently protected only by application code, so "
                "anyone with database access can rewrite or delete audit rows.\n\n"
                "Most likely cause: this database does not allow a non-SUPER user to "
                "create triggers, so migration audit/0002 could not create them. Fix "
                "with one of:\n"
                "  - set log_bin_trust_function_creators = 1 on the server, then\n"
                "    re-run: manage.py migrate audit 0001 && manage.py migrate audit\n"
                "  - or grant TRIGGER (and SUPER, if binary logging is on) to the\n"
                "    application's database user and do the same.\n"
                f"Found on {TABLE}: {sorted(found) or 'none'}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Audit-log immutability triggers present on {TABLE}: "
                + ", ".join(sorted(REQUIRED_TRIGGERS))
            )
        )
