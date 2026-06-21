"""
Regression for BUG 2 — "Request AI Draft" was unreachable: the demo had no DRAFT
review in the primary demo manager's scope, and `_ensure` never RESETS state, so a
prior session that edited the seeded DRAFT (DRAFT -> EDITING) made the action
unreachable forever. seed_demo now guarantees an Ada-owned DRAFT review and resets
it on every run.
"""
import pytest
from django.core.management import call_command

from apps.identity.models import User
from apps.reviews import state_machine as sm
from apps.reviews.models import Review
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

pytestmark = pytest.mark.django_db


def _ada_draft_reviews(acme):
    ada = User.objects.get(email="ada@acme.test")
    report_ids = set(User.objects.filter(manager=ada).values_list("id", flat=True))
    return ada, Review.objects.filter(state="DRAFT", employee_id__in=report_ids)


def test_seed_demo_gives_demo_manager_a_reachable_ai_draft_review():
    call_command("seed_demo")
    acme = Tenant.objects.get(slug="acme")
    with tenant_context(acme):
        ada, drafts = _ada_draft_reviews(acme)
        assert drafts.exists(), "demo manager has no DRAFT review for Request-AI-Draft"
        # The action is genuinely reachable for her: request_ai_draft is legal from
        # DRAFT and the manager holds RUN_AI_REVIEW_DRAFT + scope over the report.
        review = drafts.first()
        sm.request_ai_draft(review, ada)
        review.refresh_from_db()
        assert review.state == "AI_DRAFTING"  # fired (Agent-1 then lands PENDING per HITL)


def test_seed_demo_resets_a_drifted_ai_draft_review_back_to_draft():
    call_command("seed_demo")
    acme = Tenant.objects.get(slug="acme")
    with tenant_context(acme):
        ada, drafts = _ada_draft_reviews(acme)
        review = drafts.first()
        sm.start_edit(review, ada)  # a tester edits it: DRAFT -> EDITING
        review.refresh_from_db()
        assert review.state == "EDITING"

    call_command("seed_demo")  # re-seed must restore it

    with tenant_context(acme):
        review.refresh_from_db()
        assert review.state == "DRAFT"  # reset — the action is reachable again
