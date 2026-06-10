"""
A registered TEST artifact type ("widget") so the engine is tested independently
of any real consumer. A module-level map links a widget's UUID to its resolution
context; the completion/rejection callbacks record the route ids they fired on.
"""
import uuid

import pytest

from apps.approvals import registry
from apps.approvals.registry import ResolutionContext

WIDGETS = {}          # artifact_id(str) -> {"subject", "manager", "protected"}
COMPLETED = []        # route ids that fired on_route_complete
REJECTED = []         # route ids that fired on_route_rejected


def _resolve(artifact_id):
    spec = WIDGETS[str(artifact_id)]
    return ResolutionContext(
        subject=spec.get("subject"),
        manager=spec.get("manager"),
        protected_user_ids=spec.get("protected", set()),
    )


def _complete(route):
    COMPLETED.append(str(route.id))


def _reject(route):
    REJECTED.append(str(route.id))


registry.register(
    "widget",
    resolve_context=_resolve,
    on_route_complete=_complete,
    on_route_rejected=_reject,
)


@pytest.fixture
def widget():
    """Register a widget artifact and return (artifact_id, setter).

    Usage:
        wid, set_ctx = widget
        set_ctx(subject=..., manager=..., protected={...})
    """
    artifact_id = str(uuid.uuid4())
    WIDGETS[artifact_id] = {"subject": None, "manager": None, "protected": set()}

    def set_ctx(**kwargs):
        WIDGETS[artifact_id].update(kwargs)

    yield artifact_id, set_ctx
    WIDGETS.pop(artifact_id, None)


@pytest.fixture(autouse=True)
def _reset_callback_logs():
    COMPLETED.clear()
    REJECTED.clear()
    yield
    COMPLETED.clear()
    REJECTED.clear()
