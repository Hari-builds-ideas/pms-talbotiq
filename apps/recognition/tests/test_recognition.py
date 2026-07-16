"""
RW_BUILD_2 2.1 — Recognition: the visibility matrix is the LOAD-BEARING security
test (a card must reach exactly its permitted audience and NOBODY else), plus
tenant isolation, create rules, reactions, and the sender-only delete.

Relationships under tenant ``t`` (manager self-FK):
    m1 ──► a (recipient), b (a's peer)
    m2 ──► s (sender),    x (s's peer)
    u  (unrelated employee), admin (ADMIN, unrelated by tree)
A recognition is always s ──► a.
"""
import pytest

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.recognition.models import Recognition, RecognitionReaction
from apps.recognition.services import (
    create_recognition,
    delete_recognition,
    recognition_analytics,
    recognition_feed,
    toggle_reaction,
)
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import TenantFactory, UserFactory

pytestmark = pytest.mark.django_db

V = Recognition.Visibility


@pytest.fixture
def world(db):
    """The relationship graph above, returned as a namespace + a per-level card map."""
    from types import SimpleNamespace

    t = TenantFactory(slug="acme", name="Acme")
    with tenant_context(t):
        m1 = UserFactory(tenant=t, role="MANAGER", email="m1@acme.test")
        m2 = UserFactory(tenant=t, role="MANAGER", email="m2@acme.test")
        a = UserFactory(tenant=t, role="EMPLOYEE", email="a@acme.test", manager=m1)
        b = UserFactory(tenant=t, role="EMPLOYEE", email="b@acme.test", manager=m1)
        s = UserFactory(tenant=t, role="EMPLOYEE", email="s@acme.test", manager=m2)
        x = UserFactory(tenant=t, role="EMPLOYEE", email="x@acme.test", manager=m2)
        u = UserFactory(tenant=t, role="EMPLOYEE", email="u@acme.test")
        admin = UserFactory(tenant=t, role="ADMIN", email="admin@acme.test")
        cards = {
            level: create_recognition(
                s, recipient_id=a.id, value="Teamwork", message=f"{level} kudos", visibility=level
            )
            for level in [V.PRIVATE, V.MANAGER_ONLY, V.TEAM, V.COMPANY]
        }
    return SimpleNamespace(t=t, m1=m1, m2=m2, a=a, b=b, s=s, x=x, u=u, admin=admin, cards=cards)


def test_visibility_matrix(world):
    """Each level reaches exactly its permitted audience — and no one else.
    PRIVATE is private even from Admin (the key privacy property)."""
    w = world
    # (viewer, {levels they MUST see})
    expected = {
        "s (sender)": (w.s, {V.PRIVATE, V.MANAGER_ONLY, V.TEAM, V.COMPANY}),
        "a (recipient)": (w.a, {V.PRIVATE, V.MANAGER_ONLY, V.TEAM, V.COMPANY}),
        "m1 (recipient mgr)": (w.m1, {V.MANAGER_ONLY, V.TEAM, V.COMPANY}),
        "m2 (sender mgr)": (w.m2, {V.TEAM, V.COMPANY}),
        "b (recipient peer)": (w.b, {V.TEAM, V.COMPANY}),
        "x (sender peer)": (w.x, {V.TEAM, V.COMPANY}),
        "u (unrelated)": (w.u, {V.COMPANY}),
        "admin (unrelated)": (w.admin, {V.COMPANY}),
    }
    id_to_level = {card.id: level for level, card in w.cards.items()}
    for who, (viewer, must_see) in expected.items():
        with tenant_context(w.t):
            seen = {id_to_level[r.id] for r in recognition_feed(viewer) if r.id in id_to_level}
        assert seen == must_see, f"{who}: saw {seen}, expected {must_see}"


def test_no_self_recognition(world):
    with tenant_context(world.t):
        with pytest.raises(ValidationError):
            create_recognition(world.a, recipient_id=world.a.id, value="Teamwork", message="me", visibility=V.TEAM)


def test_unknown_value_rejected(world):
    with tenant_context(world.t):
        with pytest.raises(ValidationError):
            create_recognition(world.s, recipient_id=world.a.id, value="NotAValue", message="x", visibility=V.TEAM)


def test_blank_message_rejected(world):
    with tenant_context(world.t):
        with pytest.raises(ValidationError):
            create_recognition(world.s, recipient_id=world.a.id, value="Teamwork", message="  ", visibility=V.TEAM)


def test_oversized_message_rejected(world):
    # QA-NIGHT: TextField(max_length=1000) is not DB-enforced — the service must cap it.
    with tenant_context(world.t):
        with pytest.raises(ValidationError):
            create_recognition(world.s, recipient_id=world.a.id, value="Teamwork", message="x" * 1001, visibility=V.TEAM)


def test_cross_tenant_recipient_impossible(world):
    other = TenantFactory(slug="globex", name="Globex")
    with tenant_context(other):
        outsider = UserFactory(tenant=other, role="EMPLOYEE", email="out@globex.test")
    with tenant_context(world.t):
        with pytest.raises(NotFound):  # recipient invisible across tenants
            create_recognition(world.s, recipient_id=outsider.id, value="Teamwork", message="hi", visibility=V.COMPANY)


def test_cross_tenant_feed_no_leak(world):
    """A COMPANY card in tenant A must never appear in tenant B's feed."""
    other = TenantFactory(slug="globex", name="Globex")
    with tenant_context(other):
        bystander = UserFactory(tenant=other, role="ADMIN", email="admin@globex.test")
        leaked = {r.id for r in recognition_feed(bystander)}
    assert leaked == set()  # none of acme's cards (incl. the COMPANY one) leak


def test_reaction_toggle_and_unseen_card_404(world):
    company = world.cards[V.COMPANY]
    private = world.cards[V.PRIVATE]
    with tenant_context(world.t):
        # u can see the COMPANY card → toggle on, then off.
        assert toggle_reaction(world.u, company.id, "👍")["reacted"] is True
        assert RecognitionReaction.objects.filter(recognition=company, user=world.u).count() == 1
        assert toggle_reaction(world.u, company.id, "👍")["reacted"] is False
        assert RecognitionReaction.objects.filter(recognition=company, user=world.u).count() == 0
        # u CANNOT see the PRIVATE card → reacting is a 404 (never reveal it exists).
        with pytest.raises(NotFound):
            toggle_reaction(world.u, private.id, "👍")
        # unsupported emoji rejected.
        with pytest.raises(ValidationError):
            toggle_reaction(world.a, company.id, "🦄")


def test_sender_only_delete(world):
    card = world.cards[V.TEAM]
    with tenant_context(world.t):
        with pytest.raises(PermissionDenied):  # recipient is not the sender
            delete_recognition(world.a, card.id)
        delete_recognition(world.s, card.id)  # sender may
        # Soft-deleted → gone from the default manager (and feeds).
        assert Recognition.objects.filter(id=card.id).first() is None
        assert card.id not in {r.id for r in recognition_feed(world.s)}


def test_analytics_aggregate_is_tenant_scoped(world):
    with tenant_context(world.t):
        stats = recognition_analytics(world.m1)
    assert stats["total"] == 4  # the 4 seeded cards (all s→a)
    assert stats["top_values"][0] == {"value": "Teamwork", "count": 4}
    assert stats["by_visibility"][V.COMPANY] == 1
    # m1 neither sent nor received any of the s→a cards.
    assert stats["you"] == {"given": 0, "received": 0}
