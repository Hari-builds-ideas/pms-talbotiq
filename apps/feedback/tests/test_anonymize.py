"""
The anonymisation layer — Module 4's headline tests.

The provable property (the analog of Module 3's CHECK-constraint proof): the
serialized anonymised payload contains ZERO giver UUIDs, names, or emails.
"""
import json

import pytest

from apps.feedback.anonymize import (
    build_anonymized_payload,
    group_volumes,
    insufficient_groups_for,
    scan_for_identity_leaks,
)
from apps.feedback.models import Feedback
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    FeedbackCycleFactory,
    FeedbackFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _populated_cycle(org, peers=3, upward=0):
    """A COLLECTING cycle with SELF + MANAGER + N peers (+ M upward) feedback."""
    cycle = FeedbackCycleFactory(subject=org.report)
    FeedbackFactory(cycle=cycle, giver=org.report, relationship="SELF", body="I grew a lot.")
    FeedbackFactory(cycle=cycle, giver=org.manager, relationship="MANAGER", body="Solid year.")
    givers = []
    for i in range(peers):
        peer = UserFactory(tenant=org.tenant, role="EMPLOYEE", email=f"peer{i}@acme.test")
        FeedbackFactory(cycle=cycle, giver=peer, relationship="PEER", body=f"Peer note {i}.")
        givers.append(peer)
    for i in range(upward):
        rep = UserFactory(tenant=org.tenant, role="EMPLOYEE", email=f"up{i}@acme.test")
        FeedbackFactory(cycle=cycle, giver=rep, relationship="UPWARD", body=f"Upward note {i}.")
        givers.append(rep)
    return cycle, givers


# ── THE GUARANTEE: zero giver identifiers in the egress payload ─────────────


def test_payload_contains_zero_giver_identifiers(org):
    cycle, givers = _populated_cycle(org, peers=3, upward=3)
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
        # The ONLY identifier the payload may carry is the subject_id field
        # itself (recipients know whose 360 this is; SELF is inherently
        # attributed). Remove that one declared field, then prove NOTHING else
        # identifies anyone — no giver UUIDs, no emails, not even the subject's.
        scrubbed = dict(payload)
        assert scrubbed.pop("subject_id") == str(org.report.id)
        blob = json.dumps(scrubbed).lower()
        for giver in [org.report, org.manager, *givers]:
            assert str(giver.id).lower() not in blob
            assert giver.id.hex not in blob
            assert giver.email.lower() not in blob
        # Bodies ARE present (the content egresses; the identity does not).
        assert "peer note 0." in blob


def test_pseudonyms_are_opaque_and_sequential(org):
    cycle, _ = _populated_cycle(org, peers=3)
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
    peers = payload["groups"]["PEER"]
    assert [p["pseudonym"] for p in peers] == ["PEER#1", "PEER#2", "PEER#3"]
    assert payload["groups"]["SELF"][0]["pseudonym"] == "SELF#1"


def test_payload_is_deterministic(org):
    cycle, _ = _populated_cycle(org, peers=3)
    with tenant_context(org.tenant):
        assert build_anonymized_payload(cycle) == build_anonymized_payload(cycle)


# ── per-group min-volume threshold ─────────────────────────────────────────


def test_peer_group_below_threshold_is_excluded(org):
    # 5 items total but only 1 peer: the PEER group is still excluded.
    cycle, _ = _populated_cycle(org, peers=1, upward=3)
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
    assert "PEER" not in payload["groups"]
    assert payload["insufficient_groups"] == ["PEER"]
    assert payload["insufficient_volume"] is True
    # The sufficient UPWARD group (3 >= 3) is included; SELF/MANAGER always are.
    assert len(payload["groups"]["UPWARD"]) == 3
    assert "SELF" in payload["groups"] and "MANAGER" in payload["groups"]


def test_group_at_threshold_is_included(org):
    cycle, _ = _populated_cycle(org, peers=3)
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
    assert len(payload["groups"]["PEER"]) == 3
    assert payload["insufficient_groups"] == []
    assert payload["insufficient_volume"] is False


