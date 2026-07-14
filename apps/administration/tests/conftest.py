"""Shared fixtures for the administration test suite (PROD_B bulk import)."""
from types import SimpleNamespace

import pytest

from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory


@pytest.fixture
def org(db):
    """A tenant with the four roles + generous seats. Exactly 5 users so a
    ``set_seats(5)`` in a test makes the tenant full (seat-limit proofs)."""
    t = TenantFactory(slug="acme", name="Acme")
    admin = UserFactory(tenant=t, email="admin@acme.test", role="ADMIN")
    hrbp = UserFactory(tenant=t, email="hrbp@acme.test", role="HRBP")
    manager = UserFactory(tenant=t, email="manager@acme.test", role="MANAGER", manager=hrbp)
    report = UserFactory(tenant=t, email="report@acme.test", role="EMPLOYEE", manager=manager)
    peer = UserFactory(tenant=t, email="peer@acme.test", role="EMPLOYEE", manager=hrbp)  # → 5 users total
    from apps.billing.services import get_or_create_entitlement, set_seats

    with tenant_context(t):
        get_or_create_entitlement(t.id)
        set_seats(t, 100)
    return SimpleNamespace(
        tenant=t, admin=admin, hrbp=hrbp, manager=manager, report=report, peer=peer
    )


@pytest.fixture
def other_tenant(db):
    """A second, isolated tenant for cross-tenant isolation proofs."""
    return TenantFactory(slug="globex", name="Globex")
