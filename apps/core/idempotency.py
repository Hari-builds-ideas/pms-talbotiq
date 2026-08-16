"""
Idempotency keys for the operations you must not do twice (F7).

The endpoints that matter here — `submit`, `approve`, `finalize`, `checkout` —
share a shape: they move something forward one step, they write to the audit log,
and repeating one is not harmless. A double `approve` writes two approval records
for one decision; a double `checkout` charges twice.

The way it actually happens is not a malicious client. It is a phone on a train
losing the connection after the request reached the server, a browser retrying a
POST, or an impatient second click on a button whose spinner has not appeared
yet. In every one of those the caller genuinely does not know whether the first
attempt landed.

**The contract.** A client sends ``Idempotency-Key: <opaque string>``. Same key,
same request → the first response is replayed, byte for byte, with
``Idempotency-Replayed: true``. Same key, *different* request → ``409``, because
the two calls disagree about what was meant and guessing is worse than refusing.
No key → the endpoint behaves exactly as before.

**Why opt-in rather than required.** A required header would break every existing
client the moment it shipped, and the SPA sends one on the four operations that
need it. An endpoint that quietly ignores an unknown header is the failure this
avoids: a client that *believes* it is protected and is not. So a key that is
present is always honoured, and the four views that support it say so in their
docstring.

**Scope.** Keys are namespaced by tenant, user and endpoint. Two tenants that
happen to generate the same UUID must never collide, and one user's key must
never replay another's response — that would hand them a response about a record
they may not be allowed to see.
"""
from __future__ import annotations

import hashlib
import json
import logging
from functools import wraps

from django.db import IntegrityError, transaction
from rest_framework.response import Response

logger = logging.getLogger("pms.idempotency")

HEADER = "Idempotency-Key"
#: Meta key for the header above, as WSGI mangles it.
_META_KEY = "HTTP_IDEMPOTENCY_KEY"
REPLAY_HEADER = "Idempotency-Replayed"

#: Long enough for a UUID or a hash, short enough that a client cannot use the
#: table as storage.
MAX_KEY_LENGTH = 255


def key_from(request) -> str | None:
    raw = (request.META.get(_META_KEY) or "").strip()
    return raw[:MAX_KEY_LENGTH] or None


def fingerprint(request) -> str:
    """A stable hash of what this request is asking for.

    Includes the path and the body. Two calls with the same key must be the same
    call — if the body differs, the client has reused a key for a different
    operation, which is a bug on their side that this must not paper over by
    silently replaying the wrong response.

    Sorted keys so that a JSON object serialised in a different order is still
    recognised as the same request, which it is.
    """
    try:
        body = json.dumps(request.data, sort_keys=True, default=str)
    except (TypeError, ValueError):  # non-JSON body (file upload, form data)
        body = repr(sorted(request.data.items())) if hasattr(request.data, "items") else ""
    material = f"{request.method}\n{request.path}\n{body}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


#: Marker set by @idempotent, so a test can assert an endpoint still has it.
IDEMPOTENT_ATTR = "_supports_idempotency_key"


def idempotent(cls):
    """Class decorator: make this view's ``POST`` replayable under a client key.

    Usage::

        @idempotent
        class ReviewApproveView(_TransitionView):
            ...

    **A decorator rather than a mixin, and that is not a style choice.** A mixin
    can only intercept a method the class does not define itself: Python resolves
    ``self.post`` to the class's own attribute before it ever looks at a base,
    however early in the MRO that base sits. ``CheckoutView`` defines ``post``,
    so a mixin was silently inert there while looking perfectly wired — the
    endpoint accepted the header, ignored it, and executed twice. This wraps
    whatever ``post`` the class actually resolves to and installs the wrapper on
    the class, so it cannot be bypassed that way.

    Only successful responses (2xx) are stored. Replaying a 500 would make a
    transient failure permanent for that key, and replaying a 4xx would stop a
    client fixing its request and retrying with the same key — which is exactly
    what a client that just got a validation error will do.
    """
    original_post = cls.post

    @wraps(original_post)
    def post(self, request, *args, **kwargs):
        key = key_from(request)
        if key is None:
            return original_post(self, request, *args, **kwargs)

        from apps.core.models import IdempotencyRecord

        scope = f"{cls.__module__}.{cls.__name__}"
        digest = fingerprint(request)

        existing = IdempotencyRecord.objects.filter(
            tenant_id=request.user.tenant_id,
            user_id=request.user.id,
            scope=scope,
            key=key,
        ).first()
        if existing is not None:
            if existing.fingerprint != digest:
                # The client reused a key for a different request. Replaying the
                # stored response would answer a question nobody asked, and the
                # client — seeing a success — would never learn that the second
                # operation never happened.
                return Response(
                    {
                        "detail": (
                            "This Idempotency-Key was already used for a different "
                            "request. Use a new key."
                        ),
                        "code": "idempotency_key_reused",
                    },
                    status=409,
                )
            replay = Response(existing.response_body, status=existing.response_status)
            replay[REPLAY_HEADER] = "true"
            return replay

        response = original_post(self, request, *args, **kwargs)

        if 200 <= response.status_code < 300:
            try:
                with transaction.atomic():
                    IdempotencyRecord.objects.create(
                        tenant=request.user.tenant,
                        user=request.user,
                        scope=scope,
                        key=key,
                        fingerprint=digest,
                        response_status=response.status_code,
                        response_body=response.data,
                    )
            except IntegrityError:
                # Two identical requests raced and both missed the read above; the
                # unique constraint caught the loser. The work has been done twice,
                # which is the one window this cannot close from inside a single
                # request — but the client still gets a correct answer, and the row
                # that won is what future replays return. Logged, because a burst
                # of these means a client is retrying without waiting.
                logger.info("idempotency: concurrent duplicate for %s key=%s", scope, key)

        return response

    cls.post = post
    setattr(cls, IDEMPOTENT_ATTR, True)
    return cls
