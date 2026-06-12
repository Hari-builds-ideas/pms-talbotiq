"""
Feedback signals — decoupled notification seam (the Module-12 Slack push connects
here; the feedback app stays unaware of integrations).

``feedback_request_sent`` fires AFTER a ``FeedbackRequest`` invitation is created.
Emit with ``send_robust`` so a misbehaving receiver can NEVER break the invitation
(best-effort notifications).
"""
from django.dispatch import Signal

#: kwargs: tenant_id (str), request_id (str), giver_id (str), relationship (str)
feedback_request_sent = Signal()
