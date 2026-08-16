"""
PII scrubbing (B5).

The scrubber redacted only email addresses, and its own docstring said to extend
it "when profiles gain names" — which they had. These tests pin what is redacted,
what deliberately is not, and the false positives the patterns must avoid: a
scrubber that eats KPI values or years silently destroys the grounding the agents
reason from, which is worse than one that redacts too little.
"""
import pytest
from django.test import override_settings

from apps.ai.pii import contains_pii, scrub, scrub_text
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


# ── email ─────────────────────────────────────────────────────────────────────

def test_email_is_redacted_anywhere_in_a_string():
    out = scrub_text("Contact ada@acme.test about the goal.")
    assert "ada@acme.test" not in out
    assert "[REDACTED-EMAIL]" in out


def test_email_is_redacted_at_any_nesting_depth():
    payload = {"a": ["x", {"b": "reza@acme.test"}], "c": ("dan@acme.test",)}
    out = scrub(payload)
    flat = repr(out)
    assert "acme.test" not in flat
    assert flat.count("[REDACTED-EMAIL]") == 2


# ── phone ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text",
    [
        "call me on +44 20 7946 0958",
        "mobile: 555-0134-8890",
        "phone (020) 7946 0958",
        "+91 98765 43210",
        "reach me at 9876543210",
    ],
)
def test_phone_shapes_are_redacted(text):
    assert "[REDACTED-PHONE]" in scrub_text(text)


@pytest.mark.parametrize(
    "text",
    [
        # The false positives that matter — all of these are real prompt content.
        "target 2026 vs actual 2025",
        "attainment 87.5% against a target of 120",
        "cohort size 42, T-score 61.3",
        "closed 15 of 20 goals",
        "review cycle Q3 2026",
    ],
)
def test_ordinary_numbers_are_not_mistaken_for_phone_numbers(text):
    # A scrubber that eats KPI values destroys the grounding the agent needs.
    assert "[REDACTED-PHONE]" not in scrub_text(text)


def test_a_number_longer_than_e164_is_left_alone():
    # 20 digits is not a phone number; more likely an id or a hash fragment.
    assert "[REDACTED-PHONE]" not in scrub_text("ref 12345678901234567890")


# ── employee id ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text",
    [
        "employee id: A-1234",
        "Employee ID EMP99812",
        "emp no 4471",
        "staff number: X/889",
        "payroll id = 7781",
        "personnel #: QQ-12",
    ],
)
def test_labelled_employee_ids_are_redacted(text):
    out = scrub_text(text)
    assert "[REDACTED-EMPLOYEE-ID]" in out


def test_the_label_survives_so_the_model_knows_an_id_was_there():
    out = scrub_text("employee id: A-1234")
    assert "employee" in out.lower()
    assert "A-1234" not in out


def test_a_bare_token_is_not_treated_as_an_employee_id():
    # Without a label an alphanumeric token is indistinguishable from a goal
    # title, a KPI unit or a cycle name — redacting those would gut the prompt.
    text = "Goal OKR-2026-Q3 improve NPS by 12"
    assert "[REDACTED-EMPLOYEE-ID]" not in scrub_text(text)


# ── names: OFF by default ─────────────────────────────────────────────────────

def test_names_are_not_redacted_by_default():
    """evidence.py puts the subject's first name in the prompt on purpose."""
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        UserFactory(tenant=t, email="p@acme.test", display_name="Priya Nair", role="EMPLOYEE")
        out = scrub("Write a review for Priya Nair.", tenant=t)
    assert "Priya Nair" in out


@override_settings(PII_SCRUB_NAMES=True)
def test_names_become_role_tokens_when_the_setting_is_on():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        UserFactory(tenant=t, email="p@acme.test", display_name="Priya Nair", role="EMPLOYEE")
        UserFactory(tenant=t, email="m@acme.test", display_name="Dan Ops", role="MANAGER")
        out = scrub("Priya Nair reports to Dan Ops.", tenant=t)
    assert "Priya" not in out
    assert "Dan" not in out
    assert "[EMPLOYEE]" in out
    assert "[MANAGER]" in out


@override_settings(PII_SCRUB_NAMES=True)
def test_first_names_alone_are_also_replaced():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        UserFactory(tenant=t, email="p@acme.test", display_name="Priya Nair", role="EMPLOYEE")
        out = scrub("Priya missed two goals.", tenant=t)
    assert "Priya" not in out
    assert "[EMPLOYEE]" in out


@override_settings(PII_SCRUB_NAMES=True)
def test_a_longer_name_wins_over_one_of_its_parts():
    t = TenantFactory(slug="acme")
    with tenant_context(t.id):
        UserFactory(tenant=t, email="a@acme.test", display_name="Ana Maria", role="HRBP")
        out = scrub("Ana Maria approved it.", tenant=t)
    # Substituting "Ana" first would leave a stray "Maria" behind.
    assert "Maria" not in out
    assert "[HRBP]" in out


@override_settings(PII_SCRUB_NAMES=True)
def test_names_are_left_alone_without_a_tenant_rather_than_silently_skipped():
    # Nothing to look names up against. The scrubber logs a warning; the
    # assertion here is simply that it does not crash and still redacts what it
    # can without a tenant.
    out = scrub("Priya Nair on ada@acme.test")
    assert "[REDACTED-EMAIL]" in out


# ── the breach check ──────────────────────────────────────────────────────────

def test_contains_pii_flags_contact_details():
    assert contains_pii("reach ada@acme.test") is True
    assert contains_pii("call +44 20 7946 0958") is True


def test_contains_pii_ignores_names_and_ordinary_numbers():
    # A name is not a breach for an agent whose output is ABOUT that person; a
    # contact detail always is.
    assert contains_pii("Priya Nair scored 61.3 in a cohort of 42") is False
