# FRONTEND_BUILD.md — Autonomous Admin Hub v1 Build (Talbotiq PMS)

> Hari is away. You are running unattended in AUTO MODE on **Claude Opus (do NOT switch models)**.
> Goal: produce **Version 1 of the Admin Hub** — a functional, clean, correctly-wired React frontend
> for the PMS — that BUILDS and RUNS when Hari returns. Read this whole file, then read the frontend
> contract (below), then begin at Phase 0. Quality bar: a modern, restrained, premium SaaS admin UI —
> not a template default.

---

## 0. OPERATING CONTRACT — read carefully, these rules override convenience

1. **This is the FRONTEND only.** Do NOT modify any backend Python. Read the backend contract as the
   source of truth; build a React app under `frontend/` in the repo root.
2. **Source of truth (read first, never invent against it):**
   `docs/frontend-contract/00_overview.md`, `01_screens.md`, `02_state_machines.md`,
   `03_data_dictionary.md`, `04_role_journeys.md`, `05_open_questions.md`, and
   `docs/FRONTEND_READINESS.md`. Every screen, field, enum value, endpoint, capability, and state
   comes from these. If a needed detail is missing, check the relevant `apps/<x>/serializers.py`.
   NEVER invent an endpoint, field, or enum value that isn't in the contract/serializers — if you
   think one is missing, write `NEEDS_HARI_<topic>.md` and use a clearly-labelled mock placeholder.
3. **Scope of v1 = the DESKTOP ADMIN HUB**, done well. Build the screen-groups in the phase order
   below. The responsive mobile-web self-service surface is a SEPARATE later build — do NOT build it
   now, but keep components responsive-tolerant so they don't break on a narrow viewport.
4. **Phase gate.** Finish a phase COMPLETELY before starting the next. A phase is "done" only when:
   `npm run build` succeeds, `tsc --noEmit` is clean (no type errors), the lint passes, every screen
   in the phase renders all its states against the mock layer, and it is committed locally. If a phase
   cannot reach a clean build after genuine effort, STOP — write `BLOCKER_<phase>.md`, leave prior
   phases committed and building, and do not proceed.
5. **Commit locally after each phase**, message `Frontend Phase N — <name> complete`. **Never git push.**
6. **If you need a human decision** (a genuine design or data ambiguity), write `NEEDS_HARI_<topic>.md`,
   choose the safe, sensible default, and CONTINUE. Don't stall.
