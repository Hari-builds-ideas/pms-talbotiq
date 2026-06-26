# RW_BUILD_3_REPORT — Weekly Check-ins

The core engagement loop, backend-first: an employee writes a short weekly check-in (mood, wins,
blockers, learning, priorities); their manager reads and responds. Scope is enforced server-side and
proven both by test and live. Goal progress is **pulled read-only** from the goals engine — the check-in
duplicates no goal/review state (it feeds review evidence; it is not a review).

Committed, pushed, green, deployed, live-verified.

## What shipped

- **Backend** (`apps/checkins/`): `CheckIn` + `CheckInPriority` + `ManagerResponse` (TenantScopedModel,
  migration 0001); services (scope-bound CRUD, manager response, read-only goal-progress pull);
  RBAC-gated views; urls under `/api/checkins/` (`mine`/upsert, `team`, `<id>` incl. goal progress,
  `<id>/respond`). Capabilities `MANAGE_OWN_CHECKIN` (all), `VIEW_TEAM_CHECKINS` / `RESPOND_CHECKIN`
  (Manager+) added to the matrix (+ oracle test).
- **Frontend** (`features/checkins/`): `CheckInsPage` — a "My check-ins" tab with the weekly form (mood
  1–5, wins/blockers/learning, priorities) + history (with the manager's response), and a manager-only
  "My team" tab listing reports' check-ins with an inline respond (comment, needs-follow-up, add-to-1on1).
  `checkinsApi` + types in the shared layer; `/checkins` route; **Check-ins** nav item in the everyday
  Workspace set (all roles).
- **Seed**: a check-in for reza (+2 priorities, +a manager response from Ada) per tenant, idempotent.

## The scope property (call-out)

Enforced in `apps/checkins/services`:
- an employee writes/reads their **OWN** check-ins;
- a manager reads + responds within their **reporting subtree** (`actor_can_access`);
- cross-manager / peer access → **404** (never reveal it exists); cross-tenant impossible
  (`TenantScopedManager`); a manager can't respond to their own check-in (403).

**Proven two ways:**
- **[test]** `apps/checkins/tests/test_checkins.py` (9): a manager sees only their reports'; cross-manager
  + peer detail → 404; tenant isolation; one-per-(author,week); priorities replace on re-submit; manager
  response is one-per-check-in + out-of-scope 404 + can't-respond-to-own 403; **the goal-progress pull is
  read-only** (creates nothing).
- **[live]** over HTTP on the seeded data: `ada` (reza's manager) team feed → `[Reza Pahlavi]`, detail
  200; `lin` (a different manager) team feed → `[]`, detail → **404**.

## Decisions / deferrals

- **D33**: scope in the service; one-per-week; priorities replace; read-only goal pull (no review-state
  duplication).
- **Q8**: the outline's *optional* extras were deferred — the AI manager-side summary to RW_BUILD_4/5
  (keeps RW_BUILD_3 LLM-free per the quota rule), the cadence "due" nudge + rotating custom questions as
  follow-ups. The core loop is complete and useful without them.

## Verification

- Backend suite **1264 passing**, 2 deselected (+9 check-in tests, +12 parametrized matrix-oracle cases
  for the 3 new caps).
- Frontend **93 passing** (+2 check-ins + nav update), `tsc`/`eslint`/`build` clean.
- Live: the scope check above; seed idempotent (1 check-in + 2 priorities/tenant after two runs);
  frontend rebuilt + deployed.

## Your device check (before RW_BUILD_4)

Hard-refresh http://localhost:8080. As **`reza@acme.test`** (Employee) → **Check-ins** → see this week's
form + last week's seeded check-in with Ada's response. As **`ada@acme.test`** (Manager) → Check-ins →
**My team** tab → Reza's check-in with an inline respond. As **`lin@acme.test`** (a different manager) →
**My team** is empty (Reza isn't on Lin's team). Password `Passw0rd!demo`.

## Next

RW_BUILD_4 — AI assistant: read-only → propose-and-confirm (HITL).
