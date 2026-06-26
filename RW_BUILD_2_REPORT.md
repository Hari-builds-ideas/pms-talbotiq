# RW_BUILD_2_REPORT — Recognition (kudos card + feed)

A deliberately simple peer-recognition feature, backend-first. The **one load-bearing safety property —
server-enforced visibility** — is built and proven both by unit test and live over the running stack: a
card reaches exactly its permitted audience and **no one else**.

All phases complete, committed, pushed, green, deployed, and live-verified.

## Phases

| Phase | What | Commit |
|---|---|---|
| 2.1 | `Recognition` + `RecognitionReaction` models (migration 0001); visibility-enforced feed + create + react + sender-only delete; RBAC caps | `06b2dd1` |
| 2.2 | light aggregate analytics (no per-person leaderboard) | `06b2dd1` |
| 2.3 | frontend feed + give-dialog + reactions; shared `recognitionApi` + types; `/recognition` route; **Recognition** nav item | _this commit_ |
| 2.4 | idempotent `seed_demo` recognitions across all visibility levels | _this commit_ |

## The security property (call-out)

Visibility is decided **server-side** in `apps/recognition/services.recognition_feed` (one Q-object
predicate) — the client is never trusted. Levels:

- **PRIVATE** → the two parties ONLY (not even HR/Admin — private is private);
- **MANAGER_ONLY** → + the recipient's direct manager;
- **TEAM** → + the recipient's/sender's immediate team (you manage a party, or share a manager with one);
- **COMPANY** → everyone in the tenant.

Role/data-scope does **not** widen this. Reacting is gated the same way (react only to a card you can
see; otherwise 404 — never reveal it exists). Tenant isolation rides on the `TenantScopedManager`
(cross-tenant recipient/feed impossible).

**Proven two ways:**
- **[test]** `apps/recognition/tests/test_recognition.py` — the `test_visibility_matrix` checks **8
  viewers × 4 levels** (sender, recipient, recipient's manager, sender's manager, each party's peer, an
  unrelated employee, and an Admin) and asserts each sees *exactly* its permitted set. Plus cross-tenant
  recipient/feed isolation, reactions + unseen-card-404, sender-only delete, and the analytics aggregate.
- **[live]** over the running HTTP stack (`GET /api/recognition/` with per-user JWTs) on the seeded data:
  - `reza` (a party on all 4 cards) → sees `[COMPANY, MANAGER_ONLY, PRIVATE, TEAM]`;
  - `ada` (the other party) → sees all 4;
  - **`mia` (an unrelated teammate, different team)** → sees **`[COMPANY]` only** — PRIVATE / TEAM /
    MANAGER_ONLY do **not** leak to her.

## What shipped

- **Backend** (`apps/recognition/`): models, services (the visibility/feed/react/delete/analytics logic),
  serializers, RBAC-gated views, urls under `/api/recognition/`. Capabilities `GIVE_RECOGNITION` /
  `VIEW_RECOGNITION` (all roles) + `VIEW_RECOGNITION_ANALYTICS` (Manager+) added to the matrix (+ its
  oracle test updated).
- **Frontend** (`features/recognition/`): the feed (cards with sender→recipient, company value, message,
  a **visibility** badge, reaction chips with counts, sender-only delete) + a give dialog (scoped
  recipient picker, value, message, visibility). On the existing design tokens — no new design system.
  `recognitionApi` + types added to the shared layer; `/recognition` route; the **Recognition** nav item
  (deferred in RW_BUILD_1) now lives in the everyday Workspace set for all roles.
- **Seed**: 4 cards/tenant across PRIVATE/MANAGER_ONLY/TEAM/COMPANY, idempotent.

## Decisions (kept simple — "do not over-build")

- **D32**: server-enforced visibility; **no edit, sender-only soft delete** (no time window); **no
  self-recognition**; **fixed company-values list**; **aggregate-only analytics** (no per-person
  leaderboard, which would re-identify individuals).
- **Q7**: per-tenant *configurable* company values deferred (a fixed list now; a config model would be
  over-building for the MVP).

## Verification

- Backend suite **1243 passing**, 2 deselected (+9 recognition tests, +12 parametrized matrix-oracle
  cases for the 3 new capabilities).
- Frontend **91 passing** (+3 recognition + nav update), `tsc`/`eslint`/`build` clean.
- Live: the visibility check above; seed idempotent (4 cards/tenant after two runs); frontend rebuilt +
  deployed.

## Your device check (before RW_BUILD_3)

Hard-refresh http://localhost:8080. Log in as **`reza@acme.test`** (Employee) → open **Recognition** in
the sidebar → you should see the seeded cards (incl. the private one to you), and you can **Give
recognition** to a teammate. Then log in as **`mia@acme.test`** (a different team) → Recognition shows
**only the company-wide card**, never the private/team/manager-only ones. Reactions toggle on click.
Password `Passw0rd!demo`.

## Next

RW_BUILD_3 — Weekly Check-ins (from the outline; full feature, backend-first).
