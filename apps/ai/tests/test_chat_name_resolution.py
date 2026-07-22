"""
Chat name resolution — a query that names a SPECIFIC person by full name
("how is Leon Petrova doing?") must resolve to that exact person, even when many
others share a first or last name. A single ambiguous token stays ambiguous.
Regression for the tester-reported bug where "leon petrova" returned the whole
"Leon */* Petrova" family as a disambiguation list (with the exact match buried).
"""
import pytest

from apps.ai.agents.chat import _resolve_named_person
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def peopled_tenant():
    t = TenantFactory(slug="acme")
    caller = UserFactory(tenant=t, email="mgr@acme.test", role="MANAGER", display_name="Mia Manager")
    targets = {}
    for email, name in [
        ("lp@acme.test", "Leon Petrova"), ("ln@acme.test", "Leon Nair"),
        ("ls@acme.test", "Leon Sharma"), ("lw@acme.test", "Leon Walsh"),
        ("ap@acme.test", "Aisha Petrova"), ("dp@acme.test", "Diego Petrova"),
        ("np@acme.test", "Nora Petrova"),
        ("ni@acme.test", "Nadia Ivanov"), ("nc@acme.test", "Nadia Cohen"),
        ("ai@acme.test", "Arjun Ivanov"),
    ]:
        targets[name] = UserFactory(tenant=t, email=email, role="EMPLOYEE", display_name=name)
    return t, caller, targets


def test_full_name_resolves_to_exact_person(peopled_tenant):
    t, caller, targets = peopled_tenant
    with tenant_context(t):
        named, ambiguous = _resolve_named_person(caller, "how is leon petrova doing this cycle?")
        assert ambiguous == []
        assert named is not None and named.id == targets["Leon Petrova"].id

        named2, amb2 = _resolve_named_person(caller, "ok what about nadia ivanov")
        assert amb2 == []
        assert named2 is not None and named2.id == targets["Nadia Ivanov"].id


def test_single_token_stays_ambiguous(peopled_tenant):
    t, caller, _ = peopled_tenant
    with tenant_context(t):
        named, ambiguous = _resolve_named_person(caller, "how is leon doing")
        assert named is None
        assert len(ambiguous) >= 2  # Leon Petrova/Nair/Sharma/Walsh — genuinely ambiguous


def test_two_people_same_full_name_stays_ambiguous(peopled_tenant):
    t, caller, _ = peopled_tenant
    # A genuine full-name clash must NOT auto-pick one.
    UserFactory(tenant=t, email="lp2@acme.test", role="EMPLOYEE", display_name="Leon Petrova")
    with tenant_context(t):
        named, ambiguous = _resolve_named_person(caller, "how is leon petrova doing")
        assert named is None
        assert any("Leon Petrova" in a for a in ambiguous)
