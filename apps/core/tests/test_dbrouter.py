"""
Primary/replica DB router (BUILD_3 3.3).

Reads → replica, writes → primary, with read-after-write pinning (a write, or any
read inside a transaction, goes to the primary). Active now against the single DB
(replica falls back to the primary connection); provisioning a real replica is a
config change only.
"""
import pytest

from apps.core.dbrouter import PrimaryReplicaRouter, reset_write_state


def test_router_logic_reads_replica_writes_primary():
    # Pure logic (no DB transaction): a fresh unit reads from the replica; a write
    # flips subsequent reads to the primary (read-after-write); migrations are
    # primary-only; relations span the two.
    reset_write_state()
    r = PrimaryReplicaRouter()
    assert r.db_for_read(None) == "replica"
    assert r.db_for_write(None) == "default"
    assert r.db_for_read(None) == "default"  # pinned to primary after the write
    reset_write_state()
    assert r.db_for_read(None) == "replica"  # cleared → back to replica
    assert r.allow_migrate("default", "app") is True
    assert r.allow_migrate("replica", "app") is False
    assert r.allow_relation(object(), object()) is True


@pytest.mark.django_db
def test_reads_pin_to_primary_inside_a_transaction():
    # A read taken inside an open transaction (this test is wrapped in one, and so
    # is every select_for_update) must hit the primary, never the lagging replica.
    reset_write_state()
    assert PrimaryReplicaRouter().db_for_read(None) == "default"


def test_queryset_resolves_to_the_routed_alias():
    # The router IS the routing authority: a queryset asks it for its alias. Done
    # as a unit (no transaction=True DB-flush, which is flaky under full-suite
    # load with a mirrored replica) — db_for_read's "replica" decision above is
    # exactly what a non-transactional read uses; here we confirm a queryset
    # consults the router rather than hardcoding "default".
    from apps.identity.models import User

    reset_write_state()
    # In a transaction (this isn't django_db, so no wrapping txn) and no write yet
    # → the router routes the queryset's reads to the replica alias.
    assert User.objects.all().db == "replica"
    reset_write_state()


def test_both_db_aliases_load_with_connection_settings():
    # Connection sizing & resilience (BUILD_3 3.4): both aliases are configured,
    # the replica inherits the primary's CONN settings, mirrors it for tests, and
    # the router is wired.
    from django.conf import settings

    dbs = settings.DATABASES
    assert "default" in dbs and "replica" in dbs
    for alias in ("default", "replica"):
        assert dbs[alias]["CONN_MAX_AGE"] == dbs["default"]["CONN_MAX_AGE"]
        assert dbs[alias]["CONN_HEALTH_CHECKS"] is True
    assert dbs["replica"]["TEST"]["MIRROR"] == "default"
    assert "apps.core.dbrouter.PrimaryReplicaRouter" in settings.DATABASE_ROUTERS
