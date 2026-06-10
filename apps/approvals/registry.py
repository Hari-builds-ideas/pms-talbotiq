"""
Artifact-type registry — keeps the approval engine GENERIC.

Each consuming module registers its artifact type with three callables so the
engine never imports the consumer (one-way dependency: consumers -> approvals):

* ``resolve_context(artifact_id) -> ResolutionContext`` — supplies the data the
  engine needs to resolve approvers at route start: the artifact's ``subject``,
  the subject's ``manager`` (for ROLE=MANAGER), and ``protected_user_ids`` (users
  who must NOT approve this artifact — the self-approval block; for a review that
  is the subject employee). Runs inside the bound tenant.
* ``on_route_complete(route)`` — called when the route is fully APPROVED; the
  consumer performs its real completion (e.g. the review's audited finalize).
* ``on_route_rejected(route)`` — called when the route is REJECTED; the consumer
  returns the artifact to its author.

Registration happens in each consumer's AppConfig.ready() (e.g.
apps.reviews.apps.ReviewsConfig.ready -> apps.reviews.approval_integration).
"""
from dataclasses import dataclass, field

from .exceptions import UnknownArtifactType


@dataclass(frozen=True)
class ResolutionContext:
    subject = None
    manager = None
    protected_user_ids: frozenset = field(default_factory=frozenset)

    def __init__(self, *, subject=None, manager=None, protected_user_ids=()):
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "manager", manager)
        object.__setattr__(self, "protected_user_ids", frozenset(protected_user_ids))


@dataclass(frozen=True)
class ArtifactHandler:
    artifact_type: str
    resolve_context: callable
    on_route_complete: callable
    on_route_rejected: callable


_REGISTRY = {}


def register(artifact_type, *, resolve_context, on_route_complete, on_route_rejected):
    """Register (or replace) the handler for ``artifact_type``. Idempotent — safe
    to call from AppConfig.ready()."""
    _REGISTRY[artifact_type] = ArtifactHandler(
        artifact_type=artifact_type,
        resolve_context=resolve_context,
        on_route_complete=on_route_complete,
        on_route_rejected=on_route_rejected,
    )


def get_handler(artifact_type):
    handler = _REGISTRY.get(artifact_type)
    if handler is None:
        raise UnknownArtifactType(artifact_type)
    return handler


def is_registered(artifact_type):
    return artifact_type in _REGISTRY
