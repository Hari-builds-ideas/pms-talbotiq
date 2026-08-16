"""
deploy_migrate (E2) — race-safe one-shot migrations under a DB advisory lock.

Covers: migrate runs under the lock and the lock is always released (even on
failure); a concurrent racer that can't take the lock exits 0 with a message
WITHOUT migrating; the real MySQL GET_LOCK/RELEASE_LOCK round-trips; and running
the real command twice is a clean no-op (idempotent — the test DB is already
migrated).
"""
import uuid
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.core.management.commands import deploy_migrate

pytestmark = pytest.mark.django_db

_CC = "apps.core.management.commands.deploy_migrate.call_command"


def test_runs_migrate_under_lock_and_releases():
    with patch.object(deploy_migrate, "acquire_advisory_lock", return_value=True) as acq, \
         patch.object(deploy_migrate, "release_advisory_lock") as rel, \
         patch(_CC) as cc:
        call_command("deploy_migrate")
    acq.assert_called_once()
    # Two sub-commands now: migrate under the lock, then verify_audit_triggers
    # after it (C6) — a deploy must not proceed believing the audit log is
    # tamper-proof when the triggers were never created.
    invoked = [c[0][0] for c in cc.call_args_list]
    assert invoked == ["migrate", "verify_audit_triggers"]
    rel.assert_called_once()  # lock released


def test_audit_triggers_are_verified_after_the_lock_is_released():
    """Ordering matters: holding the advisory lock across the trigger check would
    make every concurrent deploy queue behind a read-only assertion."""
    calls = []
    with patch.object(deploy_migrate, "acquire_advisory_lock", return_value=True), \
         patch.object(deploy_migrate, "release_advisory_lock",
                      side_effect=lambda *a, **k: calls.append("release")), \
         patch(_CC, side_effect=lambda name, *a, **k: calls.append(name)):
        call_command("deploy_migrate")
    assert calls == ["migrate", "release", "verify_audit_triggers"]


def test_a_missing_audit_trigger_fails_the_deploy():
    """The point of wiring the check into deploy_migrate: it must STOP the deploy,
    not log and carry on."""
    from django.core.management.base import CommandError

    def _fake(name, *a, **k):
        if name == "verify_audit_triggers":
            raise CommandError("Audit-log immutability triggers are MISSING")

    with patch.object(deploy_migrate, "acquire_advisory_lock", return_value=True), \
         patch.object(deploy_migrate, "release_advisory_lock"), \
         patch(_CC, side_effect=_fake):
        with pytest.raises(CommandError, match="MISSING"):
            call_command("deploy_migrate")


def test_releases_lock_even_when_migrate_fails():
    with patch.object(deploy_migrate, "acquire_advisory_lock", return_value=True), \
         patch.object(deploy_migrate, "release_advisory_lock") as rel, \
         patch(_CC, side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            call_command("deploy_migrate")
    rel.assert_called_once()  # finally-released, never stranded


def test_skips_when_lock_unavailable_exit_0_with_message():
    out = StringIO()
    with patch.object(deploy_migrate, "acquire_advisory_lock", return_value=False), \
         patch(_CC) as cc:
        call_command("deploy_migrate", stdout=out)  # returns normally (exit 0)
    cc.assert_not_called()  # migrate was NOT run
    assert "skipping" in out.getvalue().lower()


def test_advisory_lock_real_roundtrip():
    # Exercises the real MySQL GET_LOCK / RELEASE_LOCK SQL (unique name → no clash).
    name = f"pms_test_{uuid.uuid4().hex[:12]}"
    assert deploy_migrate.acquire_advisory_lock(name, 1) is True
    deploy_migrate.release_advisory_lock(name)  # no error


def test_real_run_is_idempotent_noop():
    # The test DB is already migrated, so the REAL command (real lock + real migrate)
    # applies nothing — twice. Proves idempotency end to end.
    call_command("deploy_migrate")
    call_command("deploy_migrate")
