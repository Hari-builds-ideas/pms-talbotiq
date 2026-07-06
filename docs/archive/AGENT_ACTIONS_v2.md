# AGENT_ACTIONS_v2 — the agent's action catalogue (File F)

The chat agent proposes an action; **nothing happens until the human approves** (a
Confirm tap → `execute_action`, the only write path) or opens a deep-linked screen
(Navigate) and completes it there. Every write re-checks capability + data scope on
the real targets and calls the **same audited service a human uses** — the agent can
never do what the caller couldn't do via the normal endpoint. Params resolve
deterministically in Python; text inside a field/param is **data, never a command**.

Enumerated live at **`GET /api/ai/actions/schema`** → `{actions: [{name, label,
description, feel, capability, allowed}]}` (sensitive actions the caller can't perform
are omitted — no existence leak).

## New in File F (5 shipped)

| Action | Who | Feel | Reuses (audited path) | Demo phrase |
|---|---|---|---|---|
| `open_checkin` | Employee+ | confirm | `checkins.upsert_checkin` (OWN) | "start my check-in, mood 4" |
| `respond_to_checkin` | Manager+ | confirm | `checkins.respond_to_checkin` (subtree) | "respond to Rhea's check-in" |
| `approve_goal` | Manager+ | confirm | goal approve path (one goal) | "approve Rhea's goal from my inbox" |
| `schedule_review` | Manager+ | navigate | deep-link `/reviews` + prefill | "schedule a review for Rhea" |
| `update_kpi_actual` | Owner | confirm | `goals.record_actual` (OWN) + warn | "update my Uptime KPI to 99" |

### `open_checkin`
Starts **this week's** check-in for the caller with a stated mood (1–5). Mood is real
data the caller gives — no mood → the chat **asks** (never invents one). **Non-destructive:**
if this week's check-in already exists it downgrades to *navigate* (won't clobber the
existing check-in / its priorities). Audits `checkin.opened`.

### `respond_to_checkin`
Posts a manager response to a **direct report's** check-in (resolved by name within
the caller's reporting subtree; out-of-scope / own → 404 / 403 in the service). The
comment is a clean default the human approves; stored verbatim as data. Audits
`checkin.responded`.

### `approve_goal`
The **singular** sibling of `approve_goals`: resolves ONE named report's pending goal
and approves just that one, through the same audited approve path + execute-time scope
re-check. Routing: "goals" (plural) → bulk `approve_goals`; "goal" (singular) → this.

### `schedule_review`
**Navigate-and-prefill** (no chat write): deep-links `/reviews` with the employee +
current cycle prefilled; the human creates + starts the review there via the audited
review endpoints. (The app hosts review creation on the Reviews list — there is no
separate `/reviews/new` route — so the deeplink is `/reviews`.)

### `update_kpi_actual`
A stricter sibling of `record_actual`: it **warns** when the value contradicts the
KPI's `direction` (e.g. lowering a higher-is-better KPI) or is a **>50% jump** from the
last recorded value — but still just **records** (no analysis writes). **OWN-only**,
exactly like `record_actual`/`KpiActualsView`; it does **not** widen scope to a
report's KPI (the spec's "Owner/Manager+" is honored as Owner-only to avoid widening
permissions — iron rule #1).

## Tests
- `apps/ai/tests/test_actions.py` — 4+ invariant tests per action (inert proposal;
  out-of-scope/wrong-cap refused at execute; writes+audits once; embedded instruction
  is data), cross-tenant on `respond_to_checkin` + `approve_goal`, the suspicious-value
  warning, and the schema endpoint (incl. sensitive-hiding). 26 new tests.
- `apps/ai/tests/test_planner.py` — 2 multi-step plans over the new actions.
- `apps/ai/tests/test_planner_live.py` — 1 live `gpt-4o-mini` plan over new actions
  (`live_ai`, deselected by default; verified once).
- Full backend suite: **1406 passed, 7 deselected**.

## Deferred (2 flagged — see the per-action files)
- **`request_feedback`** — no Employee-scoped feedback-request write exists (cycle
  invitations are Manager+); wiring it as Employee+ would widen permissions. See
  `HARI_ATTENTION_NEEDED_action_request_feedback.md`.
- **`nudge_stale_goal`** — stale goals are read-only advisory; no audited per-goal
  nudge-send endpoint exists to reuse. See
  `HARI_ATTENTION_NEEDED_action_nudge_stale_goal.md`.

Both need a small new backend feature to wire safely; neither was faked. That's why
File F shipped **5 of 7** actions (suite 1406, just under the 1408 target) — a
principled trade, not a shortfall.
