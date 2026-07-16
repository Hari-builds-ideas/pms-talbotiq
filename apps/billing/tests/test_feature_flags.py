"""
Module-11 feature flags + the AI upgrade switch.

Headline properties: ``feature_flags_for`` matches the packs; the upgrade switch
flips flags INSTANTLY without changing seats (audited, cache invalidated); seats
and packs stay independent.
"""
import pytest

from apps.audit.models import AuditLog
from apps.billing import packs
from apps.billing.services import (
    add_pack,
    feature_flags_for,
    get_or_create_entitlement,
    remove_pack,
    set_seats,
    upgrade_prompt,
    upgrade_to_full_ai,
)
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


def test_starter_flags_lock_agents_3_to_5_and_paid_features(tenant):
    get_or_create_entitlement(tenant)  # STARTER default
    flags = feature_flags_for(tenant)
    # Complete map: every gated feature has a boolean.
    assert set(flags) == set(packs.ALL_FEATURES)
    # STARTER's AI taste is Agent 2 + Chat; every generative agent (incl. the
    # now-PREMIUM Agent 1) + the paid generative seams are FULL_AI-only.
    assert flags["agent2"] is True and flags["chat"] is True
    assert flags["agent1"] is False
    assert flags["agent3"] is False and flags["agent4"] is False and flags["agent5"] is False
    assert flags["jd_generator"] is False and flags["career_roadmap"] is False


def test_upgrade_flips_flags_instantly_without_changing_seats(tenant):
    ent = get_or_create_entitlement(tenant, default_seats=7)
    assert ent.seat_count == 7
    before = feature_flags_for(tenant)
    assert before["agent4"] is False and before["jd_generator"] is False

    upgrade_to_full_ai(tenant, actor=None)

    after = feature_flags_for(tenant)  # cache was cleared by the upgrade
    # Every PACK feature flips on. The PLAN-tier keys (PHASE2 L1.4 —
    # advanced_analytics/custom_branding/sso/…) are governed by the tenant's
    # subscription PLAN, not the AI pack, so a pack upgrade leaves them off.
    pack_features = packs.ALL_FEATURES - packs.PLAN_FEATURES
    assert all(after[f] is True for f in pack_features)
    assert all(after[f] is False for f in packs.PLAN_FEATURES)
    # Seats are UNTOUCHED by the pack change (the two axes are independent).
    assert get_or_create_entitlement(tenant).seat_count == 7
    # The upgrade was audited.
    with tenant_context(tenant):
        assert AuditLog.objects.filter(action="entitlement.upgraded").exists()


def test_seats_change_does_not_touch_flags(tenant):
    get_or_create_entitlement(tenant)
    before = feature_flags_for(tenant)
    set_seats(tenant, 25, actor=None)
    after = feature_flags_for(tenant)
    assert before == after  # flags derive from packs, not seats
    assert get_or_create_entitlement(tenant).seat_count == 25


def test_add_and_remove_pack_are_audited(tenant):
    get_or_create_entitlement(tenant)
    add_pack(tenant, packs.FULL_AI, actor=None)
    assert feature_flags_for(tenant)["agent4"] is True
    remove_pack(tenant, packs.FULL_AI, actor=None)
    assert feature_flags_for(tenant)["agent4"] is False
    with tenant_context(tenant):
        assert AuditLog.objects.filter(action="entitlement.pack_added").exists()
        assert AuditLog.objects.filter(action="entitlement.pack_removed").exists()


def test_upgrade_prompt_lists_locked_and_would_unlock(tenant):
    get_or_create_entitlement(tenant)  # STARTER
    prompt = upgrade_prompt(tenant)
    assert "agent4" in prompt["locked_features"]
    assert "jd_generator" in prompt["locked_features"]
    assert prompt["upgrade"]["pack"] == packs.FULL_AI
    assert "agent4" in prompt["upgrade"]["would_unlock"]
    # No pricing/payment is captured (Phase 2).
    assert "note" in prompt["upgrade"]


def test_flags_are_tenant_isolated(tenant, other_tenant):
    get_or_create_entitlement(tenant)
    upgrade_to_full_ai(other_tenant, actor=None)
    # Upgrading other_tenant must not unlock anything for tenant.
    assert feature_flags_for(tenant)["agent4"] is False
    assert feature_flags_for(other_tenant)["agent4"] is True
