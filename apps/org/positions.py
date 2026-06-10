"""
Position writes (HRBP/Admin) — create / fill / close / link-JD / unlink-JD.

Each is guarded, audits BEFORE the effect, and invalidates the tenant org cache
so the next tree / vacancy read reflects the change. ``reports_to`` and
``filled_by`` must be active + in-tenant; a linked JD must be PUBLISHED +
in-tenant. Every entry binds the tenant explicitly (off-request safe).
"""
from __future__ import annotations

from django.utils import timezone

from apps.audit.services import record
from apps.tenancy.context import tenant_context

from .exceptions import (
    IllegalPositionTransition,
    InvalidOrgInput,
    PositionAlreadyFilled,
)
from .models import Position
from .services import invalidate_org_cache


def _require_active_in_tenant(user, actor, *, role):
    """Validate that ``user`` is present, active, and in the actor's tenant."""
    if user is None:
        raise InvalidOrgInput(f"{role}_missing", f"The {role} could not be found.")
    if str(user.tenant_id) != str(actor.tenant_id):
        raise InvalidOrgInput(f"{role}_cross_tenant", f"The {role} is in another tenant.")
    if not user.is_active:
        raise InvalidOrgInput(f"{role}_inactive", f"The {role} is not active.")


def _validate_published_jd(jd, actor):
    """A linkable JD must be PUBLISHED and in the actor's tenant (else 422)."""
    from apps.jd.models import JobDescription

    if jd is None:
        raise InvalidOrgInput("jd_missing", "The job description could not be found.")
    if str(jd.tenant_id) != str(actor.tenant_id):
        raise InvalidOrgInput("jd_cross_tenant", "That job description is in another tenant.")
    if jd.status != JobDescription.Status.PUBLISHED:
        raise InvalidOrgInput(
            "jd_not_published", "Only a PUBLISHED job description can be linked."
        )


def create_position(actor, *, title, reports_to, department=None, published_jd=None):
    """Create an OPEN position (a vacancy) reporting to ``reports_to``."""
    _require_active_in_tenant(reports_to, actor, role="manager")
    if published_jd is not None:
        _validate_published_jd(published_jd, actor)
    tid = actor.tenant_id
    with tenant_context(tid):
        record(
            action="position.created",
            actor=actor,
            target_type="position",
            target_id="",
            metadata={"title": title, "reports_to": str(reports_to.id)},
            tenant=tid,
        )
        position = Position.objects.create(
            tenant_id=tid,
            title=title,
            reports_to=reports_to,
            department=department or None,
            status=Position.Status.OPEN,
            published_jd=published_jd,
            opened_at=timezone.now(),
            created_by=actor,
        )
    # A new OPEN position is a vacancy under reports_to: invalidate so the next
    # tree read rolls it up (the /vacancies list reads live, but the cached tree
    # must refresh too).
    invalidate_org_cache(tid)
    return position


def fill_position(actor, position, filled_by):
    """Fill an OPEN position: set ``filled_by`` + FILLED + ``filled_at``.

    Filling an already-FILLED position is 409 POSITION_ALREADY_FILLED; filling a
    CLOSED one is 409 ILLEGAL_POSITION_TRANSITION."""
    if position.status == Position.Status.FILLED:
        raise PositionAlreadyFilled(position.id)
    if position.status != Position.Status.OPEN:
        raise IllegalPositionTransition(position.status, "fill")
    _require_active_in_tenant(filled_by, actor, role="employee")
    with tenant_context(position.tenant_id):
        record(
            action="position.filled",
            actor=actor,
            target_type="position",
            target_id=position.id,
            metadata={"filled_by": str(filled_by.id)},
            tenant=position.tenant_id,
        )
        position.filled_by = filled_by
        position.status = Position.Status.FILLED
        position.filled_at = timezone.now()
        position.save(update_fields=["filled_by", "status", "filled_at", "updated_at"])
    invalidate_org_cache(position.tenant_id)
    return position


def close_position(actor, position):
    """Close an OPEN/FILLED position (→ CLOSED), clearing the vacancy. Closing a
    CLOSED position is 409 ILLEGAL_POSITION_TRANSITION."""
    if position.status == Position.Status.CLOSED:
        raise IllegalPositionTransition(position.status, "close")
    with tenant_context(position.tenant_id):
        record(
            action="position.closed",
            actor=actor,
            target_type="position",
            target_id=position.id,
            metadata={"from_status": position.status},
            tenant=position.tenant_id,
        )
        position.status = Position.Status.CLOSED
        position.save(update_fields=["status", "updated_at"])
    invalidate_org_cache(position.tenant_id)
    return position


def link_jd(actor, position, jd):
    """Link a PUBLISHED, in-tenant JD to the position (422 otherwise)."""
    _validate_published_jd(jd, actor)
    with tenant_context(position.tenant_id):
        record(
            action="position.jd_linked",
            actor=actor,
            target_type="position",
            target_id=position.id,
            metadata={"jd": str(jd.id)},
            tenant=position.tenant_id,
        )
        position.published_jd = jd
        position.save(update_fields=["published_jd", "updated_at"])
    invalidate_org_cache(position.tenant_id)
    return position


def unlink_jd(actor, position):
    """Clear the position's linked JD."""
    with tenant_context(position.tenant_id):
        record(
            action="position.jd_unlinked",
            actor=actor,
            target_type="position",
            target_id=position.id,
            metadata={"jd": str(position.published_jd_id) if position.published_jd_id else None},
            tenant=position.tenant_id,
        )
        position.published_jd = None
        position.save(update_fields=["published_jd", "updated_at"])
    invalidate_org_cache(position.tenant_id)
    return position
