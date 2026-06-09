"""
Service-level tests for the decoupled commercial model.

Central guarantees proven here:
  * seats and packs move INDEPENDENTLY — ``set_seats`` never touches packs, and
    ``upgrade_to_full_ai`` never touches seats;
  * a STARTER tenant unlocks exactly {agent1, agent2}; FULL_AI unlocks 1-5;
  * locked agents are denied and unlock instantly on upgrade;
  * the upgrade is idempotent;
  * the upgrade writes an immutable ``entitlement.upgraded`` audit row crediting
    the acting admin.
"""
import pytest

from apps.audit.models import AuditLog
from apps.billing.packs import AGENT1, AGENT2, AGENT3, AGENT4, AGENT5, FULL_AI, STARTER
from apps.billing.services import (
    get_or_create_entitlement,
    set_seats,
    tenant_has_agent,
    upgrade_to_full_ai,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_default_entitlement_is_starter_with_zero_seats():
    t = TenantFactory()
    ent = get_or_create_entitlement(t)
    assert ent.seat_count == 0
    assert ent.feature_packs == [STARTER]
    assert ent.unlocked_agents() == {AGENT1, AGENT2}


def test_get_or_create_is_idempotent_single_row():
    t = TenantFactory()
    first = get_or_create_entitlement(t)
    second = get_or_create_entitlement(t)
    assert first.pk == second.pk
    with tenant_context(t):
        from apps.billing.models import Entitlement

        assert Entitlement.objects.count() == 1


def test_get_or_create_respects_overrides():
    t = TenantFactory()
    ent = get_or_create_entitlement(t, default_seats=10, default_packs=[FULL_AI])
    assert ent.seat_count == 10
    assert ent.feature_packs == [FULL_AI]


def test_set_seats_changes_seats_but_not_packs():
    t = TenantFactory()
    get_or_create_entitlement(t)  # STARTER, 0 seats
    ent = set_seats(t, 25)
    assert ent.seat_count == 25
    assert ent.feature_packs == [STARTER]  # packs untouched
    # Persisted, not just in-memory.
    refreshed = get_or_create_entitlement(t)
    assert refreshed.seat_count == 25
    assert refreshed.feature_packs == [STARTER]


def test_upgrade_adds_full_ai_without_changing_seats():
    t = TenantFactory()
    set_seats(t, 25)
    before = get_or_create_entitlement(t)
    assert before.seat_count == 25

    upgraded = upgrade_to_full_ai(t)
    # Packs gained FULL_AI; seats unchanged.
    assert FULL_AI in upgraded.feature_packs
    assert STARTER in upgraded.feature_packs
    assert upgraded.seat_count == 25
    assert upgraded.unlocked_agents() == {AGENT1, AGENT2, AGENT3, AGENT4, AGENT5}

    refreshed = get_or_create_entitlement(t)
    assert refreshed.seat_count == 25  # still 25 after upgrade


def test_upgrade_is_idempotent():
    t = TenantFactory()
    upgrade_to_full_ai(t)
    again = upgrade_to_full_ai(t)
    # FULL_AI appears exactly once, not duplicated.
    assert again.feature_packs.count(FULL_AI) == 1


def test_locked_agent_denied_on_starter_unlocked_after_upgrade():
    t = TenantFactory()
    get_or_create_entitlement(t)  # STARTER
    # agents 1-2 always available; 3-5 locked on STARTER.
    assert tenant_has_agent(t, AGENT1) is True
    assert tenant_has_agent(t, AGENT2) is True
    assert tenant_has_agent(t, AGENT3) is False
    assert tenant_has_agent(t, AGENT4) is False
    assert tenant_has_agent(t, AGENT5) is False

    upgrade_to_full_ai(t)
    assert tenant_has_agent(t, AGENT3) is True
    assert tenant_has_agent(t, AGENT4) is True
    assert tenant_has_agent(t, AGENT5) is True
    # 1-2 remain available.
    assert tenant_has_agent(t, AGENT1) is True
    assert tenant_has_agent(t, AGENT2) is True


def test_upgrade_writes_audit_row_crediting_actor():
    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN", email="admin@svc.test")
    upgrade_to_full_ai(t, actor=admin)

    with tenant_context(t):
        rows = list(AuditLog.objects.filter(action="entitlement.upgraded"))
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_id == admin.id
    assert row.target_type == "tenant"
    assert row.target_id == str(t.id)
    assert row.metadata["pack_added"] == FULL_AI
    assert set(row.metadata["unlocked_agents"]) == {
        AGENT1,
        AGENT2,
        AGENT3,
        AGENT4,
        AGENT5,
    }


def test_idempotent_upgrade_writes_no_second_audit_row():
    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN", email="admin2@svc.test")
    upgrade_to_full_ai(t, actor=admin)
    upgrade_to_full_ai(t, actor=admin)  # already FULL_AI -> no-op
    with tenant_context(t):
        assert AuditLog.objects.filter(action="entitlement.upgraded").count() == 1


def test_set_seats_writes_audit_row():
    t = TenantFactory()
    admin = UserFactory(tenant=t, role="ADMIN", email="admin3@svc.test")
    set_seats(t, 42, actor=admin)
    with tenant_context(t):
        rows = list(AuditLog.objects.filter(action="billing.seats_changed"))
    assert len(rows) == 1
    assert rows[0].metadata["new_seats"] == 42
