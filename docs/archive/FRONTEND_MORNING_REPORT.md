# FRONTEND_MORNING_REPORT.md

**Run:** Autonomous overnight build of the PMS Admin Hub v1 (frontend only).
**Model:** Claude Opus (did not switch).
**Outcome:** ✅ **All 8 phases (0–7) completed, each committed locally, each builds clean.**
Nothing pushed. No blockers. No open `NEEDS_HARI_*` decisions.

---

## TL;DR

A complete, modern, restrained **desktop Admin Hub** is built under `frontend/`, in
React + TypeScript + Tailwind + shadcn-style primitives, running fully standalone
against an MSW mock layer whose shapes match the frontend contract 1:1. Every screen
group in the phase plan is implemented with real **loading / empty / populated /
error-by-code** states, role gating, the HITL human-gate affordances, and the
premium-locked upgrade flow.

- `npm run build` ✅ · `tsc --noEmit` ✅ (strict) · `eslint .` ✅ — clean at every phase commit.
- Dev server boots, serves the app, and registers the MSW worker (verified 200/200).
- Switchable to a live backend via one env flag (`VITE_USE_MOCKS=false`) — the typed API
  client and endpoint functions are identical in both modes.

> ⚠️ **Verification honesty:** I verified the build, typecheck, lint, and that the dev
> server serves + the mock worker registers. I could not drive a headless browser
> overnight, so I did **not** click through every screen in a real browser. The code
> follows standard, type-checked patterns, but please do a visual click-through
> (the role switcher in the top bar makes this fast).

---

## How to run it

