# Functional Test Matrix (web / back-end)

The COE brief's testing row requires verification of **review-cycle transitions,
automated notifications, KPI weightage = 100%, and approval escalations**, across
desktop and mobile-web. This matrix maps each required behaviour → the test(s) that
prove it → status, for the WEB/back-end side (the mobile-web surface is covered in the
mobile build). Every test below runs in the backend suite: **1193 passed, 2 deselected**.

Legend: **[test]** asserted by an automated test · **[live]** also exercised over real
HTTP / the real Celery task on the running stack.

---

## 1. Review-cycle state transitions

State machine: `apps/reviews/state_machine.py` (`TRANSITIONS` table is the single
source of truth; every transition function consults it). States: DRAFT, AI_DRAFTING,
PENDING_HUMAN_REVIEW, EDITING, APPROVED, REJECTED, FINALIZED.

| Transition (from → to) | Test | Status |
|---|---|---|
| DRAFT → EDITING → PENDING → APPROVED → FINALIZED (manual happy path) | `test_state_machine.py::test_manual_happy_path_reaches_finalized_with_no_ai` | [test] |
| DRAFT → AI_DRAFTING → PENDING (AI path + system lock) | `test_state_machine.py::test_request_ai_draft_and_system_lock` | [test] |
| PENDING → EDITING → PENDING (revise & resubmit) | `test_state_machine.py::test_pending_back_to_editing_and_resubmit` | [test] |
| PENDING → REJECTED → EDITING (reject then revise) | `test_state_machine.py::test_reject_then_revise` | [test] |
| **APPROVED → EDITING (route_rejected, Module-5 edge)** | `test_state_machine.py::test_route_rejected_returns_approved_review_to_editing` *(added W3)* | [test] |
| reject requires a non-empty reason (422) | `test_api.py::test_reject_requires_reason_then_rejects_then_revise` | [test] |
| Illegal: approve/reject/finalize/submit/ai_ready from DRAFT (409/422) | `test_state_machine.py::test_illegal_from_draft` | [test] |
| Illegal: re-approve an APPROVED review (409) | `test_state_machine.py::test_approve_twice_is_rejected` | [test] |
| Illegal: any transition out of FINALIZED (terminal) | `test_state_machine.py::test_finalized_is_terminal` | [test] |
| **Illegal: route_rejected unless APPROVED** | `test_state_machine.py::test_route_rejected_illegal_unless_approved` *(added W3)* | [test] |
| Every transition appends a timeline row | `test_state_machine.py::test_every_transition_appends_timeline_row` | [test] |
| End-to-end over HTTP (create → assess → edit → submit → approve → finalize) | `test_api.py::test_e2e_manual_hitl_flow` | [test] |

**HITL gate (no FINALIZED without a human reviewer) — 3 layers:**

| Behaviour | Test | Status |
|---|---|---|
| Finalize without approval → 422 (machine layer) | `test_hitl.py::test_finalize_without_approval_is_422_hitl` | [test] |
| Finalize checks reviewer set, not only state | `test_hitl.py::test_finalize_guard_checks_reviewer_not_only_state` | [test] |
| DB CHECK rejects FINALIZED + null reviewer (direct save / .update) | `test_hitl.py::test_db_check_rejects_finalized_with_null_reviewer_on_direct_save`, `…_on_queryset_update` | [test] |
| API returns 422 HITL_APPROVAL_REQUIRED before approval | `test_api.py::test_e2e_manual_hitl_flow` | [test] |

## 2. KPI weightage = 100.00 (exact-Decimal, no float tolerance)

Validators: `apps/goals/validators.py`; enforced in `apps/goals/serializers.py` (create)
and `apps/goals/views.py` (KPI add/delete/patch). Two invariants: a goal's KPIs sum to
100.00; an employee's ACTIVE goals sum to 100.00.

| Boundary case | Test | Status |
|---|---|---|
| Exactly 100.00 accepted (validator + various splits) | `test_weights.py::test_weights_summing_to_100_accepted` | [test] |
| 99.99 / 100.01 / other near-misses rejected (validator) | `test_weights.py::test_weights_not_summing_to_100_rejected` | [test] |
| Goal's KPIs = 99.99 rejected | `test_weights.py::test_goal_kpi_weights_9999_rejected` | [test] |
| Active goals = 100.01 rejected | `test_weights.py::test_active_goal_weights_10001_rejected` | [test] |
| Non-ACTIVE goals excluded from the sum | `test_weights.py::test_active_goal_weights_ignore_non_active` | [test] |
| API create: KPIs = 99.99 → 400 (lower boundary) | `test_api.py::test_kpi_weights_must_sum_to_exactly_100_lower_boundary` | [test] + [live] |
| API create: KPIs = 100.01 → 400 (upper boundary) | `test_api.py::test_kpi_weights_must_sum_to_exactly_100_upper_boundary` | [test] + [live] |
| API create: KPIs = exactly 100.00 → 201 | `test_api.py::test_kpi_weights_exactly_100_accepted` | [test] + [live] |
| API add KPI breaking 100 → 400, rolled back | `test_api.py::test_add_kpi_must_keep_goal_at_100` | [test] |
| API delete KPI breaking 100 → 400, rolled back | `test_api.py::test_delete_kpi_rolls_back_when_sum_breaks` | [test] |
| **API PATCH KPI weight breaking 100 → 400, rolled back** | `test_api.py::test_kpi_weight_patch_breaking_100_is_rejected` *(added W3)* | [test] |
| **API PATCH non-weight field → 200 (no spurious re-check)** | `test_api.py::test_kpi_non_weight_patch_does_not_trigger_weight_check` *(added W3)* | [test] |

