# D_SCALE_AND_HARNESS.md — prove it at 5,000 people, automatically

The whole point is that it works for ANY company size and ANY person, not the demo 10/211. Prove it.

## 1. Generate a large tenant
Add a management command (e.g. `seed_scale_tenant`) that creates a tenant with a configurable headcount —
default 5,000 people — with realistic names (including deliberate DUPLICATE full names and near-duplicate/
typo-prone names), teams, reporting lines, goals, KPIs, reviews, and cycle data. Deterministic and
idempotent. This is a TEST fixture — never auto-run in production.

## 2. Behavioural harness (the real proof)
Add `scripts/agent_scale_harness.py` that, against the large tenant, exercises the assistant end-to-end
and asserts correct behaviour — not just that code runs. It must:
- Pick MANY random people from across the whole company (not a fixed list, not only one team) and, as an
  appropriate role:
  - resolve them by exact full name → asserts resolved, no disambiguation.
  - resolve by typo → asserts fuzzy suggestion.
  - give recognition → asserts posted, including people OUTSIDE the actor's team.
  - complete a check-in → answers the follow-up question → asserts created (proves the pending-slot fix).
  - "do the same for <another random person>" → asserts same action repeated.
  - ask "how is <person>" for an in-scope person → asserts a real, data-grounded answer (not a template).
  - ask for an OUT-OF-SCOPE person's data → asserts honest refusal.
  - compare two random in-scope people → asserts both appear with reasoning.
- Include social-engineering / injection probes at scale → all refused.
- Assert DB query efficiency: resolution is a constant, bounded number of queries regardless of the 5,000
  headcount (no full-table scan, no N+1).
- Print PASS/FAIL per category with a final tally; exit non-zero on any failure.

## 3. Duplicate & edge names
Explicitly test: two real "Priya Nair" → disambiguation with emails; a person whose first name equals
another's last name; unicode/accented names; very long names. All resolve or disambiguate correctly, never
crash, never wrong-person.

## 4. Performance
Report the resolution latency and query count at 5,000 people. If anything scales with headcount instead
of staying constant, fix it (add the index / move filtering to the DB) and re-measure.

## Done when
The large-tenant harness passes for many random people across the whole company, including out-of-team
actions, answered follow-ups, reasoned data answers, duplicates, and scope refusals — with constant-cost
resolution at 5,000 people. Logged in PROGRESS.md.
