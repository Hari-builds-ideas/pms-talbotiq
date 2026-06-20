# DECISIONS.md — non-trivial choices in the build series

> Each entry: the decision · options considered · why · safe-default rationale ·
> the QUESTIONS.md item it resolves (if any).

---

### D1 (BUILD_1/1.2) — Where the N+1 fix lives, and the "bounded" threshold

**Decision.** Add `select_related`/`prefetch_related` at the point that owns the
queryset for each list path: in the **view** when the view builds it inline
(reviews, goals, org, feedback), in the **service** when a service function
returns it (jd `search_jds`, career `list_roadmaps`). The budget guard
(`ScalingResult.is_bounded`) treats an endpoint as bounded when extra rows add
`≤ max(2, extra_rows//4)` queries — i.e. a small constant, not one-per-row.

**Options considered.** (a) one central `.select_related` mixin on pagination —
rejected: the FK set differs per serializer and a blanket join risks pulling
unused tables; (b) `prefetch_related` everywhere — rejected: a forward FK is
cheaper as a JOIN (`select_related`); prefetch is reserved for the one reverse
relation (goals→kpis). (c) per-row caching — rejected: doesn't fix the query.

**Why safe.** Output bytes are identical (only query count changes); no scope,
tenant, or RBAC predicate is touched; the feedback fix select_relates only
`subject` (givers are never on that serializer), so anonymity is unaffected.
Verified by the 6 app suites (354) + the budget module.
