"""
The approval engine — deterministic, fully audited, tenant-bound.

No randomness, no AI. Every decision and state change writes an immutable audit
record BEFORE it takes effect (CLAUDE.md rule). The engine runs both on-request
(decisions via the API) and off-request (the escalation beat task), so every
public entry binds the tenant itself (scoped managers fail closed otherwise — the
lesson from Modules 2/3/4).

Sequential vs parallel:
  * SEQUENTIAL — steps run in ``order``; the ACTIVE step is the lowest-order
    PENDING one (computed, not stored). A decision on any other step is rejected
    (out-of-order). Approve advances to the next step; the last approval completes
    the route. A reject anywhere ends the route (REJECTED).
  * PARALLEL — all steps PENDING at once. The route completes APPROVED when every
    REQUIRED step is approved; ANY required reject ends it REJECTED; non-required
    steps are advisory and never block.

Self-approval block: a step resolving to a ``protected_user_id`` (for a review,
the subject employee) is reassigned to the escalation target at start — the
protected party can never approve their own artifact.
"""
import logging

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.services import record
from apps.identity.models import User
from apps.rbac.matrix import Capability, role_has_capability
from apps.tenancy.context import get_current_tenant_id, tenant_context

from . import registry
from .exceptions import ActiveRouteExists, IllegalDecision, RouteApproverUnresolvable
from .models import (
    ApprovalRoute,
    ApprovalStep,
    ApprovalStepInstance,
    ApprovalWorkflow,
)
from .signals import approval_step_assigned, approval_step_escalated

logger = logging.getLogger("pms.approvals")

_ROLE_SLOTS = {"HRBP", "ADMIN"}  # roles that act as any-holder slots (tenant-wide)


def active_workflow_for(tenant_id, artifact_type):
    """The single active workflow for (tenant, artifact_type), or None.

    Used by consumers (e.g. review.finalize) to decide route-vs-passthrough.
    """
    with tenant_context(tenant_id):
        return (
            ApprovalWorkflow.objects.filter(artifact_type=artifact_type, active=True)
            .order_by("created_at")
            .first()
        )


def activate_workflow(workflow):
    """Make ``workflow`` the sole active one for its (tenant, artifact_type).

    Deactivates any prior active workflow for the same type (at-most-one-active —
    MySQL has no partial unique, so the rule lives here). Tenant-bound.
    """
    with tenant_context(workflow.tenant_id):
        ApprovalWorkflow.objects.filter(
            artifact_type=workflow.artifact_type, active=True
        ).exclude(id=workflow.id).update(active=False)
        workflow.active = True
        workflow.save(update_fields=["active", "updated_at"])
        return workflow


# ── approver resolution ─────────────────────────────────────────────────────


def _escalation_target(step, context):
    """Resolve a step's escalation target -> (approver_user, approver_role).

    Order: explicit escalation_user > escalation_role (MANAGER resolves to the
    subject's manager, HRBP/ADMIN are slots) > ADMIN slot fallback. Returns
    (None, "ADMIN") as the universal fallback so a tenant Admin can always act.
    """
    if step.escalation_user_id:
        return step.escalation_user, None
    role = step.escalation_role
    if role == "MANAGER":
        return (context.manager, None) if context.manager else (None, "ADMIN")
    if role in _ROLE_SLOTS:
        return None, role
    return None, "ADMIN"  # fallback: a tenant Admin always can act


def _resolve_step(step, context):
    """Resolve a template step to (approver_user, approver_role, escalated).

    ROLE=MANAGER -> the subject's direct manager (specific user).
    ROLE=HRBP/ADMIN -> a role-slot (approver_user None, approver_role set).
    NAMED -> the specific user.
    Self-approval (resolved user in protected_user_ids) -> reassigned to the
    escalation target (escalated=True). An unresolvable required slot raises 422.
    """
    if step.approver_kind == ApprovalStep.ApproverKind.NAMED:
        approver, role = step.approver_user, None
    elif step.approver_role == "MANAGER":
        approver, role = context.manager, None
        if approver is None:
            # No manager to resolve to -> try escalation, else unresolvable.
            esc_user, esc_role = _escalation_target(step, context)
            if esc_user is None and esc_role is None:
                raise RouteApproverUnresolvable(
                    "ROLE=MANAGER step has no manager and no escalation target"
                )
            return esc_user, esc_role, True
    elif step.approver_role in _ROLE_SLOTS:
        approver, role = None, step.approver_role
    else:
        raise RouteApproverUnresolvable(
            f"step {step.order} has an unrecognised approver configuration"
        )

    # Self-approval block: a protected user (the subject) may never approve.
    if approver is not None and approver.id in context.protected_user_ids:
        esc_user, esc_role = _escalation_target(step, context)
        # If the escalation target is ALSO protected, fall through to ADMIN slot.
        if esc_user is not None and esc_user.id in context.protected_user_ids:
            esc_user, esc_role = None, "ADMIN"
        return esc_user, esc_role, True

    return approver, role, False


