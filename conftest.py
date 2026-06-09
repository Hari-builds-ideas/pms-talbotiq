"""
Project-wide pytest fixtures.

Exposes the common building blocks every app's tests rely on: tenants, users by
role, and a ready-made org (reporting tree). Factories live in
``apps.testsupport.factories`` and are importable directly where finer control
is needed.
"""
from types import SimpleNamespace

import pytest

from apps.testsupport.factories import TenantFactory, UserFactory


@pytest.fixture(autouse=True)
def _clear_caches():
    """Isolate tests that touch the cache. The test cache is real Redis on
    dedicated scratch DBs (see config.settings.test), so flush them around every
    test to prevent cross-test bleed."""
    from django.core.cache import caches

    for alias in ("default", "sessions"):
        caches[alias].clear()
    yield
    for alias in ("default", "sessions"):
        caches[alias].clear()


@pytest.fixture
def tenant(db):
    return TenantFactory()


@pytest.fixture
def other_tenant(db):
    return TenantFactory()


@pytest.fixture
def make_user(db):
    """Callable: make_user(tenant=..., role=..., manager=..., email=...)."""

    def _make(**kwargs):
        return UserFactory(**kwargs)

    return _make


@pytest.fixture
def org(db):
    """A single-tenant org with one user per role and a reporting line:

        admin, hrbp
        manager
          └── report   (EMPLOYEE reporting to manager)
        peer           (EMPLOYEE reporting to hrbp — a peer of `report`)
    """
    t = TenantFactory(slug="acme", name="Acme")
    admin = UserFactory(tenant=t, role="ADMIN", email="admin@acme.test")
    hrbp = UserFactory(tenant=t, role="HRBP", email="hrbp@acme.test")
    manager = UserFactory(tenant=t, role="MANAGER", email="manager@acme.test", manager=hrbp)
    report = UserFactory(tenant=t, role="EMPLOYEE", email="report@acme.test", manager=manager)
    peer = UserFactory(tenant=t, role="EMPLOYEE", email="peer@acme.test", manager=hrbp)
    return SimpleNamespace(
        tenant=t, admin=admin, hrbp=hrbp, manager=manager, report=report, peer=peer
    )
