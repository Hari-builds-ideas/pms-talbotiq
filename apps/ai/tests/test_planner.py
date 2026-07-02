"""
The agent PLANNER (OVERNIGHT_A2/A3) — plan → per-step approve, WITHOUT weakening a
single invariant. The proofs:
  * a multi-step request yields an ORDERED, INERT plan (nothing executes on emit);
  * every emitted step carries a grounded reason (composed from real fetched facts);
  * approving ONE step runs ONLY that step, through the SAME audited gate, once
    (idempotent), re-checking capability + scope (out-of-scope / forbidden → refused);
  * approving out of order is allowed but flagged; earlier steps never auto-run;
  * a plan is owner-bound (another user can't approve it → 403);
  * ambiguity becomes a clarify step (never a guess);
  * capability the caller lacks → the step is silently dropped (defense in depth).
All planner outputs use the deterministic FakeLLMProvider — no live calls here.
"""
import pytest
from django.test import override_settings
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.ai.models import AIJob, ChatPlanStep, ChatSession
from apps.ai.planner import approve_step, build_plan
from apps.audit.models import AuditLog
from apps.feedback.models import FeedbackCycle
from apps.tenancy.context import tenant_context
from apps.testsupport.factories import CycleFactory, ReviewFactory, UserFactory

pytestmark = pytest.mark.django_db
FAKE = {"LLM_PROVIDER": "apps.ai.providers.FakeLLMProvider"}


def _session(user):
    return ChatSession.objects.create(tenant_id=user.tenant_id, owner=user)


def _name(user, name):
    user.display_name = name
    user.save(update_fields=["display_name"])


@override_settings(**FAKE)
def test_multi_step_plan_is_ordered_inert_and_grounded(org):
    """"start a 360 for Rhea and draft her review" → two ordered confirm steps for
    the same person; NOTHING runs on emit; each step has a grounded reason."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        ReviewFactory(employee=org.report, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT")
        session = _session(org.manager)
        out = build_plan(org.manager, session, "start a 360 for Rhea and draft her review")
        assert out["status"] == "planned"
        steps = list(out["plan"].steps.all())
        assert [s.action for s in steps] == ["initiate_360", "draft_review"]
        assert all(s.feel == "confirm" for s in steps)
        assert all(s.reason.strip() for s in steps)  # grounded reason per step
        assert "Rhea" in steps[0].reason
        # INERT: emitting the plan created/enqueued nothing.
        assert FeedbackCycle.objects.count() == 0
        assert AIJob.objects.count() == 0


@override_settings(**FAKE)
def test_approve_one_step_executes_that_step_only_and_is_idempotent(org):
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        ReviewFactory(employee=org.report, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT")
        session = _session(org.manager)
        plan = build_plan(org.manager, session, "start a 360 for Rhea and draft her review")["plan"]
        step0, step1 = list(plan.steps.all())

        r = approve_step(org.manager, plan.id, step0.id)  # the 360 step
        assert r["status"] == "done" and r["out_of_order"] is False
        assert FeedbackCycle.objects.filter(subject=org.report, status="DRAFT").count() == 1
        assert AIJob.objects.count() == 0  # the OTHER step did not run
        # Idempotent: re-approving the same step doesn't create a second cycle.
        again = approve_step(org.manager, plan.id, step0.id)
        assert again["idempotent"] is True
        assert FeedbackCycle.objects.filter(subject=org.report).count() == 1

        r1 = approve_step(org.manager, plan.id, step1.id)  # now the review draft
        assert r1["status"] == "done"
        assert AIJob.objects.filter(agent_code="agent1").count() == 1


@override_settings(**FAKE)
def test_out_of_order_approval_is_flagged_and_never_autoruns_earlier(org):
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        ReviewFactory(employee=org.report, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT")
        session = _session(org.manager)
        plan = build_plan(org.manager, session, "start a 360 for Rhea and draft her review")["plan"]
        step0, step1 = list(plan.steps.all())

        r = approve_step(org.manager, plan.id, step1.id)  # approve step 2 first
        assert r["status"] == "done" and r["out_of_order"] is True
        # Step 1 (the 360) was NOT auto-run.
        assert FeedbackCycle.objects.count() == 0
        step0.refresh_from_db()
        assert step0.status == ChatPlanStep.Status.PENDING


@override_settings(**FAKE)
def test_capability_gate_drops_steps_and_never_leaks(org):
    """An employee lacks MANAGE_FEEDBACK_CYCLE + RUN_AI_REVIEW_DRAFT → both steps are
    dropped; the plan has no steps and the summary explains generically."""
    with tenant_context(org.tenant):
        session = _session(org.report)
        plan = build_plan(org.report, session, "start a 360 for someone and draft their review")["plan"]
        assert plan.steps.count() == 0
        assert plan.summary.strip()  # a generic explanation, not an error


@override_settings(**FAKE)
def test_approve_out_of_scope_target_is_refused_on_the_plan_path(org):
    """The plan path is not a bypass: approving a step whose target is out of scope
    raises through the SAME execute gate (here a peer's review under HRBP)."""
    with tenant_context(org.tenant):
        peer_review = ReviewFactory(
            employee=org.peer, cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT"
        )
        session = _session(org.manager)
        plan = build_plan(org.manager, session, "draft a review")["plan"]  # may be clarify/navigate
        # Hand-craft a step pointing at the peer's review to prove the execute gate holds.
        step = ChatPlanStep.objects.create(
            tenant_id=org.tenant.id, plan=plan, ordinal=99, action="draft_review",
            feel="confirm", params={"review_id": str(peer_review.id)},
        )
        with pytest.raises(PermissionDenied):
            approve_step(org.manager, plan.id, step.id)
        step.refresh_from_db()
        assert step.status == ChatPlanStep.Status.FAILED
        assert AIJob.objects.count() == 0


@override_settings(**FAKE)
def test_plan_is_owner_bound_other_user_cannot_approve(org):
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        session = _session(org.manager)
        plan = build_plan(org.manager, session, "start a 360 for Rhea")["plan"]
        step = plan.steps.first()
        with pytest.raises(PermissionDenied):  # a different user's plan → 403
            approve_step(org.report, plan.id, step.id)


@override_settings(**FAKE)
def test_ambiguous_request_becomes_a_clarify_step(org):
    """Two eligible DRAFT reviews under the manager + no name → a clarify step, not a
    guess. Approving a clarify surfaces the question and stays pending."""
    with tenant_context(org.tenant):
        r2 = UserFactory(tenant=org.tenant, role="EMPLOYEE", email="r2@acme.test", manager=org.manager)
        cyc = CycleFactory(tenant=org.tenant, status="ACTIVE")
        ReviewFactory(employee=org.report, cycle=cyc, state="DRAFT")
        ReviewFactory(employee=r2, cycle=cyc, state="DRAFT")
        session = _session(org.manager)
        plan = build_plan(org.manager, session, "draft a review")["plan"]
        step = plan.steps.first()
        assert step.feel == "clarify"
        res = approve_step(org.manager, plan.id, step.id)
        assert res["status"] == "needs_clarification"
        step.refresh_from_db()
        assert step.status == ChatPlanStep.Status.PENDING


@override_settings(**FAKE)
def test_unknown_action_from_planner_is_dropped(org):
    """Defense in depth: if the planner emitted an action not in the registry it is
    dropped (the fake never does, so we assert only registry actions survive)."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        session = _session(org.manager)
        plan = build_plan(org.manager, session, "give recognition to Rhea")["plan"]
        from apps.ai.actions import ACTIONS

        for s in plan.steps.all():
            assert s.action in ACTIONS or s.action == "clarify"