7. **At the end** (all phases done, or you stop/block, or you sense you're low on capacity), write
   `FRONTEND_MORNING_REPORT.md` at repo root: phases completed, what each delivered, the commit list,
   every NEEDS_HARI/BLOCKER file, how to run it (`cd frontend && npm install && npm run dev`), what
   remains, and your recommended next step. Leave the working tree clean.
8. **Build quality, not just function.** Reusable components, consistent design tokens, no `any`-soup,
   accessible (labels, focus, keyboard, aria), real loading/empty/error states everywhere. A screen
   without its loading + empty + error states is NOT done.

---

## 1. STACK & PROJECT SETUP (Phase 0 establishes this)

Use the locked frontend stack (CLAUDE.md): **React + TypeScript + Tailwind + shadcn/ui.** Concretely:

- **Vite + React + TypeScript** (SPA). Strict TS (`"strict": true`, no implicit any).
- **Tailwind CSS** + **shadcn/ui** components (Radix under the hood) as the component foundation.
- **React Router** for routing + an auth guard + role-gated routes.
- **TanStack Query (React Query)** for ALL server state — caching, retries, and the "poll after action"
  behaviour the contract specifies (e.g. a review in AI_DRAFTING, a route tracker after a decision).
- **react-hook-form + zod** for forms and client-side validation that mirrors backend rules
  (e.g. KPI weights must sum to exactly 100.00; reject requires a reason; exactly one JD/Position target).
- **axios** (or a typed `fetch` wrapper) for the API client, with interceptors (auth header, 401→refresh→retry).
- **MSW (Mock Service Worker)** for a deterministic mock layer so the app renders standalone overnight.
- **lucide-react** icons, **sonner** (or shadcn toast) for notifications, **@tanstack/react-table** for data tables.

Project layout under `frontend/`:
```
src/
  app/            # router, providers, auth guard, layout shell
  components/ui/  # shadcn primitives
  components/     # shared app components (DataTable, StatusBadge, Stepper, EmptyState, ErrorState, Skeletons, ConfirmDialog, FeatureGate)
  features/<area>/# one folder per screen-group (api hooks, components, pages)
  lib/            # api client, auth, query client, types, enums, format utils
  mocks/          # MSW handlers + fixtures (shapes from the contract)
  styles/         # tailwind + design tokens
```

---

## 2. DESIGN SYSTEM — establish in Phase 0, everything inherits it (the quality anchor)

Build a deliberate, restrained, premium design language — modern SaaS admin quality (think the calm,
high-contrast, generous-whitespace feel of a top-tier dashboard, NOT a bootstrap default). Define it
ONCE as tokens and apply everywhere.

- **Color tokens** (CSS variables in `styles`, wired into Tailwind theme). A neutral, professional base
  with ONE confident accent. Suggested (adjust for polish, keep it restrained):
  - Background: near-white `#FAFAFA` light / surfaces pure white `#FFFFFF`; a dark sidebar `#101418`.
  - Text: `#0F172A` primary, `#64748B` muted.
  - Borders: `#E2E8F0`, hairline.
  - Accent (primary actions, active nav): a single confident hue — deep teal `#0E7C66` (matches the
    backend docs' palette) or indigo `#4F46E5`; pick one and use it consistently.
  - Semantic: success `#0E7C66`, warning `#E67E22`, danger `#C0392B`, info `#2471A3`.
  - Status badges map to the domain enums (DRAFT/PENDING/APPROVED/REJECTED/FINALIZED, OPEN/FILLED/CLOSED,
    RED/AMBER/GREEN coverage, ON_TRACK/AT_RISK/CRITICAL) — define a `StatusBadge` with a fixed color map.
- **Typography:** Inter (or system UI stack). Clear scale (e.g. 12/14/16/20/24/30). Strong weight
  contrast for hierarchy. Tabular numbers for tables/scores.
- **Spacing & layout:** generous whitespace, an 8px rhythm, max content widths, cards with hairline
  borders + very subtle shadow (no heavy drop shadows). Rounded-2xl on cards/dialogs.
- **App shell:** a fixed left sidebar (dark) with grouped nav + icons, a top bar (tenant name, global
  search where relevant, the AI chat launcher, user menu with role + logout), and a scrollable content
  area with a consistent page header (title, description, primary action) pattern.
- **Component standards (build these shared primitives in Phase 0 and reuse):** `DataTable` (sortable,
  paginated — handles the `{count,next,previous,results}` shape AND plain arrays), `StatusBadge`,
  `Stepper`/`Timeline` (for state machines), `EmptyState`, `ErrorState` (per status code),
  `LoadingSkeleton`, `ConfirmDialog`, `FeatureGate` (renders an upgrade prompt when a feature flag is
  off), `PageHeader`, `FormField` wrappers tied to RHF+zod, `Toast` usage conventions.
- **Micro-quality:** skeleton loaders (not spinners) for tables/cards; optimistic-feel via React Query;
  focus rings; disabled+reason tooltips on gated actions; consistent date formatting (UTC→browser-local
  for datetimes, plain dates as-is per open-question #2).
- **Accessibility:** labels on every input, keyboard-navigable dialogs/menus (shadcn/Radix gives this —
  don't break it), aria-live on toasts, sufficient contrast.

Build ONE flagship screen to a high finish in Phase 0/1 (the dashboard) so the bar is visibly set; then
hold every later screen to that same bar.

---

## 3. CROSS-CUTTING BEHAVIOUR (build in Phase 0, every screen obeys)

- **Auth:** login (`POST /api/auth/login`) → store the access token IN MEMORY + the refresh token; an
  axios interceptor attaches `Authorization: Bearer`, and on 401 calls `POST /api/auth/token/refresh`
  once then retries (logout on refresh failure). Handle the MFA challenge flow. NEVER send a tenant id —
  it's in the token. Logout calls `POST /api/auth/logout` and clears state. An auth guard redirects
  unauthenticated users to login.
- **RBAC-driven UI:** fetch the role (`/api/auth/me`) and the feature map (`GET /api/billing/my-features`)
  on login; drive the visible nav + the `FeatureGate` from them. A locked premium feature shows an
  **upgrade prompt**, never a raw error. Management-only areas (succession, analytics dept/calibration,
  audit console, admin, integrations) are hidden from roles that can't reach them. Succession is NEVER
  shown to an employee.
- **Error handling (one shared mapper):** 400 = inline validation; 401 = refresh-then-login; 403 =
  "you don't have access" (role); 404 = "not found / not yours" (the contract's 404 = out-of-scope rule);
  409 = "that action isn't allowed in the current state" (illegal transition) — refresh the entity;
  422 = domain validation, show `{detail, code}` inline (e.g. HITL_APPROVAL_REQUIRED,
  REJECTION_REASON_REQUIRED, REPORTING_CYCLE, INVALID_JD_INPUT); 429 = rate/budget — show the
  `Retry-After` + `upgrade_hint`; 503 = "AI not configured yet" friendly state on AI surfaces.
- **HITL principle in the UI:** reviews, feedback summaries, succession plans, JD drafts, and AI outputs
  are PENDING_HUMAN_REVIEW until a human approves. ALWAYS render review/approve/reject affordances and a
  clear "pending review / draft — not final" indicator; never present a draft as final.
- **Async/polling:** no websockets. After an action that triggers async work (AI draft, route decision,
  summary generation), poll/refetch the entity until it settles (React Query refetch interval, stopped
  on terminal state).
- **Mock layer:** MSW handlers return fixtures whose SHAPE matches the contract exactly (real field
  names, real enum VALUES, the pagination shape). A single env flag (`VITE_USE_MOCKS`) switches between
  MSW and the live API client (same typed functions). Build everything against MSW so v1 renders
  standalone; if the docker backend is up you MAY smoke-test live, but do not depend on it.

---

## 4. PHASES — build in this order, each gated (Section 0 rule 4)

> Each phase: list the screens from `01_screens.md`, build them with all states, wire to the typed API
> hooks (MSW-backed), hold the design bar, then build-clean + typecheck + lint + commit before the next.

### Phase 0 — Foundation (do this COMPLETELY; it is the quality anchor)
Scaffold the Vite+TS+Tailwind+shadcn project under `frontend/`. Install the stack (Section 1). Build:
the design tokens + Tailwind theme (Section 2), the app shell (sidebar + topbar + content), routing +
auth guard + role-gated routes, the auth flow (login + MFA + refresh interceptor + logout), the
`/api/auth/me` + `/api/billing/my-features` bootstrap into an Auth/Feature context, the shared
component primitives (Section 2), the error mapper + toast conventions (Section 3), and the MSW mock
layer + typed API client skeleton with enums/types generated from `03_data_dictionary.md`.
**Gate:** the app builds, you can log in (against MSW), the shell renders, and one styled placeholder
page proves the design system. Commit `Frontend Phase 0 — foundation & design system complete`.

### Phase 1 — Dashboard + KPI nudges tile (build the flagship screen to a high finish)
A role-aware Admin/HRBP/Manager landing dashboard, composed client-side (there is no `/dashboard`
endpoint — per open-question #9): summary cards (counts/links pulled from the feature endpoints +
the approvals inbox count), and a **KPI nudges tile** from `GET /api/ai/nudges` (manager/HRBP scope;
hidden/empty for roles without it). Make this screen genuinely polished — it sets the bar.
**Gate + commit** `Frontend Phase 1 — dashboard complete`.

### Phase 2 — Admin core: users/roles, tenant config, entitlements + upgrade switch
- Users & roles (`/api/admin/users` + role/deactivate/reactivate/reporting-line, + display_name):
  a `DataTable` of users with role, status, manager; create-user dialog; edit role; activate/deactivate;
  set reporting line (handle the 422 REPORTING_CYCLE). Show `display_name` (fallback to email).
- Tenant config (`GET,PUT /api/admin/tenant-config`).
- Entitlements + billing (`GET /api/billing/entitlement`, `feature-flags`, `upgrade-prompt`, `POST
  /upgrade`, `PATCH /seats`): show the current packs + seats, the locked-vs-unlocked feature map, and
  an **upgrade modal** (the commercial showpiece — STARTER → FULL_AI flips the flags live). 
**Gate + commit** `Frontend Phase 2 — admin & entitlements complete`.

### Phase 3 — Approvals: workflow designer, inbox, route tracker
- Workflow designer (`/api/approvals/` workflow CRUD + activate/deactivate): create a workflow with
  ordered steps (role/named approver, sequential/parallel) — per open-question #3 this is
  create/activate/deactivate + "re-create to edit steps", not a live drag editor.
- Approver inbox (the steps awaiting the user) with approve/reject (reject requires a reason → 422 guard).
- Route tracker: a `Stepper`/`Timeline` rendering the approval route state machine
  (from `02_state_machines.md`) — sequential and parallel.
**Gate + commit** `Frontend Phase 3 — approvals complete`.

### Phase 4 — Reviews (the HITL signature flow)
Review list (scoped, paginated), the review editor, and the **review state-machine stepper**
(DRAFT → … → FINALIZED from `02_state_machines.md`) with the transition actions (start-edit, submit,
approve, reject, finalize, request-ai-draft) wired to their endpoints, each guarded by the right state
+ the error mapper (HITL_APPROVAL_REQUIRED 422, illegal-transition 409). The AI-draft action shows the
503 "AI not configured" state gracefully. Render the PENDING_HUMAN_REVIEW / draft-not-final indicators
prominently — this is the product's signature safety feature.
**Gate + commit** `Frontend Phase 4 — reviews complete`.

### Phase 5 — Org chart
The org tree (`GET /api/org/tree`) as a clean, navigable hierarchy with headcount + vacancy rollups per
node; person card (`/people/<id>`, 404 out-of-scope); vacancies list; position management
(create/fill/close/link-jd); reassign reporting line (cycle → 422). A readable tree visualisation
(indented tree or a simple node-link layout — prioritise clarity over fancy graphics).
**Gate + commit** `Frontend Phase 5 — org chart complete`.

### Phase 6 — Succession (management-only) + Analytics
- Succession (HIDE from employees entirely): dashboard, the **9-box grid** (a 3×3 calibration grid —
  visually distinctive), bench candidates + readiness, plan review/publish (HITL).
- Analytics: individual trend, department analytics WITH the **min-cohort suppression UI** (a <5-person
  cohort shows aggregate-only + a clear "suppressed for privacy" notice), and the calibration grid.
**Gate + commit** `Frontend Phase 6 — succession & analytics complete`.

### Phase 7 — JD library, audit console, integrations, AI chat (as capacity allows)
- JD library + editor + version history + lifecycle (save-draft/submit/approve/revise/archive), with the
  generate-503 seam state.
- Audit console (`GET /api/audit/logs`): read-only, filterable, paginated table.
- Integrations config (`/api/integrations/`, Admin): JIRA/SLACK enable + config; NEVER show a secret
  value (only the env-var `secret_ref` name).
- AI chat panel (`POST /api/ai/chat`): a slide-over chat launched from the topbar; read-only answers,
  503 when no provider, 429 on budget, RBAC-bound (the UI just renders what comes back).
**Gate + commit** `Frontend Phase 7 — JD, audit, integrations, chat complete`.

> If you run low on capacity, STOP after the current phase (committed + building) and write the morning
> report. A v1 with Phases 0–4 done WELL beats all 8 phases done shallowly.

---

## 5. PER-PHASE VALIDATION CHECKLIST (run before every phase commit)
- [ ] `npm run build` succeeds; `tsc --noEmit` clean; lint passes.
- [ ] Every screen renders against MSW with: loading (skeleton), empty, populated, and error-by-code states.
- [ ] Actions wired to the correct endpoint + method; the right capability gates the UI; locked features
      show the upgrade prompt (not an error); management-only screens hidden from disallowed roles.
- [ ] Forms validate client-side to match backend rules (weights = 100.00, reason required, one target, etc.)
      and surface 422 `{detail, code}` inline.
- [ ] HITL/draft indicators present on review/summary/plan/AI surfaces; no draft shown as final.
- [ ] Pagination handled where the endpoint paginates; plain arrays where it doesn't.
- [ ] Design tokens used (no ad-hoc colors); responsive-tolerant; keyboard + focus work.
- [ ] No invented endpoints/fields/enums — all trace to the contract/serializers.
- [ ] Committed locally with the standard message; NOT pushed; working tree clean.

---

## END OF RUN
Write `FRONTEND_MORNING_REPORT.md`: phases done, screens delivered, commit list, NEEDS_HARI/BLOCKER
files, exact run instructions (`cd frontend && npm install && npm run dev`, the `VITE_USE_MOCKS` flag,
how to point it at the live backend later), what remains, and recommended next steps (wire to live API,
visual polish pass, then the mobile-web self-service surface). Leave everything committed locally, not
pushed. Build a v1 that opens, navigates, and demos — that is the goal.
