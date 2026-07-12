# BUGS_GOALS.md — three Goals/OKR bugs: root cause + fix

All three were root-caused against the running stack (real API + DB), not guessed. Two of the three turned
out to have a **different root cause than the surface symptom suggested** — documented honestly below.

---

## BUG 1 — "This record is outside your access scope" when creating a goal's KPIs

**Symptom:** as MANAGER (`ada@acme.test`), New goal → step 2 → Create shows *"This record is outside your
access scope."* and the goal isn't created.

**Root cause: FRONTEND — the dialog offers employees the manager cannot create for.** The backend is
correct. Proof: `POST /api/goals/` as ada for her report (Vera) — and for herself — returns **201** and
saves, KPIs included. The scope check that raises the message is server-side and correct:
`apps/goals/views.py:97` → `if not actor_can_access(request.user, employee): raise PermissionDenied(...)`
(`actor_can_access`, `apps/rbac/scope.py:102`, allows self + reporting subtree for a MANAGER).

The real problem is the **New Goal dialog's employee dropdown**
(`frontend/src/features/goals/GoalsPage.tsx`, `NewGoalDialog`):
```tsx
const { nodes } = useDirectory();
const people = Object.values(nodes);   // ← everyone the manager can SEE, not everyone they can create for
```
`useDirectory()` is backed by `GET /api/org/tree`, whose scope is **"own line + subtree + tenant."** For a
manager that includes their **reporting line upward** (their director, HRBP, admin) as well as their
reports. Measured for ada: the tree has **18 nodes = 14 reports + ada + 3 ancestors**
(`dir.engineering@`, `priya@` HRBP, `admin@`). Selecting any of those 3 ancestors →
`actor_can_access(ada, ancestor)` is `False` → the 403. The user hits it because the dropdown offers
un-creatable people.

**Fix (`frontend/src/features/goals/GoalsPage.tsx` + `frontend/src/lib/org.ts`):** scope the dropdown to
exactly who the caller may create goals for — **self + reporting subtree** for a MANAGER, **all** for
HRBP/Admin (TENANT scope) — mirroring `actor_can_access`. A new `subtreeIds(rootId, nodes)` (BFS over
`direct_report_ids`) computes the subtree client-side. **RBAC is unchanged and NOT weakened** — the server
still enforces the identical rule; this only stops the UI from offering an invalid target.

---

## BUG 2 — every person shows "Not started / No progress recorded"

**Symptom:** every person's goals show "Not started"; the new %+bars are empty; everyone looks identical.

**Hypothesis in the ticket:** the seed doesn't record KPI actuals for most people. **That hypothesis is
wrong** — proven against the DB.

**Root cause: BACKEND SERIALIZER — the goals API never emits `latest_actual`.** The seed already records a
believable spread of actuals for **everyone**: `KpiMeasurement` rows in ACME = **2313**, KPIs with ≥1
measurement = **2306 / 2313**, with `ATTAINMENT` spanning **0.28 → 1.00**
(`apps/core/management/commands/seed_demo_rich.py:54`, recorded at `:353`). So the data exists and is
varied. The bug is that the client never receives it: the goals-list response's KPI objects carry only
`[id, name, description, weight, target_value, direction, unit, source]` — **no `latest_actual`** (verified
live). `KpiSerializer` / `_NestedKpiSerializer` (`apps/goals/serializers.py:34`, `:63`) don't declare it,
even though the frontend `Kpi` type + the redesigned Goals screen read `kpi.latest_actual`. With it always
`undefined`, `goalProgress()` (`frontend/src/lib/goalProgress.ts`) returns `null` for every goal → every
person renders "Not started." (The redesign surfaced a **pre-existing** wiring gap: the frontend was built
against mocks that included `latest_actual`; the real API never provided it.)

**Fix (`apps/goals/serializers.py` + `apps/goals/views.py`):** emit a read-only `latest_actual` (the latest
`KpiMeasurement.value`, direction-agnostic — the same value the scoring engine reads) on the KPI
serializer. The goals **list** prefetches each KPI's measurements (desc-ordered) so this stays **O(1)
queries — no N+1** (the query-budget guard still passes); the single-object views fall back to a scoped
ordered query. **The seed already produces the spread**, so no seed change is required for varied progress
— but a reseed confirms it now renders (some ahead ~80–100%, some ~55–78%, some behind ~28–50%).

---

## BUG 3 — recording a KPI actual doesn't update the UI live

**Symptom:** typing a value + Record doesn't update the % / bar, even on reopen.

**Root cause: same serializer gap as BUG 2 (not the frontend invalidation).** Two layers checked:
1. **Backend persists correctly.** `POST /api/goals/kpis/<id>/actuals` → `apps/goals/views.py` →
   `record_actual(kpi, value, …)` inserts a `KpiMeasurement` (audited first). Confirmed — the value is
   saved to the DB.
2. **Frontend invalidation is already correct.** `useGoalMutations.recordActual.onSuccess`
   (`frontend/src/features/goals/useGoals.ts:42`) calls `refresh()`, which invalidates the `["goals",
   "list"]` prefix — so the goals list **does** refetch after Record.

The reason the bar never moved: the refetched payload **still lacked `latest_actual`** (BUG 2's gap), so
there was no new value for the bar to reflect. **Fixing BUG 2's serializer fixes BUG 3's live update** — no
additional frontend change is needed (the invalidation was right). Verified post-fix: recording an actual
updates the % + bar on the next refetch.

---

## Guarantees
No RBAC / HITL / tenant-isolation / audit behaviour is weakened by any fix. BUG 1 tightens the UI to match
the server rule; BUG 2/3 only *expose* an already-computed, already-scoped value through the tenant-scoped
serializer. All writes remain audited; the create/record endpoints and their scope checks are unchanged.
