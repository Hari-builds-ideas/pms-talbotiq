"""
The JD lifecycle — small, hand-rolled, audited guarded transitions (the library
is the contract). Mirrors the Module-3 review discipline:

    create        -> DRAFT (+ JDVersion v1)
    save_draft    -> edit the working version (DRAFT or PENDING_HUMAN_REVIEW;
                     re-saving in PENDING keeps it PENDING)
    submit_for_review : DRAFT -> PENDING_HUMAN_REVIEW (validates required content)
    approve       : PENDING_HUMAN_REVIEW -> if an active "jd" workflow exists, ENTER
                    the route (status IN_REVIEW); else single-step PUBLISH
    route_rejected: IN_REVIEW -> PENDING_HUMAN_REVIEW (engine calls this)
    revise        : PUBLISHED -> DRAFT (a NEW draft version; the published version
                    stays live + immutable)
    archive       : any -> ARCHIVED

HITL: a draft is locked PENDING_HUMAN_REVIEW and only a human approve advances it
(to a route or to publish). Routing is OPT-IN exactly like reviews. Every entry
binds the tenant (off-request safe) and audits BEFORE the effect.
"""
import functools

from apps.audit.services import record
from apps.tenancy.context import tenant_context

from .exceptions import IllegalJDTransition, InvalidJDInput
from .models import JDVersion, JobDescription

S = JobDescription.Status


def _tenant_bound(fn):
    @functools.wraps(fn)
    def wrapper(jd, *args, **kwargs):
        with tenant_context(jd.tenant_id):
            return fn(jd, *args, **kwargs)

    return wrapper


def working_version(jd):
    """The version currently being edited — the highest version_number."""
    return jd.versions.order_by("-version_number").first()


def validate_jd_content(jd, version):
    """Raise InvalidJDInput (422) unless title+level and the body's summary /
    responsibilities / must_haves are present and non-empty."""
    missing = []
    if not (jd.title or "").strip():
        missing.append("title")
    if not (jd.level or "").strip():
        missing.append("level")
    body = version.body or {}
    if not str(body.get("summary", "")).strip():
        missing.append("summary")
    if not body.get("responsibilities"):
        missing.append("responsibilities")
    if not body.get("must_haves"):
        missing.append("must_haves")
    if missing:
        raise InvalidJDInput(missing)


def validate_generation_inputs(jd, version):
    """Raise InvalidJDInput (422) unless the JD carries the minimum inputs a
    generator needs: title, level and a non-empty inputs snapshot (the role brief
    the model works from). Checked BEFORE any provider call so we never ask a
    generator to invent a JD out of nothing."""
    missing = []
    if not (jd.title or "").strip():
        missing.append("title")
    if not (jd.level or "").strip():
        missing.append("level")
    if not (version.inputs_snapshot or {}):
        missing.append("inputs")
    if missing:
        raise InvalidJDInput(missing)


def create_jd(*, title, level, department="", actor, body=None, inputs=None, source=None):
    """Create a JD (DRAFT) with its first JDVersion. The single creation path."""
    tenant_id = actor.tenant_id
    with tenant_context(tenant_id):
        record(
            action="jd.created",
            actor=actor,
            target_type="job_description",
            target_id="",
            metadata={"title": title, "level": level},
            tenant=tenant_id,
        )
        jd = JobDescription.objects.create(
            tenant_id=tenant_id,
            title=title,
            level=level,
            department=department,
            status=S.DRAFT,
            source=source or JobDescription.Source.MANUAL,
            created_by=actor,
        )
        JDVersion.objects.create(
            tenant_id=tenant_id,
            jd=jd,
            version_number=1,
            body=body or {},
            inputs_snapshot=inputs or {},
            created_by=actor,
        )
        return jd


@_tenant_bound
def save_draft(jd, actor, *, body=None, inputs=None):
    """Edit the working version's body/inputs. Legal in DRAFT or PENDING (re-save
    keeps PENDING). Never edits a published version."""
    if jd.status not in (S.DRAFT, S.PENDING_HUMAN_REVIEW):
        raise IllegalJDTransition(jd.status, "save a draft for")
    version = working_version(jd)
    if version.is_published:
        # Defensive: a published version is immutable — revise() must run first.
        raise IllegalJDTransition(jd.status, "edit the published version of")
    if body is not None:
        version.body = body
    if inputs is not None:
        version.inputs_snapshot = inputs
    record(
        action="jd.drafted",
        actor=actor,
        target_type="job_description",
        target_id=jd.id,
        metadata={"version": version.version_number},
        tenant=jd.tenant_id,
    )
    version.save(update_fields=["body", "inputs_snapshot", "updated_at"])
    return jd


