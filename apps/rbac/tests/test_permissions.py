"""
Unit tests for the DRF permission classes, the RBACMixin, the decorator, and
``require_capability`` — exercised directly (no HTTP) with lightweight stubs for
``request`` and ``view``. End-to-end HTTP integration is covered in
``test_e2e_http.py``.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from apps.identity.models import User
from apps.rbac.decorators import requires_capability
from apps.rbac.matrix import Capability
from apps.rbac.mixins import RBACMixin
from apps.rbac.permissions import (
    HasCapability,
    WithinScope,
    require_capability,
)
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


def _request(user):
    return SimpleNamespace(user=user)


def _anon():
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=False, role=None))


# ── HasCapability ──────────────────────────────────────────────────────
def test_has_capability_grants_when_role_holds_it(org):
    view = SimpleNamespace(required_capability=Capability.APPROVE_REVIEW)
    assert HasCapability().has_permission(_request(org.manager), view) is True


def test_has_capability_denies_when_role_lacks_it(org):
    view = SimpleNamespace(required_capability=Capability.APPROVE_REVIEW)
    assert HasCapability().has_permission(_request(org.report), view) is False


def test_has_capability_denies_unauthenticated(org):
    view = SimpleNamespace(required_capability=Capability.VIEW_OWN)
    assert HasCapability().has_permission(_anon(), view) is False


def test_has_capability_denies_when_view_declares_nothing(org):
    view = SimpleNamespace(required_capability=None)
    assert HasCapability().has_permission(_request(org.admin), view) is False


# ── require_capability factory ─────────────────────────────────────────
def test_require_capability_factory_pins_capability(org):
    perm = require_capability(Capability.MANAGE_TENANT)()
    # View attribute is ignored; the pinned capability wins.
    view = SimpleNamespace(required_capability=Capability.VIEW_OWN)
    assert perm.has_permission(_request(org.admin), view) is True
    assert perm.has_permission(_request(org.hrbp), view) is False


# ── WithinScope (object-level) ─────────────────────────────────────────
def test_within_scope_object_is_user_directly(org):
    view = SimpleNamespace()  # no scope_subject_attr -> obj IS the subject
    perm = WithinScope()
    with tenant_context(org.tenant):
        assert perm.has_object_permission(_request(org.manager), view, org.report) is True
        assert perm.has_object_permission(_request(org.manager), view, org.peer) is False


def test_within_scope_resolves_subject_via_attr(org):
    # A record whose subject is named by scope_subject_attr.
    record = SimpleNamespace(employee=org.report)
    view = SimpleNamespace(scope_subject_attr="employee")
    with tenant_context(org.tenant):
        assert WithinScope().has_object_permission(_request(org.manager), view, record) is True
        # Manager cannot reach a record about the out-of-scope peer.
        record_peer = SimpleNamespace(employee=org.peer)
        assert WithinScope().has_object_permission(_request(org.manager), view, record_peer) is False


def test_within_scope_unwraps_user_fk(org):
    # scope_subject_attr names an object that itself carries a `.user` FK.
    holder = SimpleNamespace(user=org.report)
    record = SimpleNamespace(assignment=holder)
    view = SimpleNamespace(scope_subject_attr="assignment")
    with tenant_context(org.tenant):
        assert WithinScope().has_object_permission(_request(org.manager), view, record) is True


def test_within_scope_unresolvable_subject_fails_closed(org):
    view = SimpleNamespace(scope_subject_attr="missing")
    record = SimpleNamespace()  # no `missing` attr
    with tenant_context(org.tenant):
        assert WithinScope().has_object_permission(_request(org.manager), view, record) is False


def test_within_scope_has_permission_is_open(org):
    # Request-level admission is HasCapability's job; WithinScope never blocks there.
    assert WithinScope().has_permission(_request(org.report), SimpleNamespace()) is True


# ── RBACMixin ──────────────────────────────────────────────────────────
def test_mixin_permission_stack_without_scope():
    class V(RBACMixin):
        required_capability = Capability.APPROVE_REVIEW

    classes = {type(p).__name__ for p in V().get_permissions()}
    assert "IsAuthenticated" in classes
    assert "HasCapability" in classes
    assert "WithinScope" not in classes


def test_mixin_permission_stack_with_scope_attr():
    class V(RBACMixin):
        required_capability = Capability.APPROVE_REVIEW
        scope_subject_attr = "employee"

    classes = {type(p).__name__ for p in V().get_permissions()}
    assert "WithinScope" in classes


def test_mixin_permission_stack_with_enforce_flag():
    class V(RBACMixin):
        required_capability = Capability.VIEW_TEAM_ANALYTICS
        enforce_object_scope = True

    classes = {type(p).__name__ for p in V().get_permissions()}
    assert "WithinScope" in classes


def test_check_object_scope_passes_in_scope(org):
    class V(RBACMixin):
        enforce_object_scope = True

    view = V()
    view.request = _request(org.manager)
    with tenant_context(org.tenant):
        view.check_object_scope(org.report)  # must not raise


def test_check_object_scope_raises_out_of_scope(org):
    class V(RBACMixin):
        enforce_object_scope = True

    view = V()
    view.request = _request(org.manager)
    with tenant_context(org.tenant):
        with pytest.raises(PermissionDenied):
            view.check_object_scope(org.peer)


# ── requires_capability decorator ──────────────────────────────────────
def test_decorator_allows_authorized(org):
    @requires_capability(Capability.APPROVE_REVIEW)
    def view(request):
        return "ok"

    assert view(_request(org.manager)) == "ok"


def test_decorator_denies_unauthorized(org):
    @requires_capability(Capability.APPROVE_REVIEW)
    def view(request):
        return "ok"

    with pytest.raises(PermissionDenied):
        view(_request(org.report))


def test_decorator_denies_unauthenticated():
    @requires_capability(Capability.VIEW_OWN)
    def view(request):
        return "ok"

    with pytest.raises(NotAuthenticated):
        view(_anon())


def test_decorator_supports_method_signature(org):
    @requires_capability(Capability.MANAGE_TENANT)
    def method(self, request):
        return "ok"

    obj = object()
    assert method(obj, _request(org.admin)) == "ok"
    with pytest.raises(PermissionDenied):
        method(obj, _request(org.hrbp))
