"""
Approval signals — decoupled notification seam (the Module-12 Slack push connects
here; the approvals engine stays unaware of integrations, exactly as Module 5
documented: "the engine composes/sends NOTHING").

Both fire with ``send_robust`` so a misbehaving receiver can NEVER break the
approval flow (best-effort notifications).
"""
from django.dispatch import Signal

#: A step has become active/assigned. kwargs: tenant_id, route_id, order,
#: artifact_type, approver_id (may be None for a role-slot step).
approval_step_assigned = Signal()

#: An overdue step has been escalated/reassigned. kwargs: tenant_id, route_id, order.
approval_step_escalated = Signal()
