# NAMES_AND_VERIFY_MORNING_REPORT.md

**Run:** (1) root-cause + fix the UUID-instead-of-name bug everywhere; (2) verify
the four wired-but-unproven flows live. Unattended, Claude Opus.
**Outcome:** both done. The name bug is fixed at the root (server-resolved labels
+ a frontend guard that can never render a uuid), verified live. All four flows
were exercised end-to-end over real HTTP with transcripts captured; one minor
observation + the OIDC IdP-boundary limit are noted honestly. Groq usage: **0**
(no LLM calls — pure serializer/UI/flow work).

---

## PART 1 — the UUID-instead-of-name bug

### Root cause (not a one-off)
The UI resolved person names via `useDirectory`/`PersonName`, which read the
**scope-limited org tree** and **fell back to the raw UUID** for any id not in it
(a reviewer up the chain, an unloaded tree) — and couldn't resolve non-user
entities (cycles, JDs) at all. So "Reviewer: <uuid>" appeared whenever the
reviewer was outside the viewer's subtree. Patching one screen would not fix it.

### The fix — resolve labels server-side, render them, guard the client
- **`apps/core/display.person_label`** — the single label rule: `display_name`,
  else the email local-part; **never a uuid**; null-safe.
- **Every serializer that exposed a bare person/entity FK now also returns a
  resolved `*_name` / `*_title` beside the id** (ids kept for keys/links):
  - **reviews** — employee/reviewer/human_reviewer/cycle (+ calibration row);
    assessment assessor; transition actor
  - **audit** — actor (+ "System" for null); target stays a typed `<type> #ref`
  - **approvals** — approver / decided_by / initiated_by (route, step, inbox)
  - **goals** — employee / created_by / approved_by
  - **org positions** — filled_by + reports_to (both USERS) + published_jd title
  - **succession** — incumbent / bench candidate / nine-box employee; the engine's
    `ranked_bench` now carries `candidate_name` (fixing a latent `candidate` key
    the UI referenced but the API never returned)
  - **career** — employee + target_jd/target_position titles
  - **jd** — created_by + request requested_by
  - **feedback** — subject (cycle / my-cycles / summary); 1:1 participants
- **Anonymity preserved:** the giver is resolved ONLY on the inviter/giver-facing
  `FeedbackRequest` surface (where the caller already knows them); the **anonymised
  payload and the summary never carry a giver name** (verified live + by test).
- **Frontend:** `PersonName` takes an optional server `name` (preferred over the
  directory) and a `looksLikeUuid` guard means it can **never render a uuid**
  (unresolvable → "Unknown"); `useDirectory`/`useCycles` fallbacks no longer return
  a raw id. Wired the new labels through reviews, approvals, audit, org, feedback,
  goals-adjacent, jd, succession, career, and the cockpit. Updated the TS types +
  MSW mock fixtures.

### uuid-leak occurrences found + fixed (frontend `<PersonName>` / id render sites)
reviews: ReviewsListPage (employee, reviewer, cycle), ReviewDetailPage (header
employee+reviewer+cycle, details employee/reviewer/cycle/human_reviewer, timeline
actor), ReviewEvidence (assessor) · approvals: RouteTracker (approver) · audit:
AuditPage (actor) · org: OrgPage (reports_to, filled_by, vacancy reports-to) ·
feedback: FeedbackPage (cycle subject, summary subject), CycleSheet (subject,
invited giver) · jd: JdListPage (requested_by) · succession: RoleSheet (bench
candidate ×2) · career: CareerPage (employee) · cockpit (review employee, summary
subject). The remaining in-scope-only sites (GoalsPage group key, nudges tile,
analytics cohort row, NineBoxGrid) render subjects already in the caller's tree
and are additionally covered by the never-a-uuid guard.

### Live before → after (real HTTP, acme)
- **Reviews (the reported screen):** reviewer id `7ef82454…` → **"Lin Zhao"**;
  employee → **"Kai Andersen"**; cycle → **"H1 2026"**.
- **Audit actor** → **"Avery Stone"** (null actor → "System").
- **Org position:** reports_to → **"Priya Nair"**, filled_by → **"Ada Lovelace"**.
- **Approvals inbox/route:** `approver_name` present.
- **Feedback summary subject** → **"Ada Lovelace"**; cycle list subject resolved.
- **Anonymity:** the anonymised payload items expose only `pseudonym/body/
  marked_sensitive` — **no giver name**; the inviter's request list shows the
  giver ("Lin Zhao"), the allowed surface.

### Tests
`apps/core/tests/test_display.py` (6): `person_label` (name / local-part / null);
the review serializer resolves names not uuids; the anonymised payload never
contains a giver name; the summary resolves the subject but has no giver. Full
backend suite green; frontend tsc + eslint + build + 25 vitest green.

---

## PART 2 — the four wired-but-unproven flows (live)

