# AI quick win 4 — natural-language search (report + UI follow-up spec)

Built overnight, **backend-only + additive** (D36). Ask in plain language ("who's missing goals?",
"which reports haven't checked in this week?") and get a scope-bound answer. The LLM **only classifies**
the question into a fixed supported search; the search itself is DETERMINISTIC and runs through the
caller's reporting scope — it can only ever return people the caller can already see. Read-only.

## What shipped (backend)

- **Agent** `apps/ai/agents/nl_search.py`:
  - `SEARCHES` registry — `employees_missing_goals` (team members with no active goal) and
    `reports_without_checkin` (reports with no check-in this week); each a DETERMINISTIC,
    scope-bound `run(user)`.
  - `nl_search(user, query)` — classifies the query into a supported key via the `LLMGateway` (the model
    picks the key only), then runs it deterministically. Unrecognised → `{search:"unknown", results:[]}`.
- **Endpoint** `POST /api/ai/search` (`NLSearchView`, `VIEW_TEAM_SCORES` — Manager+) → `{status, search,
  results:[{id, employee}]}`. AI-throttled. 200 / 503 / 429.
- Reuses `VIEW_TEAM_SCORES`; no auth/SSO/shared/deploy/nav/matrix change. The LLM never composes a query
  or reads data — it returns one key from a fixed set; data access is the deterministic scoped query.

## Verification

- **[test]** `apps/ai/tests/test_nl_search.py`: each deterministic search returns the right scoped people
  (missing-goals / no-checkin) and is scope-bound (an employee with no subtree → empty); classify→run via
  FakeLLMProvider; an unrecognised classification → `unknown`/empty; endpoint manager-200 / employee-403.
  Full backend suite green; frontend untouched + green. **No live OpenAI.**

## UI follow-up (for review — NOT built overnight)

1. `shared`: `aiApi.search = (query) => unwrap<{search:string;results:{id:string;employee:string}[]}>(
   api.post("/ai/search", { query }))`.
2. Either a small search box on the manager dashboard / Team Analytics, or fold it into the **chat
   assistant** as another response type (the assistant already classifies intent; NL search is a natural
   "find" intent that returns a people list). Both touch existing surfaces, so they need your review.
3. Extend `SEARCHES` with more scoped queries over time (each deterministic + scope-bound).
