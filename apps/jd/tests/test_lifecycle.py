"""
JD lifecycle — the hand-rolled guarded transitions and the versioning rule.

Covers the happy path (create -> draft -> submit -> approve -> publish), the
required-content gate (422 INVALID_JD_INPUT), every illegal transition (409
ILLEGAL_JD_TRANSITION), and the immutable-published / revise-makes-a-new-draft
invariant that lets the library keep its published content mid-revision.
"""
import pytest

from apps.jd import lifecycle
from apps.jd.exceptions import IllegalJDTransition, InvalidJDInput
from apps.jd.models import JobDescription
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

S = JobDescription.Status

_GOOD_BODY = {
    "summary": "Owns the reliability of the billing platform.",
    "responsibilities": ["Run incident response", "Mentor SREs"],
    "must_haves": ["5+ years operating production systems"],
    "nice_to_haves": ["Kafka"],
}


def _draft(org, body=None):
    return lifecycle.create_jd(
        title="Staff SRE", level="L5", department="Platform",
        actor=org.hrbp, body=body if body is not None else dict(_GOOD_BODY),
    )


def test_create_starts_in_draft_with_version_one(org):
    jd = _draft(org)
    assert jd.status == S.DRAFT
    assert jd.source == JobDescription.Source.MANUAL
    assert jd.created_by_id == org.hrbp.id
    assert jd.current_version_id is None
    with tenant_context(org.tenant):
        v = jd.versions.get()
        assert v.version_number == 1 and v.is_published is False


def test_save_draft_edits_working_version(org):
    jd = _draft(org, body={})
    lifecycle.save_draft(jd, org.hrbp, body=_GOOD_BODY, inputs={"seniority": "staff"})
    with tenant_context(org.tenant):
        v = lifecycle.working_version(jd)
        assert v.body["summary"].startswith("Owns")
        assert v.inputs_snapshot == {"seniority": "staff"}


def test_submit_requires_content(org):
    jd = _draft(org, body={"summary": "", "responsibilities": [], "must_haves": []})
    with pytest.raises(InvalidJDInput) as exc:
        lifecycle.submit_for_review(jd, org.hrbp)
    detail = exc.value.detail
    assert detail["code"] == "INVALID_JD_INPUT"
    assert set(detail["missing"]) == {"summary", "responsibilities", "must_haves"}
    jd.refresh_from_db()
    assert jd.status == S.DRAFT  # unchanged


def test_submit_moves_to_pending_human_review(org):
    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.PENDING_HUMAN_REVIEW


def test_submit_illegal_from_non_draft(org):
    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    with pytest.raises(IllegalJDTransition) as exc:
        lifecycle.submit_for_review(jd, org.hrbp)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ILLEGAL_JD_TRANSITION"


def test_approve_single_step_publishes_without_workflow(org):
    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.PUBLISHED
    assert jd.approval_route_id is None
    with tenant_context(org.tenant):
        v = lifecycle.working_version(jd)
        assert v.is_published is True
        assert jd.current_version_id == v.id


def test_approve_illegal_from_non_pending(org):
    jd = _draft(org)
    with pytest.raises(IllegalJDTransition) as exc:
        lifecycle.approve(jd, org.hrbp)  # still DRAFT
    assert exc.value.status_code == 409


def test_save_draft_illegal_once_published(org):
    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    with pytest.raises(IllegalJDTransition):
        lifecycle.save_draft(jd, org.hrbp, body={"summary": "tamper"})


def test_revise_opens_new_draft_published_stays_live_and_immutable(org):
    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    with tenant_context(org.tenant):
        published = jd.current_version
        published_id, published_number = published.id, published.version_number

    lifecycle.revise(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.DRAFT
    # current_version still points at the live published version (library intact).
    assert jd.current_version_id == published_id
    with tenant_context(org.tenant):
        working = lifecycle.working_version(jd)
        assert working.version_number == published_number + 1
        assert working.is_published is False
        # The new draft seeds from the published body but is a distinct row.
        assert working.id != published_id
        assert working.body == _GOOD_BODY
        # The published version is frozen.
        jd.current_version.refresh_from_db()
        assert jd.current_version.is_published is True

    # Editing the new draft never mutates the live published version.
    lifecycle.save_draft(jd, org.hrbp, body={"summary": "v2 rewrite",
                                             "responsibilities": ["x"], "must_haves": ["y"]})
    with tenant_context(org.tenant):
        jd.current_version.refresh_from_db()
        assert jd.current_version.body == _GOOD_BODY  # unchanged


def test_revise_republish_advances_current_version(org):
    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    lifecycle.revise(jd, org.hrbp)
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.PUBLISHED
    with tenant_context(org.tenant):
        assert jd.current_version.version_number == 2
        assert jd.versions.filter(is_published=True).count() == 2


def test_revise_illegal_from_draft(org):
    jd = _draft(org)
    with pytest.raises(IllegalJDTransition):
        lifecycle.revise(jd, org.hrbp)


def test_archive_and_archive_is_idempotent_guarded(org):
    jd = _draft(org)
    lifecycle.archive(jd, org.hrbp)
    jd.refresh_from_db()
    assert jd.status == S.ARCHIVED
    with pytest.raises(IllegalJDTransition):
        lifecycle.archive(jd, org.hrbp)


def test_every_transition_is_audited(org):
    from apps.audit.models import AuditLog

    jd = _draft(org)
    lifecycle.submit_for_review(jd, org.hrbp)
    lifecycle.approve(jd, org.hrbp)
    with tenant_context(org.tenant):
        # jd.created is audited pre-insert (target_id="", row identified by
        # metadata) exactly like review.created; the rest carry the JD id.
        by_id = set(
            AuditLog.objects.filter(target_id=str(jd.id)).values_list("action", flat=True)
        )
        assert {"jd.submitted", "jd.approved", "jd.published"} <= by_id
        assert AuditLog.objects.filter(
            action="jd.created", metadata__title="Staff SRE"
        ).exists()