def test_self_and_manager_bypass_the_threshold(org):
    # 1 SELF + 1 MANAGER are below 3 but are attributed by nature — included.
    cycle, _ = _populated_cycle(org, peers=0)
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
    assert "SELF" in payload["groups"] and "MANAGER" in payload["groups"]
    assert payload["insufficient_groups"] == []  # empty PEER group is absent, not at-risk


def test_per_cycle_min_volume_override(org):
    cycle, _ = _populated_cycle(org, peers=3)
    cycle.min_volume = 5
    cycle.save()
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
    assert "PEER" not in payload["groups"]  # 3 < the overridden 5
    assert payload["insufficient_groups"] == ["PEER"]


def test_group_volumes_counts_by_relationship(org):
    cycle, _ = _populated_cycle(org, peers=2, upward=1)
    with tenant_context(org.tenant):
        volumes = group_volumes(cycle)
        assert volumes == {"SELF": 1, "MANAGER": 1, "PEER": 2, "UPWARD": 1}
        assert insufficient_groups_for(cycle) == ["PEER", "UPWARD"]


# ── the deterministic anonymity-breach guard ───────────────────────────────


def test_breach_guard_flags_tenant_user_email_in_body(org):
    cycle, _ = _populated_cycle(org, peers=3)
    with tenant_context(org.tenant):
        # One peer names a colleague by email inside the body.
        leaky = Feedback.objects.filter(cycle=cycle, relationship="PEER").first()
        leaky.body = f"Talk to {org.peer.email} about this."
        leaky.save()
        payload = build_anonymized_payload(cycle)
        findings = scan_for_identity_leaks(cycle, payload)
    assert findings, "the guard must flag a tenant user's email in a body"
    assert findings[0]["pattern"] == "tenant_user_email"
    assert findings[0]["group"] == "PEER"
    # Findings never carry the giver identity.
    assert "giver" not in findings[0]
    assert findings[0]["pseudonym"].startswith("PEER#")


def test_breach_guard_flags_any_email_like_string(org):
    cycle, _ = _populated_cycle(org, peers=3)
    with tenant_context(org.tenant):
        leaky = Feedback.objects.filter(cycle=cycle, relationship="PEER").first()
        leaky.body = "Contact them at someone.external@gmail.com please."
        leaky.save()
        payload = build_anonymized_payload(cycle)
        findings = scan_for_identity_leaks(cycle, payload)
    assert findings and findings[0]["pattern"] == "email_like"


def test_breach_guard_passes_clean_bodies(org):
    cycle, _ = _populated_cycle(org, peers=3)
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
        assert scan_for_identity_leaks(cycle, payload) == []


def test_breach_guard_ignores_excluded_groups(org):
    # A leak inside a below-threshold group never egresses, so it is not scanned.
    cycle, _ = _populated_cycle(org, peers=1)
    with tenant_context(org.tenant):
        leaky = Feedback.objects.filter(cycle=cycle, relationship="PEER").first()
        leaky.body = f"Ping {org.peer.email}."
        leaky.save()
        payload = build_anonymized_payload(cycle)
        assert "PEER" not in payload["groups"]
        assert scan_for_identity_leaks(cycle, payload) == []


# ── isolation ──────────────────────────────────────────────────────────────


def test_payload_and_scan_are_tenant_scoped(org, other_tenant):
    cycle, _ = _populated_cycle(org, peers=3)
    outsider = UserFactory(tenant=other_tenant, email="outsider@other.test")
    with tenant_context(org.tenant):
        payload = build_anonymized_payload(cycle)
        blob = json.dumps(payload)
        assert "outsider@other.test" not in blob
        # The scan compares against THIS tenant's users only.
        findings = scan_for_identity_leaks(cycle, payload)
        assert findings == []
    with tenant_context(other_tenant):
        from apps.feedback.models import FeedbackCycle

        assert FeedbackCycle.objects.filter(id=cycle.id).count() == 0
