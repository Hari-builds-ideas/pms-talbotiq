# HARI_ATTENTION_NEEDED — agent action `nudge_stale_goal` (File F)

**Status:** NOT shipped this run — deliberately. There is **no audited write endpoint**
a human uses to "nudge a stale goal," so it can't be wired without inventing an
unaudited write path (iron rule #1: every agent write calls the SAME audited endpoint
a human uses). Decision needed.

## What the spec asked (OVERNIGHT_F, action 4)
> `nudge_stale_goal` (Manager+): sends a nudge on one of the caller's stale goals
> surfaced by `aiApi.staleGoals`. Confirm-in-chat with the goal id resolved
> deterministically.

## Why it doesn't wire
The stale-goals feature is **read-only + advisory** by design:
- `GET /api/ai/stale-goals` → `stale_goals_for(user)` returns dicts of
  `{goal (title), employee, days_stale}` — **no goal id**, and it **persists nothing**
  ("Advisory — suggests, never nudges anyone automatically"). `suggest_followup`
  drafts one AI sentence; it writes nothing.
- There is **no "nudge" model and no nudge-send endpoint**. `notify_kpi_nudge(...)` in
  `apps/integrations/notifications.py` is an internal Slack helper composed by Agent-2
  — not a per-goal, human-invoked, audited endpoint.

So "send a nudge on goal X" has no human-equivalent audited write to reuse, and
`stale_goals_for` doesn't even expose the goal id to resolve deterministically.

## Options for you (pick one)
1. **Add a real nudge write** — a `GoalNudge` model (goal FK, from/to users, note,
   sent_at) + `POST /api/goals/<id>/nudge` (capability `NUDGE_GOAL`, Manager+,
   scope = reporting subtree, audited `goal.nudged`) + surface the goal **id** in
   `stale_goals_for`. The agent action then wires to that endpoint like the others.
   (Recommended — it's the missing piece to make the stale-goal loop actionable.)
2. **Reuse continuous feedback** — a "nudge" becomes `give_continuous_feedback` to the
   report referencing the goal. Real + audited, but changes the semantics (feedback ≠
   nudge) and would be surprising; not recommended.
3. **Keep it advisory** — leave stale-goals read-only; the manager acts via the
   existing screens (check-in response / 1:1). No agent action.

## Not a blocker
The other five File F actions shipped green on `main`. Wiring this safely needs a
small new backend feature (option 1); it wasn't attempted rather than faked.