@_tenant_bound
def submit_for_review(jd, actor):
    """DRAFT -> PENDING_HUMAN_REVIEW. Validates required content first (422)."""
    if jd.status != S.DRAFT:
        raise IllegalJDTransition(jd.status, "submit for review")
    validate_jd_content(jd, working_version(jd))
    record(
        action="jd.submitted",
        actor=actor,
        target_type="job_description",
        target_id=jd.id,
        metadata={},
        tenant=jd.tenant_id,
    )
    jd.status = S.PENDING_HUMAN_REVIEW
    jd.save(update_fields=["status", "updated_at"])
    return jd


@_tenant_bound
def approve(jd, actor):
    """PENDING_HUMAN_REVIEW -> route (if an active "jd" workflow) or PUBLISH.

    The HRBP's human approval: with an active "jd" workflow it ENTERS the route
    (status IN_REVIEW + approval_route link); with none it single-step publishes.
    """
    if jd.status != S.PENDING_HUMAN_REVIEW:
        raise IllegalJDTransition(jd.status, "approve")

    record(
        action="jd.approved",
        actor=actor,
        target_type="job_description",
        target_id=jd.id,
        metadata={},
        tenant=jd.tenant_id,
    )

    # Lazy import keeps lifecycle import-order-independent of the approvals app.
    from apps.approvals.engine import active_workflow_for, start_route

    if jd.approval_route_id is None and active_workflow_for(jd.tenant_id, "jd"):
        route = start_route("jd", jd.id, initiated_by=actor, tenant_id=jd.tenant_id)
        record(
            action="jd.routed",
            actor=actor,
            target_type="job_description",
            target_id=jd.id,
            metadata={"route_id": str(route.id)},
            tenant=jd.tenant_id,
        )
        jd.status = S.IN_REVIEW
        jd.approval_route = route
        jd.save(update_fields=["status", "approval_route", "updated_at"])
        return jd

    return _publish(jd, actor)


def _publish(jd, actor):
    """Publish the working version — the audited PUBLISH. Called single-step by
    approve AND by the approval-route completion handler. Caller is tenant-bound."""
    version = working_version(jd)
    record(
        action="jd.published",
        actor=actor,
        target_type="job_description",
        target_id=jd.id,
        metadata={"version": version.version_number},
        tenant=jd.tenant_id,
    )
    version.is_published = True
    version.save(update_fields=["is_published", "updated_at"])
    jd.status = S.PUBLISHED
    jd.current_version = version
    jd.approval_route = None
    jd.save(update_fields=["status", "current_version", "approval_route", "updated_at"])
    return jd


@_tenant_bound
def route_rejected(jd, *, reason=""):
    """IN_REVIEW -> PENDING_HUMAN_REVIEW — the approval route rejected publication.

    Returns the JD to the author to revise; clears the route link. A re-approve
    starts a FRESH route. SYSTEM transition (the route's reject was the decision)."""
    if jd.status != S.IN_REVIEW:
        raise IllegalJDTransition(jd.status, "route-reject")
    record(
        action="jd.route_rejected",
        actor=None,
        target_type="job_description",
        target_id=jd.id,
        metadata={"reason": reason},
        tenant=jd.tenant_id,
    )
    jd.status = S.PENDING_HUMAN_REVIEW
    jd.approval_route = None
    jd.save(update_fields=["status", "approval_route", "updated_at"])
    return jd


@_tenant_bound
def revise(jd, actor):
    """PUBLISHED -> DRAFT by opening a NEW draft version (copying the published
    body as a starting point). The published version stays live + immutable until
    the new draft is itself published; ``current_version`` is untouched here."""
    if jd.status != S.PUBLISHED:
        raise IllegalJDTransition(jd.status, "revise")
    published = jd.current_version
    next_number = (jd.versions.order_by("-version_number").first().version_number) + 1
    record(
        action="jd.drafted",
        actor=actor,
        target_type="job_description",
        target_id=jd.id,
        metadata={"version": next_number, "revision_of": published.version_number if published else None},
        tenant=jd.tenant_id,
    )
    JDVersion.objects.create(
        tenant_id=jd.tenant_id,
        jd=jd,
        version_number=next_number,
        body=dict(published.body) if published else {},
        inputs_snapshot=dict(published.inputs_snapshot) if published else {},
        created_by=actor,
    )
    jd.status = S.DRAFT
    jd.save(update_fields=["status", "updated_at"])
    return jd


@_tenant_bound
def archive(jd, actor):
    """any (non-ARCHIVED) -> ARCHIVED."""
    if jd.status == S.ARCHIVED:
        raise IllegalJDTransition(jd.status, "archive")
    record(
        action="jd.archived",
        actor=actor,
        target_type="job_description",
        target_id=jd.id,
        metadata={},
        tenant=jd.tenant_id,
    )
    jd.status = S.ARCHIVED
    jd.save(update_fields=["status", "updated_at"])
    return jd
