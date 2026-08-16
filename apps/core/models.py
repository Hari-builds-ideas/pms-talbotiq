"""
Cross-cutting models. Currently one: the idempotency ledger (F7).

It lives in ``core`` rather than in ``reviews`` or ``billing`` because the four
endpoints it protects sit in three different apps, and a shared table beats three
near-identical ones.
"""
from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel


class IdempotencyRecord(TenantScopedModel):
    """One stored response, keyed by (tenant, user, endpoint, client key).

    Scoped by tenant AND user deliberately. Two tenants can generate the same
    UUID, and a key belonging to one user must never replay a response to
    another — that would hand them the body of a request about a record they may
    have no right to see. The endpoint (``scope``) is in the key as well, so a
    client reusing one key across two operations gets a 409 rather than the wrong
    response.

    The stored body is the DRF response data, before rendering. It is replayed
    verbatim.
    """

    #: The requesting user. Not the tenant's admin, the actual caller.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="idempotency_records",
    )
    #: Dotted path of the view class — one namespace per endpoint.
    scope = models.CharField(max_length=255)
    #: The opaque value the client sent in Idempotency-Key.
    key = models.CharField(max_length=255)
    #: SHA-256 of method + path + body. A second call under the same key with a
    #: different fingerprint is a client bug, and answering it with the stored
    #: response would answer a question nobody asked.
    fingerprint = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "core_idempotency_record"
        constraints = [
            # The actual guarantee. Two concurrent identical requests both miss
            # the read and both try to insert; this is what stops the second from
            # creating a duplicate row and makes the replay deterministic.
            models.UniqueConstraint(
                fields=["tenant", "user", "scope", "key"],
                name="uq_idempotency_tenant_user_scope_key",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="ix_idem_tenant_created"),
        ]

    def __str__(self):
        return f"{self.scope} {self.key} -> {self.response_status}"
