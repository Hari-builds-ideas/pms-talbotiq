# AI quick win 3 — stale-goal nudge (report + UI follow-up spec)

Built overnight, **backend-only + additive** (D36). READ-ONLY + scope-bound: surfaces a manager's ACTIVE
goals with no KPI progress in ~30 days and drafts ONE follow-up suggestion. Advisory — it **suggests**,
it never nudges anyone automatically and persists nothing.

## What shipped (backend)

- **Agent** `apps/ai/agents/stale_goals.py`:
  - `stale_goals_for(user, days=30)` — DETERMINISTIC, read-only: ACTIVE goals in the caller's reporting
    subtree whose latest KPI measurement is older than `days` (or which have none). Tenant-/scope-bound.
  - `suggest_followup(user, stale)` — ONE short AI suggestion via the `LLMGateway` for the batch (called
    at most once, and only when there ARE stale goals). Returns `None` with no provider — the list still
    stands.
- **Endpoint** `GET /api/ai/stale-goals` (`StaleGoalsView`, `VIEW_TEAM_SCORES` — Manager+) → `{stale:
  [{goal, employee, days_stale}], suggestion: str|null}`. AI-throttled.
- Reuses `VIEW_TEAM_SCORES`; no auth/SSO/shared/deploy/nav/matrix change.

## Verification

- **[test]** `apps/ai/tests/test_stale_goals.py` (4): stale-vs-fresh detection + scope (an employee with
  no subtree sees nothing); suggestion drafted only when stale (FakeLLMProvider); suggestion `None` with
  no provider (graceful); endpoint manager-200 (with list + suggestion) / employee-403. Full backend
  suite green; frontend untouched + green. **No live OpenAI.**

## UI follow-up (for review — NOT built overnight)

1. `shared`: `aiApi.staleGoals = () => unwrap<{stale:{goal:string;employee:string;days_stale:number|null}[];
   suggestion:string|null}>(api.get("/ai/stale-goals"))` + types.
2. A manager-dashboard tile or a panel on the Team Analytics / Goals screen: list the stale goals with
   their staleness and show the AI suggestion as advisory copy + a "start a check-in" link. (Either
   touches an existing screen / nav, so it needs your review.)
3. Optional later: turn "follow up on these" into a **propose-and-confirm action** (RW_BUILD_4 registry)
   so a manager can approve a batch nudge — but only mapped to a real audited write.