# ── starting a route ────────────────────────────────────────────────────────


def start_route(artifact_type, artifact_id, *, initiated_by, tenant_id=None):
    """Snapshot the active workflow into a running route for ``artifact_id``.

    Returns the created ApprovalRoute, or None when no active workflow exists for
    the type (the caller then takes its non-routed path). Raises ActiveRouteExists
    (409) if a route is already in flight for the artifact, or
    RouteApproverUnresolvable (422) — in which case NO partial route is created.
    """
    tenant_id = tenant_id or get_current_tenant_id()
    with tenant_context(tenant_id):
        workflow = (
            ApprovalWorkflow.objects.filter(artifact_type=artifact_type, active=True)
            .order_by("created_at")
            .first()
        )
        if workflow is None:
            return None

        if ApprovalRoute.objects.filter(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            status=ApprovalRoute.Status.IN_PROGRESS,
        ).exists():
            raise ActiveRouteExists(artifact_type, artifact_id)

        context = registry.get_handler(artifact_type).resolve_context(artifact_id)
        steps = list(workflow.steps.order_by("order"))
        if not steps:
            raise RouteApproverUnresolvable(f"workflow '{workflow.name}' has no steps")

        # Resolve EVERY step first; a failure raises before any row is written.
        resolved = [(step, *_resolve_step(step, context)) for step in steps]

        now = timezone.now()
        route = ApprovalRoute.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            mode=workflow.mode,
            status=ApprovalRoute.Status.IN_PROGRESS,
            initiated_by=initiated_by,
            started_at=now,
        )

        sequential = workflow.mode == ApprovalWorkflow.Mode.SEQUENTIAL
        active_instances = []
        for idx, (step, approver, approver_role, escalated) in enumerate(resolved):
            # SEQUENTIAL: only the first step's clock starts now. PARALLEL: all.
            is_active_now = (not sequential) or idx == 0
            due_at = None
            if is_active_now and step.timeout_hours:
                due_at = now + timezone.timedelta(hours=step.timeout_hours)
            instance = ApprovalStepInstance.objects.create(
                tenant_id=tenant_id,
                route=route,
                order=step.order,
                approver=approver,
                approver_role=approver_role,
                required=step.required,
                status=ApprovalStepInstance.Status.PENDING,
                due_at=due_at,
                timeout_hours=step.timeout_hours,
                escalation_role=step.escalation_role,
                escalation_user=step.escalation_user,
                escalated=escalated,
            )
            if is_active_now:
                active_instances.append(instance)

        record(
            action="route.started",
            actor=initiated_by,
            target_type="approval_route",
            target_id=route.id,
            metadata={
                "artifact_type": artifact_type,
                "artifact_id": str(artifact_id),
                "mode": workflow.mode,
                "steps": len(resolved),
            },
            tenant=tenant_id,
        )
        # Module-12 Slack push seam: notify the initially-active assignee(s)
        # (best-effort; send_robust so a receiver can never break the route).
        for instance in active_instances:
            _notify_assigned(route, instance)
        return route


def _notify_assigned(route, step_instance):
    """Fire the ``approval_step_assigned`` signal for an active step (best-effort —
    ``send_robust`` so a receiver bug can never break the approval flow)."""
    approval_step_assigned.send_robust(
        sender=start_route,
        tenant_id=str(route.tenant_id),
        route_id=str(route.id),
        order=step_instance.order,
        artifact_type=route.artifact_type,
        approver_id=str(step_instance.approver_id) if step_instance.approver_id else None,
    )


# ── deciding a step ─────────────────────────────────────────────────────────


