"""
verify_audit_triggers (C6).

The command exists for one failure: a managed MySQL that will not let a non-SUPER
user create triggers, so migration audit/0002 reports success while the
BEFORE UPDATE / BEFORE DELETE triggers were never created. The audit log then
falls back to application-level immutability only, and nothing anywhere says so.

So the test that matters is not "it passes when the triggers exist" — it is "it
FAILS when one is dropped". A checker that cannot fail is not a checker.
"""
import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.audit.management.commands.verify_audit_triggers import (
    REQUIRED_TRIGGERS,
    existing_triggers,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_passes_when_both_triggers_exist():
    # The migration created them; this is the ordinary state.
    call_command("verify_audit_triggers")
    assert set(REQUIRED_TRIGGERS).issubset(existing_triggers())


def test_fails_loudly_when_a_trigger_is_missing():
    """Drop one, assert the command refuses, put it back."""
    victim = "audit_log_block_update"
    with connection.cursor() as cur:
        cur.execute(f"DROP TRIGGER IF EXISTS {victim}")
    try:
        with pytest.raises(CommandError) as exc:
            call_command("verify_audit_triggers")
        message = str(exc.value)
        # It has to name what is missing and what to do — a deploy failing with
        # "check failed" sends someone hunting.
        assert victim in message
        assert "log_bin_trust_function_creators" in message
        assert "application code" in message.lower()
    finally:
        # Restore exactly what migration audit/0002 creates.
        with connection.cursor() as cur:
            cur.execute(
                f"CREATE TRIGGER {victim} BEFORE UPDATE ON audit_log "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'audit_log is append-only: UPDATE is not permitted.'"
            )
    assert set(REQUIRED_TRIGGERS).issubset(existing_triggers())


def test_fails_when_both_are_missing_and_names_both():
    with connection.cursor() as cur:
        for name in REQUIRED_TRIGGERS:
            cur.execute(f"DROP TRIGGER IF EXISTS {name}")
    try:
        with pytest.raises(CommandError) as exc:
            call_command("verify_audit_triggers")
        for name in REQUIRED_TRIGGERS:
            assert name in str(exc.value)
    finally:
        with connection.cursor() as cur:
            cur.execute(
                "CREATE TRIGGER audit_log_block_update BEFORE UPDATE ON audit_log "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'audit_log is append-only: UPDATE is not permitted.'"
            )
            cur.execute(
                "CREATE TRIGGER audit_log_block_delete BEFORE DELETE ON audit_log "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'audit_log is append-only: DELETE is not permitted.'"
            )


# Note: that the triggers actually BLOCK a raw UPDATE/DELETE is already covered
# by apps/audit/tests/test_audit_log.py ("DB-level immutability"). This file only
# tests the checker — whether it notices when they are gone.
