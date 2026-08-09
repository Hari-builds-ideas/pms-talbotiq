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
from apps.testsupport.factories import CycleFactory, GoalFactory, ReviewFactory, UserFactory

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
def test_a_plan_headline_says_who_it_is_for(org):
    """The line a human reads before approving has to name the person.

    A request made with a pronoun came back as one: after "who are my two weakest?",
    "give them recognition for their effort" summarised as "…give recognition for their
    effort this quarter". Every step underneath named the right person; the headline —
    which is what the approver actually reads and decides on — did not.
    """
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        ReviewFactory(employee=org.report,
                      cycle=CycleFactory(tenant=org.tenant, status="ACTIVE"), state="DRAFT")
        session = _session(org.manager)
        out = build_plan(org.manager, session, "start a 360 for Rhea and draft her review")

        assert out["status"] == "planned"
        steps = list(out["plan"].steps.all())
        assert [s.action for s in steps] == ["initiate_360", "draft_review"]
        summary = out["plan"].summary

    assert "Rhea" in summary, f"the approver is not told who this is for: {summary!r}"


@override_settings(**FAKE)
def test_a_plan_headline_that_already_names_the_person_is_left_alone(org):
    """No belt-and-braces restatement: nobody gets told twice."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        session = _session(org.manager)
        plan = build_plan(org.manager, session,
                          "give recognition to Rhea Report for her work")["plan"]
        plan.summary = "Ready to recognise Rhea Report."
        # Re-run the naming over an already-explicit headline.
        from apps.ai.planner import _name_the_subjects, _subject_label

        realized = [("give_recognition", {"preview": [{"recipient": "Rhea Report"}]})]
        assert _subject_label(realized[0][1]) == "Rhea Report"
        out = _name_the_subjects(org.manager, plan.summary, realized)

    assert out == "Ready to recognise Rhea Report."


@override_settings(**FAKE)
def test_a_plan_about_the_callers_own_records_is_not_addressed_to_them(org):
    """"Start my check-in" does not want "(for Nikhil Vasquez)" bolted onto it."""
    from apps.ai.planner import _name_the_subjects

    _name(org.manager, "Nikhil Vasquez")
    realized = [("open_checkin", {"preview": [{"employee": "Nikhil Vasquez"}]})]

    assert _name_the_subjects(org.manager, "Ready to open your check-in.", realized) == (
        "Ready to open your check-in.")


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


# ── OVERNIGHT_F: multi-step plans hitting the NEW actions ───────────────────────


@override_settings(**FAKE)
def test_multi_step_plan_with_new_actions_checkin_then_goal(org):
    """"respond to the check-in for Rhea and approve the goal for Rhea" → two ordered
    confirm steps (respond_to_checkin, approve_goal); nothing runs on emit."""
    import datetime

    from apps.checkins.models import ManagerResponse
    from apps.checkins.services import upsert_checkin

    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        cyc = CycleFactory(tenant=org.tenant, status="ACTIVE")
        GoalFactory(employee=org.report, cycle=cyc, status="ACTIVE")  # pending (approved_by=None)
        upsert_checkin(org.report, week_of=datetime.date(2026, 6, 29), mood=3)
        session = _session(org.manager)
        out = build_plan(org.manager, session,
                         "respond to Rhea's check-in and approve Rhea's goal")
        assert out["status"] == "planned"
        steps = list(out["plan"].steps.all())
        assert [s.action for s in steps] == ["respond_to_checkin", "approve_goal"]
        assert all(s.feel == "confirm" and s.reason.strip() for s in steps)
        # INERT: no response posted, no goal approved on emit.
        assert ManagerResponse.objects.count() == 0
        assert AuditLog.objects.filter(action="goal.approved").count() == 0


@override_settings(**FAKE)
def test_multi_step_plan_mixes_navigate_and_confirm(org):
    """"schedule a review for Rhea and start a 360 for Rhea" → a NAVIGATE step
    (schedule_review) then a CONFIRM step (initiate_360); inert on emit."""
    with tenant_context(org.tenant):
        _name(org.report, "Rhea Report")
        CycleFactory(tenant=org.tenant, status="ACTIVE")
        session = _session(org.manager)
        out = build_plan(org.manager, session, "schedule a review for Rhea and start a 360 for Rhea")
        assert out["status"] == "planned"
        steps = list(out["plan"].steps.all())
        assert [s.action for s in steps] == ["schedule_review", "initiate_360"]
        assert steps[0].feel == "navigate" and steps[0].deeplink == "/reviews"
        assert steps[1].feel == "confirm"
        assert FeedbackCycle.objects.count() == 0  # inert


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


# ── FIX 3: pending-slot follow-up — a reply FILLS the slot, never restarts ────────


@override_settings(**FAKE)
def test_pending_recognition_slot_is_filled_by_the_next_message(org):
    """"recognise priya" is genuinely ambiguous (many Priyas) → a clarify step. The
    user's next message "Priya Nair" must COMPLETE the recognition — resume the same
    action — not start a new, unrelated plan."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        _name(org.hrbp, "Priya Nair")
        for surname in ("Silva", "Novak", "Khan"):
            UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name=f"Priya {surname}")
        session = _session(org.manager)

        # Turn 1: ambiguous → a clarify step that remembers the action to resume.
        out1 = build_plan(org.manager, session, "give recognition to priya")
        step1 = out1["plan"].steps.first()
        assert step1.feel == "clarify"
        assert step1.params.get("clarify_action") == "give_recognition"

        # Turn 2: the answer fills the slot → a give_recognition CONFIRM for Priya Nair,
        # NOT a fresh "draft a review" plan.
        out2 = build_plan(org.manager, session, "Priya Nair")
        step2 = out2["plan"].steps.first()
        assert step2.action == "give_recognition"
        assert step2.feel == "confirm"
        assert step2.params.get("recipient_user_id") == str(org.hrbp.id)


@override_settings(**FAKE)
def test_pending_slot_yields_to_a_genuine_new_command(org):
    """A pending clarify must not hijack a real new command: if the next message is
    itself an action ("approve my team's goals"), plan THAT, don't force-fill."""
    with tenant_context(org.tenant):
        _name(org.manager, "Ada Lovelace")
        for surname in ("Silva", "Novak"):
            UserFactory(tenant=org.tenant, role="EMPLOYEE", display_name=f"Priya {surname}")
        cyc = CycleFactory(tenant=org.tenant, status="ACTIVE")
        GoalFactory(employee=org.report, cycle=cyc, status="ACTIVE")
        session = _session(org.manager)

        build_plan(org.manager, session, "give recognition to priya")  # pending clarify
        out = build_plan(org.manager, session, "approve my team's goals")
        actions = [s.action for s in out["plan"].steps.all()]
        assert "approve_goals" in actions  # the new command won, not a recognition fill