**[live]** Against the running stack as a manager: `POST /api/goals/` with KPI weights
99.99 → **400** ("must sum to exactly 100.00 (got 99.99)"), 100.01 → **400**, 100.00 →
**201** (then cleaned up).

## 3. Approval escalations (sequential + parallel + timeout sweep)

Engine: `apps/approvals/engine.py` (`escalate_step`, `overdue_pending_steps`);
beat task: `apps/approvals/tasks.py::escalate_overdue_routes`.

| Behaviour | Test | Status |
|---|---|---|
| SEQUENTIAL: step 1 active, step 2 pending | `test_engine.py::test_sequential_resolution_and_active_step` | [test] |
| SEQUENTIAL: out-of-order decision rejected (409) | `test_engine.py::test_sequential_out_of_order_rejected` | [test] |
| SEQUENTIAL: full approval completes + fires handler | `test_engine.py::test_sequential_full_approval_completes_and_fires_handler` | [test] |
| SEQUENTIAL: a reject ends the route | `test_engine.py::test_sequential_reject_ends_route_and_fires_rejected` | [test] |
| PARALLEL: all required approve → completes | `test_engine.py::test_parallel_all_required_approve_completes` | [test] |
| PARALLEL: a required reject ends the route | `test_engine.py::test_parallel_required_reject_ends_route` | [test] |
| Timeout sweep: overdue step → reassigned to escalation target, audited, route stays open | `test_escalation.py::test_sweep_escalates_overdue_step_and_audits` | [test] + [live] |
| Sweep ignores not-yet-due / no-timeout / already-decided steps | `test_escalation.py::test_sweep_ignores_step_not_yet_due`, `…_ignores_step_with_no_timeout`, `…_skips_already_decided_step` | [test] |
| **PARALLEL: overdue step escalates independently of its active sibling** | `test_escalation.py::test_sweep_escalates_a_parallel_step_independently` *(added W3)* | [test] |
| Sweep is multi-tenant + off-request (no context leak) | `test_escalation.py::test_sweep_escalates_across_tenants_without_leaking_context` | [test] |
| Sweep summary shape on empty run | `test_escalation.py::test_summary_dict_shape_on_empty_sweep` | [test] |

**[live]** Seeded a real overdue SEQUENTIAL route on the running stack and ran the actual
`escalate_overdue_routes()` Celery task: summary `{scanned: 1, escalated: 1, errors: 0}`,
the step reassigned MANAGER → HRBP, route still IN_PROGRESS (then cleaned up).

## 4. Automated notifications (generation on key events)

Signal-driven (Django `Signal`, `send_robust`, best-effort): the engine/services fire
signals, `apps/integrations/receivers.py` subscribes and calls the Slack notifier
(`apps/integrations/notifications.py`), which is a clean no-op when Slack is unconfigured.

| Event → notification | Test | Status |
|---|---|---|
| Route start fires `approval_step_assigned` for the active step | `test_signals.py::test_start_route_fires_assignment_for_the_active_step` | [test] |
| Escalation fires `approval_step_escalated` | `test_signals.py::test_escalate_step_fires_escalation_signal` | [test] |
| **Route start → receiver invokes the assignment notifier (delivery generated)** | `test_signals.py::test_route_start_generates_an_assignment_notification` *(added W3)* | [test] + [live] |
| **Escalation → receiver invokes the escalation notifier** | `test_signals.py::test_escalation_generates_an_escalation_notification` *(added W3)* | [test] + [live] |
| **Feedback invitation → receiver invokes the feedback notifier** | `test_services.py::test_send_feedback_request_generates_a_notification` *(added W3)* | [test] |

**[live]** During the live escalation run, the integrations receiver invoked both the
assignment and escalation notifiers (logged as a Slack no-op — no enabled integration on
the demo tenant — proving the generation path runs and degrades gracefully).

> Note (honest): review state changes deliberately emit **no** Slack notification (the
> review timeline + audit log are the in-app record); only approval routing + feedback
> invitations push to the Module-12 Slack seam. Actual Slack delivery to a real workspace
> is the customer's integration to enable (a 🔑 infra/config item, not a code task).

---

## Gaps closed in W3
`route_rejected` (APPROVED→EDITING) + its illegal-from-non-APPROVED guard; PARALLEL-step
escalation; notification **delivery** (signal→receiver→notifier) for approval assignment,
escalation, and feedback invitations; KPI weight=100 enforcement on **PATCH** (edit), not
only create/add/delete. +8 tests; suite 1185 → **1193**.
