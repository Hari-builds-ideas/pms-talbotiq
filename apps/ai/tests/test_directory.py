"""
Directory resolution (apps.ai.directory) — the name→person lookup that powers agent
actions, kept DELIBERATELY separate from data access.

The contract under test:
  * DIRECTORY resolution ranges over the WHOLE tenant for recognition, so a manager
    can recognise a colleague OUTSIDE their team (the "Priya Nair, an HRBP" bug).
  * An EXACT full-name match wins outright and NEVER disambiguates, even when many
    people share the first name (7 "Priya *" must not drown out "Priya Nair").
  * Resolving a name grants NO data access — a manager can name an out-of-team person
    for recognition, yet still cannot resolve them for a performance-DATA action.
  * It scales: the lookup is DB-backed + capped, never loading the whole table.
"""
import pytest

from apps.ai import actions
from apps.ai.directory import AMBIGUOUS, resolve_person_in_population
from apps.recognition.models import Recognition
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import UserFactory

pytestmark = pytest.mark.django_db


def _name(user, display):
    user.display_name = display
    user.save(update_fields=["display_name"])
    return user


def test_recognition_resolves_a_person_outside_the_managers_team(org):
    """The reported bug: a MANAGER recognising an HRBP (outside their reporting line)
    must resolve — recognition is tenant-wide, not team-scoped."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        _name(org.hrbp, "Priya Nair")  # HRBP — NOT in the manager's reporting subtree
        recipient = actions._resolve_recipient_in_tenant(
            org.manager, "give recognition to priya nair for her excellent team work"
        )
        assert recipient is not None and recipient is not AMBIGUOUS
        assert recipient.id == org.hrbp.id


def test_exact_full_name_never_disambiguates_amid_shared_first_names(org):
    """Seven people named "Priya *" — the exact "Priya Nair" must win, not ASK."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        target = _name(org.hrbp, "Priya Nair")
        for surname in ("Silva", "Novak", "Khan", "Lindqvist", "Mbeki", "Costa"):
            UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name=f"Priya {surname}")
        # Exact full name → resolves to the one Priya Nair, no AMBIGUOUS.
        recipient = actions._resolve_recipient_in_tenant(org.manager, "recognise priya nair")
        assert recipient is not None and recipient is not AMBIGUOUS
        assert recipient.id == target.id
        # But a BARE first name that 7 people share is genuinely ambiguous → ASK.
        assert actions._resolve_recipient_in_tenant(org.manager, "recognise priya") is AMBIGUOUS


def test_two_real_people_same_exact_name_ask(org):
    """Two genuine "Priya Nair" → the only honest answer is to ASK (list them)."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        _name(org.hrbp, "Priya Nair")
        UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name="Priya Nair")
        assert actions._resolve_recipient_in_tenant(org.manager, "recognise priya nair") is AMBIGUOUS


def test_typo_in_a_name_still_resolves_by_fuzzy(org):
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        target = _name(org.report, "Akhil Menon")
        recipient = actions._resolve_recipient_in_tenant(org.manager, "give kudos to akil menonn")
        assert recipient is not None and recipient is not AMBIGUOUS
        assert recipient.id == target.id


def test_directory_resolution_does_not_grant_data_access(org):
    """Naming an out-of-team person for RECOGNITION resolves them (directory), but the
    SAME person is unresolvable for a data/write action (scope) — resolution ≠ access."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        _name(org.peer, "Priya Nair")  # employee under HRBP — outside manager's team

        # Directory (tenant-wide): resolves the out-of-team colleague.
        assert actions._resolve_recipient_in_tenant(org.manager, "recognise priya nair").id == org.peer.id
        # Data scope (visible-only): the SAME name does NOT resolve for the manager —
        # they can't see this person's performance data, and resolution mustn't leak it.
        assert actions._resolve_person(org.manager, "how is priya nair doing") is None


def test_recognition_to_out_of_team_person_executes_and_posts(org):
    """End to end: propose → execute give_recognition for an out-of-team recipient
    actually posts a Recognition (the recipient is not dropped)."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        _name(org.hrbp, "Priya Nair")
        proposal = actions._propose_give_recognition(
            org.manager, "give recognition to priya nair for teamwork"
        )
        assert proposal["action"] == "give_recognition"
        assert proposal["params"]["recipient_user_id"] == str(org.hrbp.id)
        out = actions.execute_action(org.manager, "give_recognition", proposal["params"])
        assert out["ok"] is True
        assert Recognition.objects.filter(recipient=org.hrbp, sender=org.manager).count() == 1


def test_population_restriction_scopes_directory_lookup(org):
    """The population argument is what separates tenant-wide from scoped: the same
    name resolves against the whole tenant but NOT against a restricted id set."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        _name(org.peer, "Priya Nair")
        # whole tenant → found
        assert resolve_person_in_population(org.manager, "priya nair", population_ids=None).id == org.peer.id
        # restricted population that excludes the peer → not found
        assert resolve_person_in_population(
            org.manager, "priya nair", population_ids={org.manager.id, org.report.id}
        ) is None
