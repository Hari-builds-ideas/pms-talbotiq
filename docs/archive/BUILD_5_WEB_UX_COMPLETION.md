# BUILD_5 — Web application UX completion (Tier-1 redesign), then the mobile readiness gate

> Read BUILD_0_READ_FIRST.md first. Build 5 of 5 in this series. The backend is now fast, async,
> concurrency-safe, observable, and prod-config-ready (builds 1–4). This build finishes the WEB
> application's UX so the features feel like a finished product — implementing the Tier-1 (and where time
> allows Tier-2) work from docs/frontend-redesign/ux-spec.md §8.3 — and ends with a MOBILE READINESS GATE
> (a check + a go/no-go, NOT the mobile build itself; mobile is a separate series that only starts after
> web is complete and Hari has looked at it).
>
> IMPORTANT: this is UI/UX work, the area where Hari's eye is the real judge. Build it well, keep every
> screen wired to the REAL API with all states, but flag the visual/subjective calls for Hari in the
> report rather than assuming them settled. ZERO LLM calls beyond reusing seeded/PENDING AI artifacts.

Each screen below: keep the real data wiring, RBAC/feature-flag gating, HITL/confidence treatment, the
error-code states (400/401/403/404/409/422/429/503), loading skeletons, and empty/first-run states. No
dead buttons, no mock-only screens. Verify each against the running backend (VITE_USE_MOCKS=false).

---

## Phase 5.1 — Command-center dashboards (the biggest lift)

Replace the per-role tile-dump dashboards with insight-first command centers (per ux-spec §8.3):
- A pinned "needs you" band driven by REAL counts: approvals awaiting, reviews to write/approve, feedback
  summaries to release (HRBP), feedback requests to give, AI jobs that finished and need a human decision.
  Each item links straight to the action; add one-click bulk actions where the backend supports them
  (e.g. approve-many in the inbox) — only real, scoped actions.
- Role-appropriate insight widgets using recharts (already a dep): team performance distribution / risk
  bands (manager/HRBP), cycle progress, KPI attainment summaries — fed by the real analytics/goals reads
  (now cached + N+1-free from builds 1 & 4). Tabular numbers, the indigo design tokens.
- Keep employee cockpit vs manager+ hub split as today (don't invent an employee web surface — that's
  mobile).

**Verify [live]:** each role's dashboard shows real needs-you counts that navigate correctly + at least
one real data-viz; bulk action works against the API. Capture per role in PROGRESS.md. Commit
`BUILD_5 5.1 — command-center dashboards`.

## Phase 5.2 — Goals & KPIs: wizard + live weight + attainment viz

- Replace the form-dump create dialog with a guided goal-creation WIZARD: step through goal → KPIs →
  weights, with a LIVE weight bar that enforces the 100% sum (server-validated, the rule already exists)
  and shows green/over/under in real time. 
