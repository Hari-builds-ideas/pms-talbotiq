# A_TOOLS.md — the permission-scoped read-tool set

Define the fixed set of typed tools the Gemini agent calls. The model composes these to answer questions;
it never writes SQL and never sees the DB. Aim for ~8–12 mid-grained tools (research §1). Each tool: a
clear name, a typed schema (JSON-schema for Gemini function-calling), an ORM-backed implementation, and a
scope check on every call.

## Where scope comes from (critical)
Every tool receives the caller's identity + role + tenant from a TRUSTED server-side context object that
is NOT part of the model-visible arguments. The model may pass a `person_id` or a `team` selector, but the
tool decides whether the caller may see that data — via the existing access checks. The model cannot set
or spoof "who am I".

## The tool set (implement each; adjust names to the codebase)
Resource/read tools:
1. `find_people(query)` → resolve names company-wide (reuse the existing resolver): returns id, name,
   email, team, role for matches. Directory-level (company-wide).
2. `get_person_overview(person_id)` → cycle status, pace, risk band, headline — DATA-scoped (caller must
   be allowed to see this person; else a denied marker).
3. `get_person_goals(person_id)` → goals + weights + progress — DATA-scoped.
4. `get_person_kpis(person_id)` → KPIs with target/actual/attainment% — DATA-scoped.
5. `get_person_reviews(person_id)` → review status/state (not raw private text beyond scope) — DATA-scoped.
6. `get_cycle_scores(person_id, cycle?)` → score(s) for one or more cycles — DATA-scoped (enables
   improvement/delta questions).
7. `get_my_team()` → the caller's reporting set (ids + light summary) — scoped to who they manage.
8. `get_feedback_summary(person_id)` → 360 summary state — DATA-scoped.
9. `list_check_ins(person_id?)` → recent check-ins/mood — DATA-scoped.

Aggregate/compute tools (backend does the math — research §2):
10. `rank_team(metric, order, cycle?)` → backend computes a ranking of the caller's scoped team by a named
    metric (pace, attainment, score, improvement-since-cycle). Returns ordered list with the computed
    numbers. The LLM never sorts raw rows itself.
11. `team_aggregate(metric, filter?)` → backend computes counts/averages ("how many behind pace",
    "average score", "count at risk") over the scoped team.
12. `compute_improvement(person_id|team, from_cycle, to_cycle)` → backend computes deltas between cycles.

> All ranking, counting, averaging, delta math happens in these backend tools in Python from scoped rows.
> The model requests the computation and phrases the result — it must not do arithmetic on returned rows.

## Rules for every tool
- Re-run the permission check on EVERY call, from the trusted context. Out-of-scope person → return a
  structured `{"denied": true, "reason": "..."}`, never the data.
- Tenant-isolated (existing tenant scoping) — a tool can never reach another tenant.
- Return typed, minimal, structured data (ids + the fields needed) — not huge blobs.
- Efficient at 5,000 people: indexed queries, bounded result sizes, no full scans, no N+1.
- No hardcoded names or seed-specific logic.

## Tests
- Each tool returns correct data for an in-scope target and `denied` for an out-of-scope target.
- Aggregate tools compute correct numbers vs a hand-checked fixture.
- Cross-tenant call returns nothing/denied.
- Query count constant regardless of tenant size.

## Done when
The full tool set exists, typed for Gemini function-calling, ORM-backed, scope-checked per call, math in
the backend, efficient at scale, tested. Logged in PROGRESS.md.
