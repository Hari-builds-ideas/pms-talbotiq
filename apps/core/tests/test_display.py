"""
Tests for human-label resolution (apps.core.display.person_label) and the
serializer ``*_name`` fields that stop raw UUIDs leaking to the UI — plus a guard
that resolving names NEVER breaks 360-feedback giver anonymity.
"""
import json

import pytest

from apps.core.display import person_label
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import (
    CycleFactory,
    FeedbackCycleFactory,
    FeedbackFactory,
    ReviewFactory,
    TenantFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ── person_label ──────────────────────────────────────────────────────────────


def test_person_label_prefers_display_name():
    u = UserFactory(display_name="Reza Pahlavi", email="reza@acme.test")
    assert person_label(u) == "Reza Pahlavi"


def test_person_label_falls_back_to_email_local_part_never_uuid():
    u = UserFactory(display_name=None, email="amir@acme.test")
    label = person_label(u)
    assert label == "amir"
    assert "@" not in label  # never the domain
    assert "-" not in label  # not a uuid


def test_person_label_none_for_null_user():
    assert person_label(None) is None


# ── the reported bug: review serializer resolves names, not uuids ──────────────


def test_review_serializer_exposes_names_not_uuids():
    from apps.reviews.serializers import ReviewSerializer

    t = TenantFactory()
    mgr = UserFactory(tenant=t, role="MANAGER", display_name="Manager One", email="mgr@acme.test")
    emp = UserFactory(tenant=t, role="EMPLOYEE", display_name="Reza Pahlavi", email="reza@acme.test", manager=mgr)
    with tenant_context(t):
        cycle = CycleFactory(tenant=t, name="Q2 2026")
        review = ReviewFactory(employee=emp, cycle=cycle)  # reviewer defaults to emp.manager
        data = ReviewSerializer(review).data

    # ids are still present (UI keys/links)…
    assert str(data["employee"]) == str(emp.id)
    assert str(data["reviewer"]) == str(mgr.id)
    # …and the resolved labels are real names, not uuids.
    assert data["employee_name"] == "Reza Pahlavi"
    assert data["reviewer_name"] == "Manager One"
    assert data["cycle_name"] == "Q2 2026"
    assert str(emp.id) not in data["employee_name"]


# ── anonymity: resolving names must NOT leak a 360 giver's identity ────────────


def test_anonymized_payload_never_contains_a_giver_name():
    from apps.feedback.anonymize import build_anonymized_payload

    t = TenantFactory()
    subject = UserFactory(tenant=t, display_name="Ada Subject", email="ada@acme.test")
    giver = UserFactory(tenant=t, display_name="Secret Giver", email="secret@acme.test")
    with tenant_context(t):
        cycle = FeedbackCycleFactory(subject=subject, status="CLOSED", min_volume=1)
        FeedbackFactory(cycle=cycle, giver=giver, relationship="PEER", body="Solid work.")
        payload = build_anonymized_payload(cycle)

    blob = json.dumps(payload).lower()
    # the giver's NAME and email never appear; only the pseudonym egresses
    assert "secret giver" not in blob
    assert "secret@acme.test" not in blob
    assert str(giver.id) not in blob
    assert "peer#1" in blob  # the pseudonym is what egresses


def test_feedback_summary_serializer_resolves_subject_not_giver():
    from apps.feedback.serializers import FeedbackSummarySerializer

    t = TenantFactory()
    subject = UserFactory(tenant=t, display_name="Ada Subject", email="ada@acme.test")
    with tenant_context(t):
        cycle = FeedbackCycleFactory(subject=subject, status="CLOSED")
        from django.utils import timezone

        from apps.feedback.models import FeedbackSummary

        summary = FeedbackSummary.objects.create(
            tenant_id=t.id, cycle=cycle, subject=subject, status="RELEASED",
            generated_at=timezone.now(), volume_total=3,
        )
        data = FeedbackSummarySerializer(summary).data

    assert data["subject_name"] == "Ada Subject"  # subject is known, resolved
    # the summary shape never carries a giver field at all
    assert "giver" not in data and "giver_name" not in data
