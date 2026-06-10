"""
Matrix tests — assert ``role_has_capability`` matches the §2 table EXACTLY for
every (role, capability) pair, including that NOBODY holds
``bypass_tenant_isolation`` / ``alter_audit_log``.

The expected table below is written out independently of ``matrix.CAPABILITIES``
(it is the spec restated as data) so the test genuinely cross-checks the
implementation rather than tautologically re-deriving it.
"""
import pytest

from apps.rbac.matrix import (
    CAPABILITIES,
    Capability,
    Role,
    role_has_capability,
)

# The §2 matrix as an independent oracle: capability -> set of roles allowed.
EXPECTED = {
    Capability.VIEW_OWN: {Role.EMPLOYEE, Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.SUBMIT_SELF_EVAL: {Role.EMPLOYEE, Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.VIEW_TEAM_ANALYTICS: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.MANAGE_REPORTS_GOALS: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.RUN_AI_REVIEW_DRAFT: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.APPROVE_REVIEW: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.BU_ANALYTICS_CALIBRATION: {Role.HRBP, Role.ADMIN},
    Capability.SUCCESSION_BENCH_FULL: {Role.HRBP, Role.ADMIN},
    Capability.GENERATE_JD: {Role.HRBP, Role.ADMIN},
    Capability.MANAGE_JD_LIBRARY: {Role.HRBP, Role.ADMIN},
    Capability.MANAGE_TENANT: {Role.ADMIN},
    Capability.READ_PRIVATE_DATA: {Role.HRBP, Role.ADMIN},
    # Module 2 — Goals & KPI engine.
    Capability.VIEW_OWN_GOALS: {Role.EMPLOYEE, Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.UPDATE_OWN_ACTUALS: {Role.EMPLOYEE, Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.APPROVE_GOALS: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.VIEW_TEAM_SCORES: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.MANAGE_KPI_TEMPLATES: {Role.HRBP, Role.ADMIN},
    Capability.CONFIGURE_SCORING: {Role.ADMIN},
    Capability.MANAGE_CYCLES: {Role.HRBP, Role.ADMIN},
    # Module 3 — Reviews & Appraisal Cycles.
    Capability.MANAGE_REVIEWS: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.FINALIZE_REVIEW: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.VIEW_OWN_REVIEW: {Role.EMPLOYEE, Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.SUBMIT_SELF_ASSESSMENT: {Role.EMPLOYEE, Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.SUBMIT_ASSESSMENT: {Role.MANAGER, Role.HRBP, Role.ADMIN},
    Capability.CALIBRATE_REVIEWS: {Role.HRBP, Role.ADMIN},
    Capability.BYPASS_TENANT_ISOLATION: set(),
    Capability.ALTER_AUDIT_LOG: set(),
}

ALL_ROLES = sorted(Role.ALL)


def test_expected_table_covers_every_capability():
    """Guard the oracle: if a capability is added to the matrix, this test forces
    the expectation table to be updated too (no silent gaps)."""
    assert set(EXPECTED) == set(CAPABILITIES)


@pytest.mark.parametrize("capability", sorted(EXPECTED))
@pytest.mark.parametrize("role", ALL_ROLES)
def test_role_capability_matches_matrix(role, capability):
    expected = role in EXPECTED[capability]
    assert role_has_capability(role, capability) is expected


@pytest.mark.parametrize("role", ALL_ROLES)
def test_nobody_can_bypass_tenant_isolation(role):
    assert role_has_capability(role, Capability.BYPASS_TENANT_ISOLATION) is False


@pytest.mark.parametrize("role", ALL_ROLES)
def test_nobody_can_alter_audit_log(role):
    assert role_has_capability(role, Capability.ALTER_AUDIT_LOG) is False


def test_unknown_capability_fails_closed():
    assert role_has_capability(Role.ADMIN, "no_such_capability") is False


def test_unknown_role_fails_closed():
    assert role_has_capability("WIZARD", Capability.VIEW_OWN) is False


def test_none_role_fails_closed():
    assert role_has_capability(None, Capability.VIEW_OWN) is False


def test_matrix_values_are_frozensets():
    """Capability -> roles mapping must be immutable so it can't be mutated at
    runtime to widen access."""
    assert all(isinstance(v, frozenset) for v in CAPABILITIES.values())
