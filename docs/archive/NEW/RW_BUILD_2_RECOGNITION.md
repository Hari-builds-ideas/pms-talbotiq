# RW_BUILD_2 — Recognition (card + feed)

> Read BUILD_0_READ_FIRST.md and PRODUCT_REWEIGHTING_PLAN.md (Decision 2) first; all BUILD_0 rules apply.
> Build backend-first with tests, then UI. Recognition is deliberately SIMPLE — do not over-build. The
> one real safety property is that VISIBILITY is enforced server-side (a private/manager-only recognition
> must never leak to a team/company feed). Almost zero LLM calls.

## Phase 2.1 — Backend: the Recognition model + endpoints
- Tenant-scoped `Recognition` (TenantScopedModel): tenant FK, sender (FK User, the actor), recipient (FK
  User, same tenant — cross-tenant impossible via the scoped manager), `value`/category (from the
  tenant's configurable company values; seed a sensible default list: Teamwork, Leadership, Innovation,
  Ownership, Customer Focus, Problem-Solving, Learning, Execution, Helping Others, Above & Beyond),
  message, optional badge, `visibility` (PRIVATE / MANAGER_ONLY / TEAM / COMPANY), created_at. Reactions
  as a small related model or a counts map (👍 ❤️ 🎉 🚀 👏).
- Endpoints (all tenant-scoped, RBAC: any user can give recognition to another user in their tenant):
  create; the FEED (list) — **the feed query must enforce visibility server-side**: COMPANY → all in
  tenant; TEAM → sender's/recipient's team; MANAGER_ONLY → the recipient's manager (+ the two parties);
  PRIVATE → only sender + recipient. A user must never receive a recognition row their visibility level
  doesn't permit. React to a recognition (toggle own reaction).
- Decide in DECISIONS.md: can a recognition be edited/deleted (default: sender can delete own within a
  window; no edit — keep it simple); whether self-recognition is allowed (default: no).
- Tests: create; the visibility matrix (each level shows to exactly the right audience and NOBODY else —
  this is the security test); tenant isolation (cross-tenant recipient impossible / cross-tenant feed
  leak impossible); reactions; cannot recognize across tenants. Audit the create (INSERT) if it fits the
  audit model.

**Verify [test]:** model migration apply/reverse; the visibility-matrix tests green (the load-bearing
ones); tenant isolation green. Commit `RW_BUILD_2 2.1 — recognition model + visibility-enforced API`.

## Phase 2.2 — Backend: light recognition analytics (optional, keep minimal)
- A small aggregate endpoint (HR/manager scope): given vs received counts, top company values, monthly
  trend — tenant-scoped, aggregate-only, no cross-tenant. Reuse the analytics privacy-suppression posture
  if cohorts are small.
**Verify [test]:** aggregate is tenant-scoped + correct on seeded data. Commit `RW_BUILD_2 2.2 —
recognition analytics (light)`.

## Phase 2.3 — Frontend: the recognition card + feed
- A "Give recognition" action: pick recipient (scoped people search), pick a company value, write a
  message, choose a badge (optional), choose visibility (default TEAM) → submit. All states.
- The recognition FEED (a tab/screen reachable from the per-role nav added in RW_BUILD_1): a stream of
  recognitions the viewer is permitted to see, with reactions. LinkedIn/Slack-like, but on the existing
  design tokens — do not invent a new design system.
- Wire to the real API; respect the kind-aware error mapper; loading/empty/error states; the empty state
  invites the first recognition.
- Add recognition to the per-role nav (it was deliberately deferred in RW_BUILD_1 if the route didn't
  exist yet — now it does).
**Verify [test]+[live]:** give a recognition end-to-end; confirm on the device/stack that a PRIVATE one
does NOT appear in another teammate's feed and a COMPANY one does; reactions work; frontend tests for the
give-form + feed + a visibility rendering test. Commit `RW_BUILD_2 2.3 — recognition UI (card + feed)`.

## Phase 2.4 — Seed + demo
- Seed a few recognitions across visibility levels in seed_demo (idempotent) so the feed isn't empty in a
  demo and the visibility behaviour is demonstrable.
**Verify [live]:** the seeded feed shows correctly per role. Commit `RW_BUILD_2 2.4 — seed recognitions`.

---
## End of RW_BUILD_2
Write `RW_BUILD_2_REPORT.md`: the model + the visibility enforcement (with the matrix test results — call
this out, it's the security-relevant part), the feed/card UI, analytics, what's verified [test]/[live].
Then proceed to RW_BUILD_3 (Weekly Check-ins).