```bash
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

- **Mock mode (default):** `frontend/.env` ships with `VITE_USE_MOCKS=true`. The whole
  app renders against MSW fixtures — no backend needed. Log in with any password; use
  the **“Demo accounts”** quick-fill on the login screen (`admin@acme.test`,
  `hrbp@acme.test`, `ada@acme.test` — the last one demos the MFA step; any 6 digits pass).
- **Preview roles fast:** the top bar has a **“Preview role”** switcher (mock-only) to
  jump between Admin / HRBP / Manager and see the nav + screens re-gate live.
- **Point at the live Django backend later:**
  1. Set `VITE_USE_MOCKS=false` in `frontend/.env`.
  2. Set `VITE_API_BASE_URL` to the backend (default `/api`; e.g. proxy `/api` to the
     Django host, or set an absolute URL).
  3. The same `src/lib/api/endpoints.ts` functions hit the real endpoints; auth uses
     `POST /api/auth/login` → access in memory, refresh in localStorage, 401→refresh→retry.

Other scripts: `npm run build`, `npm run typecheck`, `npm run lint`, `npm run preview`.

---

## Phases completed

| Phase | Name | Commit |
|------|------|--------|
| 0 | Foundation & design system | `5bf9c02` |
| 1 | Dashboard + KPI nudges tile | `8dd3bc7` |
| 2 | Admin & entitlements | `64f8414` |
| 3 | Approvals | `289a70f` |
| 4 | Reviews (HITL signature flow) | `ee7df58` |
| 5 | Org chart | `860e0be` |
| 6 | Succession & analytics | `266025e` |
| 7 | JD, audit, integrations, chat | `143bf21` |

### Phase 0 — Foundation & design system
- Vite + React + TS (strict) + Tailwind + shadcn-style primitives, project layout per the brief.
- **Design tokens** (HSL CSS variables → Tailwind theme): slate base, one confident
  **Modern Blue** primary, **purple** for AI states, **gold** for premium-locked, plus
  semantic success/warning/danger/info. Compact enterprise type scale, hairline borders,
  subtle shadows, rounded-2xl. (Palette follows the V0 brief, which supersedes the
  teal/indigo suggestion in `frontend_build.md`.)
- **App shell:** fixed dark sidebar (role-filtered, grouped nav) + top bar (tenant,
  AI-chat launcher, user menu, dev role switcher) + scrollable content with a consistent
  `PageHeader`.
- **Cross-cutting:** auth (login + MFA challenge + refresh interceptor + logout),
  `/api/auth/me` + `/api/billing/my-features` bootstrap into an Auth/Feature context,
  React Query client, one shared **error mapper** (400/401/403/404/409/422/429/503) and
  toast conventions, the **MSW mock layer** + typed axios client + enums/types generated
  from the data dictionary.
- **Shared primitives:** `DataTable` (sortable + server pagination + plain arrays),
  `StatusBadge` (fixed enum→colour map), `Stepper`/`Timeline`, `EmptyState`, `ErrorState`
  (per status code), skeleton loaders, `ConfirmDialog` (with required-reason capture),
  `FeatureGate`, HITL `DraftBadge`/`ConfidenceBadge`/`HitlBanner`, `PageHeader`, `Field`,
  `Panel`, `StatCard`, `PersonName` + a cached people directory.

### Phase 1 — Dashboard
- Role-aware, **action-first** landing composed client-side (no `/dashboard` endpoint):
  a stat strip (pending approvals, at-risk reports, coverage gaps, plan) + tiles for the
  **approval inbox**, **KPI nudges** (`/api/ai/nudges`, Agent 2, gated), **succession
  risk**, and a **Full-AI upsell**. Each tile owns its loading/empty/error states.
  Employees get a “self-service is on mobile-web” notice.

### Phase 2 — Admin & entitlements (Admin-only)
- **Users & Roles:** DataTable with create-user, change-role, set-reporting-line
  (422 `REPORTING_CYCLE` inline), edit display name, deactivate/reactivate.
- **Tenant Config:** validated free-form JSON editor (dirty/reset/save).
- **Entitlements:** plan + seats editor (`PATCH /seats`) + a feature map (locked vs
  unlocked) + the **Upgrade-to-Full-AI modal** that flips every premium flag live across
  the app (re-bootstraps the feature map).

### Phase 3 — Approvals
- Approver **inbox**, a **route-tracker slide-over** (timeline; sequential + parallel;
  per-step status/due/escalation/comment) with approve and reject-with-required-reason,
  and an HRBP+ **workflow designer** (list + activate/deactivate + create-with-ordered-steps;
  re-create to edit per open-question #3).

### Phase 4 — Reviews (the HITL signature flow)
- Paginated, cycle-filtered list + create dialog (needs an active cycle). Detail/editor
  with the **review state-machine stepper** and a state-driven action bar wiring every
  transition (start-edit / save-draft / submit / approve / reject-with-reason / finalize /
  request-ai-draft), guarded by state and the error mapper (409 illegal, 422 HITL/reason),
  a graceful **503 “AI not configured”** state, prominent **PENDING_HUMAN_REVIEW** banner
  + confidence + low-confidence warning, `AI_DRAFTING` polling, and read-only finalized.
  Sidebar shows details, assessments, transition history and the linked approval route.

### Phase 5 — Org chart
- A clean recursive **reporting tree** with per-node headcount + vacancy rollups and
  expand/collapse; a **person-card slide-over** (profile, reporting line, positions, JDs)
  with reassign (422 `REPORTING_CYCLE` inline) and 404 “not in your scope”; a paginated
  **positions** table (create / fill / close / link-published-JD / unlink, HRBP+); a
  **vacancies** list.

### Phase 6 — Succession & analytics
- **Succession** (management-only; employees 404 via API + hidden from nav): coverage
  dashboard (RED/AMBER/GREEN), a distinctive **3×3 nine-box** grid, a critical-role
  slide-over with bench + readiness overrides + mark-critical-role, and the **HITL plan
  flow** (generate → PENDING → action items → publish; red-flag/`INADEQUATE_COVERAGE`
  surfacing; 503 Agent-4 enrich seam).
- **Analytics:** individual trend (bars + table), department analytics honouring
  **min-cohort (<5) suppression** (aggregate-only + privacy notice, no individuals), and an
  HRBP/Admin **calibration grid**.

### Phase 7 — JD, audit, integrations, chat
- **JD Library:** paginated library + requests tabs, create/request dialogs, and a
  detail/editor with a versioned body editor, version history, the full lifecycle
  (save-draft / submit → 422 `INVALID_JD_INPUT` / approve → publish-or-IN_REVIEW / revise /
  archive) and the gated **AI-generate 503 seam**.
- **Audit Console:** read-only, filterable (actor / target / action), paginated, **no
  mutation controls**.
- **Integrations:** Jira/Slack enable + non-secret config + `secret_ref` captured as an
  **env-var NAME, never a token**.
- **AI chat:** a slide-over launched from the top bar — read-only, RBAC-scoped answers,
  with blocked-write / 503 / feature-locked states. (Built into the shell in Phase 0.)

---

## Contract fidelity notes

- **No invented endpoints/fields/enums** beyond one in-contract addition: I wired
  `GET /api/cycles/` (listed in the contract mount map / screens) so Reviews, Analytics
  and Succession can offer cycle selectors. **Please confirm the live serializer fields**
  for a cycle (`id, name, start_date, end_date, status`) — that’s the only shape I assumed
  rather than read from a sample payload.
- Pagination is applied exactly where the contract paginates (reviews, JD list + requests,
  org search + positions, succession critical-roles + bench + nine-box, audit) via the
  `{count,next,previous,results}` envelope; everything else is a plain array.
- HITL is enforced everywhere a draft exists (reviews, JD, succession plans): draft badge +
  confidence + low-confidence (<0.70) warning, and the human approve/reject/publish gate is
  always present.
- 404 = “not yours / not there” (route back, never imply existence); 403 = role can’t;
  503 = calm “AI not configured” (manual path still works); 429 honours `Retry-After`.

## Decisions taken (safe defaults — no blockers)

- **Palette:** followed the V0 brief (Modern Blue / purple AI / gold premium) over the
  alternative hues suggested in `frontend_build.md`.
- **AI chat** was built in Phase 0 (it’s a cross-cutting shell affordance) rather than
  deferred, so the shell felt complete from the start.
- **Refresh token** is kept in `localStorage` (access token in memory). For a hardened
  deploy this should move to an http-only cookie issued by a backend-for-frontend — noted
  in `src/lib/auth/tokenStore.ts`.

There are **no `NEEDS_HARI_*` or `BLOCKER_*` files** — the contract + V0 brief covered
every decision.

---

## What remains / recommended next steps

1. **Wire to the live backend** (`VITE_USE_MOCKS=false`) and smoke-test each screen against
   real payloads; confirm the `/api/cycles/` shape and any field nuances vs the serializers.
2. **Visual click-through + polish pass** in a browser (use the role switcher). Tune
   spacing/density to taste; the design tokens are centralised in `src/styles/globals.css`
   and `tailwind.config.ts`.
3. **Build the mobile-web self-service surface** (separate build): own goals/actuals, own
   review, give 360 feedback, own career roadmap, chat. Shared session/user/API/feature
   layers are already reusable; nothing desktop-specific is baked into them.
4. **Nice-to-haves:** route-level code-splitting (vendor chunks already split), real export
   (view-inline / download-JSON) on org/jd/analytics, and a richer org-chart node-link
   visual if desired (current indented tree prioritises clarity).
5. **Tests:** add a few component/integration tests (Vitest + Testing Library) over the
   HITL and gating logic before QA handoff.

## Where things live

```
frontend/
  src/app/         router, guards, shell (sidebar/topbar), nav
  src/components/  shared primitives (DataTable, StatusBadge, Stepper, states, Hitl, …)
  src/components/ui/  shadcn-style primitives (button, dialog, table, …)
  src/features/<area>/  one folder per screen group (api hooks + pages + dialogs)
  src/lib/         api client + endpoints, auth, errors, format, enums, types, hooks
  src/mocks/       MSW handlers + fixtures (shapes from the contract)
  src/styles/      tokens + Tailwind layer
```

Working tree is clean apart from your own pre-existing edits (`V0_ADMIN_HUB_BRIEF.md`,
`frontend_build.md`), which I left untouched. All frontend work is committed on `main`,
not pushed.