- Replace one-by-one actual entry with a clearer recording UX (inline edit / batch where sensible),
  optimistic + 409-aware (build 4's versioning), recompute → risk badges update.
- Add attainment gauges / progress viz per goal/KPI (target vs actual vs pace) using recharts.

**Verify [live]:** create a goal via the wizard (weights enforced live), record actuals, recompute,
gauges update. Commit `BUILD_5 5.2 — goal wizard + attainment viz`.

## Phase 5.3 — Reviews: polished AI draft + draft-vs-final + comments

- Build on BUILD_2's async job UX: the "request AI draft" flow shows a clean working state → poll →
  PENDING draft in its HITL gate with the confidence chip. Make it feel intentional (skeleton + status,
  not a frozen button).
- Add a draft-vs-final treatment (clearly show AI-DRAFT vs human-edited vs FINALIZED) and inline
  comments/edit affordances on sections. Preserve the state machine (DRAFT→PENDING→APPROVED→FINALIZED)
  and the approval-route hook.

**Verify [live]:** the full review flow incl. AI draft → edit → submit → approve → finalize, all states
visible. Commit `BUILD_5 5.3 — review AI/HITL UX + draft-vs-final`.

## Phase 5.4 — Career, Succession, Analytics depth

- Career: concrete tiers with progress-to-target visualization (not abstract); per-tier progress
  controls; the AI enrich draft clearly advisory. RESOLVE the flagged gap: either add an accept→ACTIVE
  endpoint for an enriched AI roadmap (so a human can adopt it) OR present it explicitly as an advisory
  alternative with no "active" implication — decide in DECISIONS.md and implement (if adding the
  endpoint, scope/test it server-side).
- Succession (HRBP-only, employees still 404): an interactive nine-box (drag or click to reposition with
  a real persisted override where the backend supports it), a coverage heatmap (RED/AMBER/GREEN), bench
  depth + readiness, and a real plan-detail view (the generated→enriched→published narrative in its HITL
  gate).
- Analytics: richer recharts viz for individual trend + department, with the min-cohort (<5) suppression
  made VISUALLY explicit (aggregate-only + a privacy notice for small cohorts). The 4-vs-5 boundary must
  read clearly.

**Verify [live]:** career progress + the accept/advisory decision works; succession nine-box/heatmap/
plan-detail work and employees still 404; analytics suppression boundary reads clearly. Commit per
sub-area, e.g. `BUILD_5 5.4a — career`, `5.4b — succession`, `5.4c — analytics`.

## Phase 5.5 — Cross-cutting polish & remaining surfaces

- Typed tenant-config form (replace the raw JSON), integrations test-connection + event-log affordances
  (no-op until real creds, but the UI is complete), audit console date-range filter + readable action
  labels (build on the name-resolution from earlier), chat history within a session (still read-only/
  RBAC-bound/write-blocked), breadcrumbs everywhere (primitive exists), the cmdk command palette wired to
  real navigation + actions, sonner toasts standardized, a global error boundary, consistent empty/
  first-run states, and a polished login + app shell.
- Apply the error-code mapper consistently (429 shows Retry-After + upgrade hint; 503 shows the calm
  "AI unavailable, manual path works"). Ensure the desktop hub degrades gracefully on a narrow viewport
  (true responsive self-service is mobile, not this).

**Verify [live]+[build]:** spot-check the polished surfaces against the API; build/tsc/lint clean; the
command palette navigates + acts for real. Commit `BUILD_5 5.5 — cross-cutting polish`.

## Phase 5.6 — Frontend test coverage for the new UX

- Add Vitest/RTL tests over the new load-bearing UI logic: the needs-you/bulk-action gating, the goal
  weight-sum wizard validation, the AI-job polling state machine (working→pending→degraded→failed), the
  409 stale-write handling, the suppression rendering, RBAC/feature-flag gating on the new surfaces.
- Keep meaningful coverage of the risky bits (not 100%). Ensure build/tsc/lint stay clean.

**Verify [test]+[build]:** new frontend tests pass; build green. Commit `BUILD_5 5.6 — frontend tests for
new UX`.

## Phase 5.7 — MOBILE READINESS GATE (assess + go/no-go; do NOT build mobile here)

- Verify the prerequisites the mobile series needs (per MOBILE_BUILD_PLAN.md): the self-service endpoints
  exist and are now N+1-free/cached (my-features, my goals, record actual, my review + self-assessment,
  give 360 + my-cycles summary, career roadmap + progress, chat, nudges). Confirm each is solid and list
  any thin gap (e.g. a device-register endpoint for push is a known later add).
- Confirm the shared layer is extractable: the typed API client, types/enums, the error-code mapper, the
  RBAC/feature-flag helpers, and the auth/refresh logic are platform-agnostic enough to lift into a
  shared package for Expo/RN reuse. Note exactly which files would move (don't move them yet).
- Write `MOBILE_READINESS.md`: prerequisites met / gaps, the shared-layer extraction list, and a clear
  GO/NO-GO recommendation for starting the mobile series — explicitly stating mobile starts only after
  Hari has reviewed the finished web app.

**Verify:** the readiness checklist is accurate against the code. Commit `BUILD_5 5.7 — mobile readiness
gate`.

---

## End of BUILD_5 (and the series)
Write `BUILD_5_REPORT.md` AND a `SERIES_COMPLETE_REPORT.md` summarizing builds 1–5: what's now
production-ready at the code level (perf, async AI, atomic limits, replica-ready router, prod config,
metrics, concurrency, caching, finished web UX), what is verified [test]/[live]/[build], the full
commit/push list, all QUESTIONS/DECISIONS/BLOCKER files, the final backend + frontend test counts, and
the explicit statement of what remains OUTSIDE this series (infra provisioning + the Gemini key — both
Hari/company actions). Put the visual/subjective calls that need Hari's eye in a clearly-marked section.
Mobile is the next, separate series — start it only after Hari reviews the web app.