def _active_sequential_step(route):
    return (
        route.step_instances.filter(status=ApprovalStepInstance.Status.PENDING)
        .order_by("order")
        .first()
    )


def _authorize_decider(step, actor, context):
    """Raise PermissionDenied unless ``actor`` may decide ``step``."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication required to decide an approval step.")
    # Cross-tenant can never act, even a same-role-slot holder in another tenant.
    if str(actor.tenant_id) != str(step.tenant_id):
        raise PermissionDenied("This approval step belongs to a different tenant.")
    if not role_has_capability(actor.role, Capability.ACT_ON_APPROVAL_STEP):
        raise PermissionDenied("Your role cannot act on approval steps.")
    # Self-approval can never sneak in via a role-slot the protected user holds.
    if actor.id in context.protected_user_ids:
        raise PermissionDenied("You cannot approve your own artifact.")
    if step.approver_id is not None:
        if actor.id != step.approver_id:
            raise PermissionDenied("You are not the assigned approver for this step.")
    else:
        # Role-slot: any in-scope holder of the role (HRBP/ADMIN are tenant-wide).
        if actor.role != step.approver_role:
            raise PermissionDenied(
                f"This step requires a {step.approver_role}; you are a {actor.role}."
            )


def record_decision(step_instance, actor, decision, comment=""):
    """Record an APPROVE/REJECT on a step and advance the route. Tenant-bound.

    The acting user must be the assigned approver (NAMED/MANAGER) or an in-scope
    holder of the step's role-slot (HRBP/ADMIN); the protected subject can never
    decide. A non-active / already-decided step, or a route not IN_PROGRESS, is
    rejected (409) — never a silent no-op. Audits BEFORE the effect.
    """
    decision = str(decision).upper()
    if decision not in ("APPROVE", "REJECT"):
        raise IllegalDecision(f"Unknown decision '{decision}'.")

    with tenant_context(step_instance.tenant_id):
        route = step_instance.route
        if route.status != ApprovalRoute.Status.IN_PROGRESS:
            raise IllegalDecision(
                "The route is no longer in progress.", route_status=route.status
            )
        if step_instance.status != ApprovalStepInstance.Status.PENDING:
            raise IllegalDecision(
                "This step has already been decided.", step_status=step_instance.status
            )
        if route.mode == ApprovalWorkflow.Mode.SEQUENTIAL:
            active = _active_sequential_step(route)
            if active is None or active.id != step_instance.id:
                raise IllegalDecision(
                    "Sequential steps must be decided in order; this step is not active yet.",
                    step_status=step_instance.status,
                )

        context = registry.get_handler(route.artifact_type).resolve_context(route.artifact_id)
        _authorize_decider(step_instance, actor, context)

        audit_action = "step.approved" if decision == "APPROVE" else "step.rejected"
        record(
            action=audit_action,
            actor=actor,
            target_type="approval_route",
            target_id=route.id,
            metadata={"order": step_instance.order, "decision": decision},
            tenant=route.tenant_id,
        )

        now = timezone.now()
        step_instance.status = (
            ApprovalStepInstance.Status.APPROVED
            if decision == "APPROVE"
            else ApprovalStepInstance.Status.REJECTED
        )
        step_instance.decided_by = actor
        step_instance.decided_at = now
        step_instance.comment = comment or ""
        step_instance.save(
            update_fields=["status", "decided_by", "decided_at", "comment", "updated_at"]
        )

        if decision == "REJECT":
            _reject_route(route, actor)
        else:
            _advance_after_approval(route, step_instance, actor)
        return step_instance


def _advance_after_approval(route, step_instance, actor):
    if route.mode == ApprovalWorkflow.Mode.SEQUENTIAL:
        nxt = _active_sequential_step(route)
        if nxt is None:
            _complete_route(route, actor)
        else:
            # Start the next step's clock as it becomes active.
            if nxt.timeout_hours and nxt.due_at is None:
                nxt.due_at = timezone.now() + timezone.timedelta(hours=nxt.timeout_hours)
                nxt.save(update_fields=["due_at", "updated_at"])
            # Notify the newly-active assignee (best-effort Slack push seam).
            _notify_assigned(route, nxt)
        return

    # PARALLEL: complete when every REQUIRED step is approved; a required reject
    # already ended the route above.
    required = route.step_instances.filter(required=True)
    if not required.exclude(status=ApprovalStepInstance.Status.APPROVED).exists():
        _complete_route(route, actor)


def _complete_route(route, actor):
    record(
        action="route.completed",
        actor=actor,
        target_type="approval_route",
        target_id=route.id,
        metadata={"artifact_type": route.artifact_type, "artifact_id": str(route.artifact_id)},
        tenant=route.tenant_id,
    )
    route.status = ApprovalRoute.Status.APPROVED
    route.completed_at = timezone.now()
    route.save(update_fields=["status", "completed_at", "updated_at"])
    registry.get_handler(route.artifact_type).on_route_complete(route)


def _reject_route(route, actor):
    record(
        action="route.rejected",
        actor=actor,
        target_type="approval_route",
        target_id=route.id,
        metadata={"artifact_type": route.artifact_type, "artifact_id": str(route.artifact_id)},
        tenant=route.tenant_id,
    )
    route.status = ApprovalRoute.Status.REJECTED
    route.completed_at = timezone.now()
    route.save(update_fields=["status", "completed_at", "updated_at"])
    registry.get_handler(route.artifact_type).on_route_rejected(route)


# ── escalation (called by the beat task per overdue step) ────────────────────


def escalate_step(step_instance):
    """Reassign an overdue PENDING step to its escalation target. Tenant-bound.

    In-place reassign (escalated=True, new clock) so the new approver can act;
    audited ``step.escalated``. If somehow no target resolves at all, the step and
    route go ESCALATED (stuck, needs manual intervention) — but the ADMIN-slot
    fallback means that does not happen for a tenant with any Admin.
    """
    with tenant_context(step_instance.tenant_id):
        route = step_instance.route
        if (
            route.status != ApprovalRoute.Status.IN_PROGRESS
            or step_instance.status != ApprovalStepInstance.Status.PENDING
        ):
            return step_instance  # no longer escalatable; nothing to do

        # Build a fake "step" carrying this instance's escalation snapshot, and a
        # context whose manager is unknown here (escalation_role=MANAGER on an
        # instance falls back to ADMIN — managers are resolved only at start).
        class _Snap:
            escalation_user_id = step_instance.escalation_user_id
            escalation_user = step_instance.escalation_user
            escalation_role = step_instance.escalation_role

        ctx = registry.get_handler(route.artifact_type).resolve_context(route.artifact_id)
        target_user, target_role = _escalation_target(_Snap, ctx)

        record(
            action="step.escalated",
            actor=None,
            target_type="approval_route",
            target_id=route.id,
            metadata={
                "order": step_instance.order,
                "to_user": str(target_user.id) if target_user else None,
                "to_role": target_role,
            },
            tenant=route.tenant_id,
        )

        if target_user is None and target_role is None:
            step_instance.status = ApprovalStepInstance.Status.ESCALATED
            step_instance.escalated = True
            step_instance.save(update_fields=["status", "escalated", "updated_at"])
            route.status = ApprovalRoute.Status.ESCALATED
            route.save(update_fields=["status", "updated_at"])
            return step_instance

        step_instance.approver = target_user
        step_instance.approver_role = target_role
        step_instance.escalated = True
        if step_instance.timeout_hours:
            step_instance.due_at = timezone.now() + timezone.timedelta(
                hours=step_instance.timeout_hours
            )
        step_instance.save(
            update_fields=["approver", "approver_role", "escalated", "due_at", "updated_at"]
        )
        # Module-12 Slack push seam: notify that the step was escalated/reassigned
        # (best-effort; send_robust so a receiver can never break the sweep).
        approval_step_escalated.send_robust(
            sender=escalate_step,
            tenant_id=str(route.tenant_id),
            route_id=str(route.id),
            order=step_instance.order,
        )
        return step_instance


def overdue_pending_steps():
    """All overdue PENDING steps across ALL tenants (system scan, off-request).

    Uses the cross-tenant escape (allowed off the request path); the caller then
    escalates each within its own tenant context.
    """
    now = timezone.now()
    return list(
        ApprovalStepInstance.objects.all_tenants()
        .filter(status=ApprovalStepInstance.Status.PENDING, due_at__isnull=False, due_at__lt=now)
    )