### 1. Approval route — PROVEN end-to-end ✅
Admin created + activated a SEQUENTIAL `review` workflow (MANAGER → HRBP).
- ella's review → start-edit → submit → approve → **finalize ENTERED the route**
  (state APPROVED, route IN_PROGRESS, 2 PENDING steps).
- step 1 approve (ada) → step1 APPROVED / step2 PENDING (**tracker advanced**);
  step 2 approve (priya) → route **APPROVED** → review **FINALIZED**.
- ines's review → route → **reject (with reason)** → route **REJECTED** → review
  back to **EDITING** (artifact rollback).
- Workflow **deactivated** afterward (demo state restored).
- **Escalation:** the step carried `timeout_hours`/`escalation_role` (accepted);
  triggering it needs the overdue beat (can't force live) — it is covered by
  `apps/approvals/tests/test_escalation.py`.
- **Observation (not a blocker):** an approval-*step* reject accepts an EMPTY
  comment (200), unlike the review-level reject which requires a reason (422). The
  reject still works (route REJECTED + rollback); whether a step-reject comment
  should be mandatory is a small product call — flagged, not changed.
- *Demo-state note:* this created ella (FINALIZED) + ines (EDITING) reviews
  (runtime artifacts; `TenantScopedModel` soft-deletes, so they can't be cleanly
  removed without holding their unique slot — left in place, harmless).

### 2. Entitlement upgrade flip — PROVEN + restored ✅
globex (STARTER): premium agent1/3/4/5/jd_generator/career_roadmap all **locked**
(agent2 + chat on). `POST /billing/upgrade {FULL_AI}` → **all premium unlocked**
(flags flip app-wide). **Restored** globex to `['STARTER']` via the model + a
tenant-cache invalidation (there is no API downgrade; the upgrade's own cache
invalidation is why the raw write first needed `invalidate_tenant_cache`) —
re-verified premium re-locked, agent2+chat still on. Demo state unchanged.

### 3. MFA + OIDC — PROVEN to the provable boundary ✅
- **seed_demo** now idempotently enrols a standing MFA account **`mfa@acme.test`**
  (password `Passw0rd!demo`) with a CONFIRMED TOTP device on a **fixed** secret
  (base32 **`JBSWY3DPJVDEDXVNX3XQCI2FM6E2XTPP`**) — runs twice clean (1 user, 1
  device, no dupes).
- **Two-step login (live):** `POST /auth/login` → `mfa_required:true` + an
  `mfa_token`, **no access token**; computed the current TOTP from the secret →
  `POST /auth/mfa/challenge {mfa_token, code}` → **access + refresh issued**. A
  wrong code → **401 mfa_invalid**.
- **Enroll endpoint (live):** `POST /auth/mfa/enroll` (authenticated) returns a
  `secret` + `config_url`.
- **OIDC:** `GET /auth/oidc/complete` with no session → **401** (the IdP-handoff
  boundary). **Cannot fully verify the SSO round-trip without a real IdP** —
  honestly out of scope here; the local-login + MFA path is the primary entry.

### 4. Analytics min-cohort suppression — the 4-vs-5 edge PROVEN ✅
Extended seed_demo (idempotent) with a 21st employee (**Vera Lindqvist**) who
round-robins to Ada, giving Ada exactly **5** scored reports. Live:
- **Ada (cohort 5):** `suppressed:false`, **5 individuals shown** + aggregate.
- **Lin (cohort 4):** `suppressed:true`, **0 individuals** (aggregate-only).
The precise <5-suppressed / ≥5-shown boundary now demonstrates out of the box.

---

## Commits + push (both pushed to origin/main, fast-forward)
- `81666dc` Fix the UUID-instead-of-name bug at the root (10 serializers + engine +
  the frontend guard + tests + 27 wired call-sites). Backend 1065 green.
- `<this commit>` seed_demo: a standing MFA-enrolled demo account + the 21st
  employee that creates the live 4-vs-5 analytics min-cohort edge (idempotent;
  runs twice clean). + this report. Backend 1065 green.

## Groq usage
**0 LLM calls** — this run was serializer/UI/flow + seed work. No AI agents were
re-run (existing PENDING/seeded artifacts reused).

## NEEDS_HARI / BLOCKER
- **No BLOCKER files.** No new NEEDS_HARI.
- One small product call flagged: should an approval-*step* reject require a
  comment (like the review-level reject does)? Currently optional; the flow works
  either way.

## What remains
- Optionally make the step-reject comment mandatory (1-line validation + a test).
- The full OIDC/SSO round-trip needs a real IdP to verify (infra, not code).
- The in-scope-only PersonName sites (GoalsPage/nudges/9-box/analytics rows) could
  also pass server names for consistency — they already never show a uuid (guard).

## Top thing to do next
**Finish-the-web Tier-1 UX** (the command-center dashboards + goal wizard + review
AI streaming, per `docs/frontend-redesign/ux-spec.md` §8.3): the data is now clean
(real names everywhere) and the core flows are all proven live, so the highest
remaining leverage is making the screens *feel* premium rather than plain.
