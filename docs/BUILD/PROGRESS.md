# Overnight build — progress log

Branch: `hari/prod-hardening`
Started: 2026-08-16
Plan: `OVERNIGHT_BUILD_PROMPT.md` · Audit: `docs/AUDIT/REPO_FACTS.md`

This log is the resume point. Every completed item is appended below with its
status, the files it touched, how it was verified, and what it still needs from a
human. Items marked DONE are skipped on resume.

---

## DECISIONS TAKEN

Judgement calls made under R9 (no questions asked mid-run). Review these.

---

## ITEM LOG

## A0 — Reproduce and inventory mobile bugs
Status: DONE
Changed: docs/BUILD/MOBILE_AUDIT.md, docs/BUILD/PROGRESS.md
Verified by: real headless Chromium walk of the production SPA build (nginx
`:8090`) against the real Django API, tenant `acme`, all four roles, at 390×844
and 360×800. 26 route/viewport combinations measured. Frontend baseline green
(`npx vitest run` → 28 files / 150 tests passed).
Needs from human: nothing.

Key findings (full detail in MOBILE_AUDIT.md):
- **P0** a `Topbar` render error unmounts the whole app — `ErrorBoundary` wraps
  only `<Outlet/>`, so `#root` empties to a white screen with no recovery.
- **P1** the topbar right cluster (notifications, Ask AI, account menu → the only
  Sign out) renders at `right:487` on a 390px screen: 97px off-screen and
  untappable on every route for every role. Cause: flexbox `min-width:auto` on
  the search button.
- **P1** `/settings` overflows by 578–608px; `/reviews` `/admin/users` `/audit`
  `/jd` each render a table wider than the viewport.
- **P2** hamburger is 16×32; 24 more shell controls under 44×44; 9 inputs under
  16px on `/settings` (iOS zoom); greeting uses browser tz, not `User.timezone`,
  which `/api/auth/me` does not even return.
- Sidebar is already closed-on-mount and closes on route change; missing focus
  trap, Escape-to-close, and desktop preference persistence.
- No broken image assets — the "AI icons missing" report is almost certainly the
  off-screen Ask AI button.

## A1 — Viewport and base layout (+ P0 shell-crash fix)
Status: DONE
Changed: frontend/index.html, frontend/src/styles/globals.css,
frontend/src/app/shell/AppLayout.tsx, frontend/src/app/shell/Topbar.tsx,
.gitignore
Verified by: `npx tsc --noEmit` clean; `npx vitest run` 28 files / 150 tests
pass; production image rebuilt and re-walked at 390×844 against the real API —
dashboard off-screen overflow **487 → 0**, sub-44px targets on `/` 10 → 5, and
the topbar no longer appears as an offender on any route.
Needs from human: nothing.

- Topbar: `min-w-0` on the search button (flexbox `min-width:auto` was the root
  cause), `ml-auto shrink-0` on the right cluster, icon-only search below `sm`.
  Notifications / Ask AI / account menu are now on-screen and tappable.
- Shell-level `ErrorBoundary` added around `ShellFrame` so a Topbar/Sidebar throw
  degrades instead of emptying `#root`.
- `viewport-fit=cover` + `pt-safe/pb-safe/px-safe/pb-safe-4` utilities.
- `html, body, #root` height 100% + `overflow-x: hidden`; `.scroll-x` escape
  hatch for genuinely wide content.
- `h-[100dvh]` for the shell; content padding `px-4 py-6` below `sm`.
- Shell tap targets raised to 44×44 (hamburger was 16×32).
- `.gitignore`: `!docs/BUILD/` — the Python `build/` rule was swallowing
  `docs/BUILD/` on case-insensitive macOS, so the build log could not be
  committed.

## A2 — Sidebar is a drawer on mobile, closed by default
Status: DONE
Changed: frontend/src/app/shell/AppLayout.tsx, frontend/src/app/shell/Sidebar.tsx,
frontend/src/app/shell/Topbar.tsx, frontend/src/app/shell/AppLayout.test.tsx
Verified by: 8 new vitest cases (158 total, up from 150); `tsc --noEmit` clean;
live browser check at 390×844 — closed on mount, `role=dialog`/`aria-modal` on
open, focus lands on the first nav item, Escape closes, `localStorage` empty
after a mobile toggle.
Needs from human: nothing.

- Added: focus trap + focus restore, Escape to close, modal ARIA (drawer only),
  `aria-expanded` on the hamburger.
- Breakpoint moved `lg` (1024) → `md` (768) per spec; one `DESKTOP_QUERY`
  constant now drives the CSS variants, the backdrop and the JS check.
- Viewport class is live via a `matchMedia` change listener, so rotation
  re-applies the layout instead of waiting for the next navigation.
- Desktop collapse preference persists; a mobile open state never does.

## A3 — Post-login paint race
Status: DONE (symptom did not reproduce; a real adjacent defect was fixed)
Changed: frontend/src/app/guards.tsx, frontend/src/features/auth/LoginPage.tsx,
SignupPage.tsx, AcceptInvitePage.tsx, PasswordResetPages.tsx
Verified by: XHR delayed 900ms in-page (CDP throttling is blocked by the browse
allowlist) and the DOM sampled every 100ms across the login transition —
`/login` → chromed dashboard with skeletons at 2000ms → data at 3100ms. No
blank, unstyled or partial frame. `tsc` clean; vitest 158 pass.
Needs from human: nothing.

- The A3 gating is already correct in the existing code: `completeLogin()` awaits
  `/me` + `/my-features` before resolving, and `navigate()` runs after that
  await, so the shell never renders without a resolved profile. `StatCard`
  already takes `loading` and every cockpit passes its query's `isLoading`.
- The reported "half-built screen" is almost certainly A1 (topbar controls 97px
  off-screen, sidebar covering content), now fixed.
- Real defect fixed here: all four auth screens and `FullScreenLoader` used
  `h-screen`/`min-h-screen`. On mobile `100vh` counts collapsible browser chrome,
  so the centred loader sat low and the login card scrolled needlessly. Now
  `100dvh` (vh retained as fallback) plus safe-area padding.

## A4 — Time-aware greeting in the user's timezone
Status: DONE
Changed: apps/identity/views.py, apps/identity/tests/test_tokens_session.py,
shared/src/types.ts, frontend/src/lib/greeting.ts (new),
frontend/src/lib/greeting.test.ts (new),
frontend/src/features/dashboard/DashboardPage.tsx
Verified by: 9 new frontend tests against a pinned clock (167 total) + 2 new
backend tests (`pytest apps/identity/tests/test_tokens_session.py` → 9 passed);
`tsc --noEmit` clean.
Needs from human: nothing.

- `/api/auth/me` now returns `timezone`, defaulted to `"UTC"` server-side (never
  null). Without it the client had no way to be correct.
- Bands: 05:00–11:59 morning, 12:00–16:59 afternoon, 17:00–20:59 evening,
  21:00–04:59 night (the night band did not exist before).
- Hour derived via `Intl.DateTimeFormat` in the target zone, so DST is handled by
  the platform tz database; an unknown zone falls back rather than throwing.
- Re-evaluates on `visibilitychange` + `focus`, so an overnight session is
  correct in the morning. The date label renders in the same zone.
- The exact reported failure is now a test: `2026-08-17T18:35:00Z` → "Good night"
  for `Asia/Kolkata`, "Good evening" for `UTC`.

**Follow-up for the human:** `mobile/src/app/(tabs)/index.tsx` has the identical
three-band device-clock greeting. Mobile is not in the deployed stack and has no
test harness, so it was left unchanged rather than edited blind.

## A5 — Missing AI feature icons
Status: DONE (root cause was A1; fallback added)
Changed: frontend/src/brand.tsx
Verified by: live check at 390×844 — Ask AI button now `right:344`, 44×44,
`onScreen:true`, `svg:true`; every brand asset returns 200 from nginx and
`document.images` reports `naturalWidth > 0`. `tsc` clean; 167 tests pass.
Needs from human: nothing.

- Ruled out all three candidate causes: lucide imports fine (11–24 SVGs/route),
  no asset 404s, no responsive class hides icons.
- Actual cause: the Ask AI control sat at `right:437` on a 390px viewport, past
  the edge and clipped by the shell's `overflow-hidden`. A1 fixed it.
- Fallback added: `BrandMark`/`BrandWordmark` now degrade to the inline lucide
  mark via `onError` instead of rendering an empty box when a PNG 404s.

## A6 — Tables and data-dense views
Status: DONE
Changed: frontend/src/components/DataTable.tsx,
frontend/src/lib/hooks/useIsDesktop.ts (new),
frontend/src/app/shell/AppLayout.tsx, and the `mobilePrimary` wiring on
AuditPage, UsersPage, ReviewsListPage, OrgPage, JdListPage (×2 tables)
Verified by: live walk at 390×844 — off-screen content on `/admin/users`,
`/audit`, `/reviews`, `/jd` went **602/659/607/570 → 0**, each renders **0
tables**, and `/audit` shows 50 cards under an "audit entry list" label with the
Details disclosure. `tsc` clean; 167 tests pass.
Needs from human: nothing.

- Finding: tables were never breaking the page — the `Table` primitive already
  wraps in `overflow-auto`, so they scrolled inside their own box. The real cost
  was reading a record one horizontal swipe at a time with no scroll affordance.
- One seam: every table screen uses the shared `DataTable`, so the card layout
  lives there rather than in six screens.
- Cards carry per-value labels, keyboard-operable row activation, and a
  stop-propagation guard so the Details disclosure cannot trigger navigation.
- `goals`, `feedback`, `approvals` from the A6 list are **not** table-based
  (measured `tableCount: 0`) — they already render as cards/lists, nothing to do.

## A7 — Forms, modals and dialogs on small screens
Status: DONE
Changed: frontend/src/components/ui/{input,textarea,select,dialog,sheet}.tsx,
frontend/src/features/auth/{LoginPage,SignupPage,PasswordResetPages}.tsx,
frontend/src/features/settings/SettingsPage.tsx,
frontend/src/features/admin/{UsersPage,BillingPage}.tsx,
frontend/src/features/approvals/WorkflowDialog.tsx
Verified by: live walk at 390×844 — `/settings` off-screen **570 → 0** and
sub-16px inputs **9 → 2** (both checkboxes, which don't zoom); `/checkins` 4→0,
`/audit` 3→0, `/admin/users` 1→0, `/admin/billing` 1→0. `tsc` clean; 167 pass.
Needs from human: nothing.

- **Gotcha worth remembering:** this project's Tailwind scale defines `base` as
  0.875rem (**14px**), so the obvious `text-base` fix still tripped iOS zoom.
  Controls use a literal `text-[16px]` below `sm` — 16 is a platform threshold,
  not a design token. Only caught by measuring computed style.
- Dialogs → full-screen sheets below `md` (`inset-0`, `100dvh`, own scroll,
  safe-area padding); close button 16px glyph → 44×44.
- Side sheets full-bleed below `sm` (were `w-3/4` = 292px on a 390px screen).
- Select dropdowns capped at `min(24rem, 60dvh)` with own scroll.
- `inputMode`/`autoCapitalize`/`autoCorrect` on email, `tel` on phone, `numeric`
  on billing + workflow number fields.
- Real bug fixed: the `/settings` "This device" badge sat inside a truncating
  paragraph, so it rendered ~570px off-screen and was clipped — the label
  identifying your own session was invisible on a phone.

## A8 — Charts
Status: DONE
Changed: frontend/src/components/TrendChart.tsx
Verified by: live check at 390×844 — analytics chart renders 324×220 with 4 x
ticks and 4 y ticks, none colliding. `tsc` clean; 167 tests pass.
Needs from human: nothing.

- Charts were already `ResponsiveContainer`-based and measured 308×220 — no
  slivers, no overflow. This was density tuning, not a rescue.
- Below `md`: `interval="preserveStartEnd"`, 32px `minTickGap`, 10px ticks,
  y-gutter 36→28px, y capped at 4 ticks.
- Height floored at 180px so a small `height` prop or a collapsing flex parent
  cannot produce an unreadable sliver.

## A9 — Touch targets and spacing
Status: DONE
Changed: frontend/src/styles/globals.css (`.tap-target`),
frontend/src/components/ui/{button,tabs,checkbox}.tsx,
frontend/src/features/{recognition,goals,dashboard,checkins,settings,feedback}/*,
frontend/src/app/shell/AppLayout.tsx
Verified by: live sweep of 8 routes at 390×844 — **under-sized controls 393 → 0**,
off-screen content 0. `tsc` clean; 167 tests pass.
Needs from human: nothing.

- `.tap-target` puts a 44×44 hit area on an invisible `::after` so the control's
  visual size — and the desktop layout — is unchanged. Sizing 393 chips and icons
  to 44px outright would have wrecked the dense enterprise UI.
- Gated `(max-width: 767.98px), (pointer: coarse)`: `coarse` alone misses touch
  devices reporting a fine pointer; width alone misses large tablets. Kept off
  desktop so adjacent controls don't steal each other's clicks.
- Applied at the primitives (Button, Tabs, Checkbox) so unaudited screens benefit
  too.
- The measurement harness now distinguishes "small rect but 44px hit area" from
  genuinely small — `getBoundingClientRect` cannot see a pseudo-element, so it
  was reporting fixed controls as broken.

## A10 — Regression tests
Status: DONE
Changed: frontend/src/components/DataTable.test.tsx (new),
frontend/src/test/a11y/mobile-a11y.test.tsx (new),
frontend/src/app/shell/AppLayout.test.tsx, frontend/src/components/DataTable.tsx
Verified by: `npx vitest run` → 31 files / **181 tests** (150 at the A0
baseline); `tsc --noEmit` clean; all 18 axe checks green.
Needs from human: nothing.

- **The mobile axe pass caught a real fault I shipped in A6**: `nested-interactive`
  (serious) — the card had `role="button"` and contained the `<details>`
  disclosure, which a screen reader cannot address. Tapping worked, so nothing
  else would have caught it. Fixed by making the lead field a real `<button>`
  (the accessible, keyboard-operable action) and dropping the role from the card,
  which keeps pointer convenience without nesting.
- Existing a11y suite only ever ran at desktop width (jsdom's absent `matchMedia`
  reads as desktop), so it never saw the drawer or the card list.
- On "no route renders with horizontal overflow at 360px": jsdom has no layout
  engine, so that assertion would be theatre there. Real geometry is measured in
  a headless browser (A11); vitest locks the structure it depends on
  (`overflow-x-hidden` on the scroll region, `min-w-0` on the content column).
  The test file states this rather than implying wider coverage.

## A11 — Verify
Status: DONE
Changed: frontend/src/components/DataTable.tsx, frontend/src/components/ui/tabs.tsx,
frontend/src/features/dashboard/cockpit.tsx, frontend/src/features/goals/GoalsPage.tsx,
frontend/src/features/org/{OrgTreeView,LazyOrgTreeView}.tsx,
frontend/src/features/help/GettingStartedPage.tsx, docs/BUILD/MOBILE_AUDIT.md
Verified by: rebuilt production image, re-ran the full A0 harness — 26
route/viewport combinations, 4 roles, 390×844 and 360×800.
Needs from human: nothing.

**Totals: off-screen 4796px → 24px · under-sized targets 1249 → 13 · wide tables
6 → 0 · sub-16px inputs 29 → 2.**

Caught on the re-walk (i.e. things the first pass missed or caused):
- `/reviews` under-sized targets had gone **up** 15 → 50: the A10 lead button is
  full-width but 24px tall and needed the hit area too.
- Tab strip pushed `/feedback` 9px over — now scrolls itself.
- Employee dashboard still had 7 sub-16px inputs: call sites pass
  `className="text-xs"` and tailwind-merge lets the caller win over the
  component. Those sites now opt into 16px below `sm` explicitly.
- Org tree chevrons (20×20), org person rows, getting-started links.

Four documented residuals (in MOBILE_AUDIT.md with reasons): `/admin/users` 19px
at 360 only; `/feedback` tab strip 5px before it scrolls; 2 checkboxes under 16px
(iOS doesn't zoom for those); 13 inline prose links where a 44px box would
overlap the neighbouring line.

---

# PHASE B

## B1 — Per-tenant AI configuration, encrypted at rest
Status: DONE
Changed: apps/ai/{crypto,tenant_config,models,providers,gateway}.py,
apps/ai/{gemini_provider,openai_provider,groq}.py, apps/ai/migrations/0005_*,
apps/ai/tests/test_tenant_ai_config.py, config/settings/base.py, .env.example,
docs/BUILD/ENV_REFERENCE.md
Verified by: 19 new tests; `pytest apps/ai apps/administration` → 590 passed.
Needs from human: `FIELD_ENCRYPTION_KEY` (generate per environment) before
per-tenant keys can be stored. Unset is safe — see ENV_REFERENCE.md.

- New `ai.TenantAIConfig` model (not a corner of `TenantConfig.settings`, which is
  returned and replaced wholesale by the admin API and would leak/clobber the key).
- Fernet, authenticated, with comma-separated key rotation.
- **Fails closed on write** (no key → refuse, never plaintext), **degrades on
  read** (undecryptable → fall back to the environment key, don't 500).
- Resolution: tenant key → environment key → not configured.
- Provider stored as a **slug**, mapped to a dotted path in code — an admin form
  accepting an importable path would be an RCE shape.
- The decrypted value never leaves `apps/ai/tenant_config`.

## B4 — Invert the AI switch failure mode
Status: DONE
Changed: apps/ai/tenant_switch.py, apps/ai/tests/test_ai_switch_fails_closed.py
Verified by: 5 tests including an exploding manager asserting `False`.
Needs from human: nothing.

- Was fail-**open**: an unreadable setting meant AI stayed on. Since we tell
  customers this switch is how they stop employee data reaching a model provider,
  "we couldn't read your preference so we sent it anyway" is never acceptable.
- Now fail-**closed**; default stays ON for a tenant that never set it (absent ≠
  off). Reads the new model, falling back to the legacy
  `TenantConfig.settings["ai_enabled"]` so pre-B1 choices survive.

## B5 — Extend the PII scrubber
Status: DONE
Changed: apps/ai/pii.py, apps/ai/gateway.py, apps/ai/tests/test_pii_scrub.py,
config/settings/base.py
Verified by: 28 new tests; `pytest apps/ai apps/feedback apps/reviews` → 728
passed.
Needs from human: decide whether `PII_SCRUB_NAMES` should be on for this
deployment (default off — see below).

- Adds phone numbers (7–15 digits, bounded at both ends) and **labelled**
  employee/staff/payroll ids.
- The digit bound is the important part: an unbounded number pattern eats
  "attainment 87.5% against 120" and "cohort size 42, T-score 61.3" — the exact
  values a review is built from. Mangling those produces confidently wrong AI
  output, which is worse than redacting too little. 5 tests guard this.
- Employee ids only in labelled form; a bare token is indistinguishable from a
  goal title or KPI unit. The label survives so the model knows an id was there.
- **Names stay unredacted by default** — `evidence.py` passes the subject's first
  name deliberately. `PII_SCRUB_NAMES=True` swaps them for role tokens.
- The docstring now states plainly what is *not* redacted and why, which is what
  a customer asking "what leaves our tenant?" actually needs.

## B2 — Admin UI for AI configuration
Status: DONE
Changed: apps/ai/admin_views.py (new), apps/ai/urls.py,
apps/ai/tests/test_admin_ai_config.py (new), shared/src/api/endpoints.ts,
frontend/src/features/admin/AISettingsPage.tsx (new),
frontend/src/app/{router.tsx,nav.ts,nav.test.ts}
Verified by: 18 backend tests (RBAC ×4 roles, no key in any response or audit
row, 409 path, rotation audit, PATCH-doesn't-clobber, 4 test-connection states,
cross-tenant invisibility); frontend `tsc` clean + 181 tests.
Needs from human: nothing to build; `FIELD_ENCRYPTION_KEY` to actually store a
key (the UI explains this state rather than failing).

- `GET/PATCH /api/ai/admin/config` + `POST /api/ai/admin/test-connection`, gated
  on the existing `MANAGE_TENANT_CONFIG` — no new authority.
- **No endpoint returns the key.** Reads give a last-4 hint only; rotating means
  typing a new one.
- PATCH not PUT, so "turn AI off" cannot arrive as a document that drops the key.
  There is a test for that specific regression.
- Failures are specific: 409 naming `FIELD_ENCRYPTION_KEY`; 400 listing allowed
  providers; test-connection distinguishes not-configured / switched-off /
  budget-exhausted / provider-rejected.
- Test-connection runs through the normal gateway so budget, ceiling and PII
  scrubbing all apply — testing a path that doesn't exist in production would be
  worse than not testing.
- Key set/rotate/clear/switch/test are all audited with actor + action; metadata
  carries `key_last4` only.

## B3 — Honest "AI unavailable" states
Status: DONE
Changed: apps/ai/http.py (new), apps/ai/views.py (12 response sites),
apps/ai/tests/test_ai_unavailable_states.py (new),
frontend/src/components/AIUnavailable.tsx (new),
frontend/src/features/chat/ChatPanel.tsx
Verified by: 7 new backend tests incl. an end-to-end sweep of 5 AI endpoints;
`pytest apps/ai` → 612 passed; frontend `tsc` clean + 181 tests.
Needs from human: nothing.

- Four codes: `ai_disabled`, `ai_not_configured`, `ai_budget_exhausted`,
  `ai_provider_error` — previously all flattened into one 503 with prose like
  "chat unavailable: PROVIDER_ERROR".
- Budget exhaustion is **429, not 503**: a 503 tells monitoring the service is
  broken when it is behaving exactly as configured.
- "Switched off" vs "never configured" resolved by asking the switch rather than
  threading it through every agent call site.
- One `AIUnavailable` component renders all four; the admin-only remediation line
  is shown **only to admins** — telling an employee to change a setting they
  can't reach is worse than saying nothing.

## B6 — Per-tenant AI spend visibility
Status: DONE
Changed: shared/src/api/endpoints.ts,
frontend/src/features/admin/AISettingsPage.tsx
Verified by: frontend `tsc` clean + 181 tests. Backend endpoint pre-existed and
is covered by the billing suite.
Needs from human: nothing.

- `GET /api/billing/ai-usage` already existed and was well built, but **nothing
  called it** — an admin still needed shell access to see spend.
- Now on the admin AI page: calls / tokens / estimated cost / budget count over
  7·30·90 days, a per-agent breakdown showing usage against each cap, and the
  unpriced-models warning surfaced rather than folded in as zero (a silent zero
  reads as "this was free"). The estimate disclaimer travels with the figures.

---

# PHASE C

## C1 — Continuous integration
Status: DONE
Changed: .github/workflows/ci.yml (new), docs/BUILD/CI.md (new)
Verified by: YAML parsed and asserted (2 jobs, 10 steps, correct job name,
`continue-on-error` on the audit job).
Needs from human: **enable branch protection in the GitHub UI** — exact click
path in `docs/BUILD/CI.md`. The workflow proves tests pass; it cannot stop a
merge when they don't.

- Gate job: MySQL 8.0 + Redis 7 services, both requirements files, `pytest`, then
  `npm ci` + `test` + `build`.
- Two things the service container can't express are explicit steps: the
  `test\_%` grant, and `log_bin_trust_function_creators=1` — without which the
  `audit_log` triggers can't be created and `audit/0002` fails. **CI now proves
  on every push that audit immutability can be installed.**
- Audit job (pip-audit, npm audit) is advisory, not a gate. Expect it red
  initially: Django 4.2 is past its security window (PHASE G).

## C2 — Non-root containers
Status: DONE
Changed: Dockerfile, docker-compose.prod.yml
Verified by: built the image and checked it — `id` → uid 10001; `touch
/app/manage.py` → Permission denied; media + staticfiles writable; gunicorn
"Listening at 0.0.0.0:8000"; `pytest apps/tenancy` → 14 passed.
Needs from human: nothing.

- `appuser` UID/GID 10001 (high, so it can't collide with a host user on a bind
  mount). Only `/app/media` and `/app/staticfiles` are chowned — **the source
  tree stays root-owned so the runtime can't modify the code it's executing.**
- `security_opt: no-new-privileges` + `cap_drop: ALL` on web, worker, beat,
  migrate.
- `read_only` deliberately **not** set, with the reason written in the file
  (gunicorn's /dev/shm heartbeat, MEDIA_ROOT writes) so the omission doesn't read
  as an oversight.

## C3 — Tenant suspension terminates sessions
Status: DONE
Changed: apps/tenancy/{status,signals,apps,middleware}.py,
apps/tenancy/tests/test_suspension_terminates_sessions.py, apps/identity/views.py
Verified by: 11 new tests; **full backend suite 1922 passed**.
Needs from human: nothing.

- Was checked at login only, so suspending a tenant left access tokens working
  for 15 min and refresh rotating for **7 days**.
- Now refused in `TenantMiddleware` (401 `tenant_inactive`) and in the refresh
  view — refresh is the one endpoint the middleware can't cover, since it's
  reached with an expired access token.
- Cached + `post_save`-invalidated: **measured 0 queries** across 5 checks, and a
  bogus tenant id caches its negative so it can't amplify into a query per
  request.
- Fails closed; message blames the workspace, not the person.

## C4 — Config defaults that break in production
Status: DONE
Changed: config/settings/prod.py, docker-compose.prod.yml, docs/archive/ (new),
deleted vercel.json + render.yaml, moved railway*.json
Verified by: prod settings raise `ImproperlyConfigured` without `PUBLIC_APP_URL`
and load cleanly with it (both checked in-container).
Needs from human: set `PUBLIC_APP_URL` at deploy (compose now refuses to start
without it).

- `PUBLIC_APP_URL` required in prod. Its base default `http://localhost:8080`
  doesn't error — it **sends**, so every recovery email would carry a dead link.
- `vercel.json` deleted (hardcoded a production API hostname, so any preview hit
  prod); `render.yaml` deleted (ran AI jobs inline via `CELERY_TASK_ALWAYS_EAGER`);
  `railway*.json` archived. Four deployment stories → one.

## C6 — Verify audit triggers after every migration
Status: DONE
Changed: apps/audit/management/commands/verify_audit_triggers.py (new),
apps/audit/tests/test_verify_triggers_command.py (new),
apps/core/management/commands/deploy_migrate.py
Verified by: runs green against the live DB; 3 tests including **dropping a
trigger and asserting the command fails**. `pytest apps/audit` → 32 passed.
Needs from human: nothing.

- On managed MySQL the migration can report success while the triggers were never
  created — silently dropping the only layer of audit immutability that survives
  someone with a DB client. `deploy_migrate` now fails the deploy instead.
- Error names the missing trigger and gives both remedies; a non-MySQL backend is
  an error, not a pass, because reporting OK there would be a lie.

## C7 — Invite-only signup
Status: DONE
Changed: apps/identity/{signup_views,urls}.py, config/settings/base.py,
apps/identity/tests/{test_signup_mode.py (new),test_signup.py},
shared/src/api/endpoints.ts, frontend/src/lib/hooks/usePublicConfig.ts (new),
frontend/src/features/auth/{LoginPage,SignupPage}.tsx
Verified by: 10 new tests; `pytest apps/identity` → 86 passed; frontend 181 pass.
Needs from human: set `SIGNUP_MODE=open` once billing works.

- Default `invite_only`. Signing up today would create a real workspace on a plan
  no invoice can follow (C8).
- New `GET /api/auth/public-config` so flipping the env var doesn't also require a
  frontend rebuild. Tiny by design, with a test pinning the exact key set.
- **Invitations unaffected in both modes** — explicitly tested, as it's the thing
  most likely to break here by accident.
- Client defaults to closed while loading/erroring.

## C8 — Payments honesty
Status: DONE
Changed: apps/billing/payments/providers.py, apps/billing/views.py,
apps/billing/tests/test_payments.py,
frontend/src/features/admin/BillingPage.tsx, frontend/src/mocks/handlers.ts
Verified by: `pytest apps/billing` → 108 passed; frontend 181 pass.
Needs from human: nothing (wiring a real SDK is a future decision; instructions
are kept in each docstring).

- `create_checkout` returned a plausible `cs_test_...` id and a checkout URL that
  went nowhere, with **no signal that no money moved**. Now `NotImplementedError`
  → 501 `payments_not_implemented`.
- The signature-verified webhook side is untouched — it's real and correct.
- UI: paid-plan buttons replaced with "Contact us to move to this plan".
- Two existing tests guarded a property that still holds (a client can't
  self-activate); they now assert it via the 501. Added one asserting the response
  carries no `session_id`/`checkout_url`.


## C9 — Durable media storage
Status: DONE
Changed: config/settings/{base,prod}.py, docker-compose.prod.yml,
requirements.txt, apps/core/tests/{test_prod_settings,test_deploy_migrate}.py
Verified by: both branches resolved in-container (off → FileSystemStorage,
on → GoogleCloudStorage, imports clean, no network); `pytest apps/core` → 101
passed, `apps/identity` → 86 passed.
Needs from human: set `USE_GCS_MEDIA=true` + `GS_BUCKET_NAME` at deploy, or
accept the named-volume fallback.

- `MEDIA_ROOT` pointed inside the container with no volume behind it, so every
  uploaded avatar vanished on the next container replacement. Silent: the photo
  endpoint 404s and the UI falls back to initials, so it reads as "photos keep
  disappearing", not as data loss.
- Bucket is private — `default_acl=None`, `querystring_auth` on, no public URLs.
  Media still only reaches a browser through the authenticated, scope-checked
  photo endpoint. A public bucket of employee avatars is a leak wearing a CDN.
- `file_overwrite=False`, so one upload can never silently replace another.
- ADC by default rather than a shipped key file.
- Also repaired four `apps/core` tests my own C4/C6 commits broke, by **adding**
  tests for the new contracts (prod fails closed without `PUBLIC_APP_URL`;
  trigger check runs after the advisory lock is released; a missing trigger
  fails the deploy) rather than only patching them green.

## C10 — Mock layer kept out of production builds
Status: DONE
Changed: frontend/vite.config.ts, .github/workflows/ci.yml
Verified by: both directions built — normal build logs the removal and `dist/`
has no worker; `VITE_USE_MOCKS=true` still produces one. tsc clean, 181 tests.
Needs from human: nothing.

- Measured first: the JS half was already safe — `import.meta.env.VITE_USE_MOCKS`
  folds to a literal `false`, so Rollup drops the mock import and the "any
  password works" path with it.
- `public/mockServiceWorker.js` was the real gap. Vite copies `public/` verbatim,
  so production served a request-interception service worker at 200. Inert only
  because the code that registers it is absent — one refactor from being live.
- Plugin deletes it in `closeBundle` (public/ assets sit outside the bundle
  graph). CI asserts both halves after every build, because a build-time
  guarantee nobody checks is one that quietly stops holding — and this one
  protects a passwordless login path.

## C11 — Declare the proxy depth
Status: DONE
Changed: apps/core/checks.py
Verified by: four outcomes exercised in-container against prod settings;
`pytest apps/core` → 112 passed.
Needs from human: set `DJANGO_NUM_PROXIES` explicitly at deploy (1 for Caddy
alone, 2 behind a CDN).

- Behind TLS, DRF identifies anonymous clients from `X-Forwarded-For`, which a
  proxy **appends** to. Wrong depth → a client supplying its own header gets a
  fresh throttle bucket every request, so the per-IP limit on `/api/auth/login`
  stops existing. Nothing errors; the counter just never fills.
- `prod.py` defaults it to 1, and that default is the trap. The check therefore
  asks whether it was **declared**, not whether it has a value: unset with proxy
  headers → `pms.E004`; defaulted → `pms.W002`; declared → silent.
- Runs under `check --deploy` only, so it gates a release without firing in tests.

## C12 — Stop shipping performance text to Sentry
Status: DONE
Changed: apps/core/observability.py, apps/core/tests/test_sentry.py,
apps/core/tests/test_sentry_scrubbing.py (new)
Verified by: 11 new tests; `pytest apps/core` → 112 passed.
Needs from human: nothing.

- Key-name redaction keeps every field whose name doesn't look sensitive — and
  here that *is* the sensitive part: `draft_body` (a written review), `body` (360
  feedback, 1:1 notes), `blockers` (a check-in). None would ever make a denylist,
  so any 500 on those endpoints shipped the text to a third-party store on a
  different retention policy. The pre-existing test asserted an `email` in the
  body was **preserved** — the behaviour, not an oversight.
- Enumerating fields that matter is the wrong shape of defence (list grows with
  every feature, omissions are silent). The body now goes wholesale, replaced by
  a marker so a developer knows one existed.
- Kept: stack trace, endpoint, method, tenant tag, request id — tested, because
  scrubbing that makes debugging impossible gets switched off.
- Query strings scrubbed too: invitation and reset links carry a single-use
  token, so a GET that 500s shipped a working credential.

## C13 — Every endpoint declares what it gates
Status: DONE
Changed: apps/ai/views.py,
apps/core/tests/test_endpoints_declare_permissions.py (new)
Verified by: `pytest apps/ai` → 619 passed; the new URLconf-wide guard, 4 passed.
Needs from human: nothing.

- `ai/jobs` and `ai/jobs/<pk>` leaned on `DEFAULT_PERMISSION_CLASSES` and declared
  nothing. Behaviour was already correct (both filter `requested_by=request.user`
  over the tenant-scoped manager), but the guarantee lived in the queryset, so an
  auditor couldn't tell "deliberately open" from "somebody forgot", and a change
  to the project default would have moved them with no diff touching them.
- The test walks the **whole URLconf** rather than naming the three views from the
  audit — naming three won't catch the fourth, and the fourth is the one written
  next month. Necessarily-public views (login, signup, SSO callbacks, signed
  webhooks, ops probes) are listed and all declare `AllowAny`: exempt from
  requiring auth, not from saying so.
- The sweep found no other offenders, which is the useful half of the result.

## C5 — Scheduled offsite backups with a proven restore path
Status: DONE
Changed: scripts/{backup_db.sh,backup_alert.py (new),gcs_backup_setup.sh (new),
restore_drill.sh (new)}, deploy/systemd/{pms-backup.service,pms-backup.timer,
pms-restore-drill.service} (new), docs/BUILD/BACKUP_RESTORE.md (new)
Verified by: a real 27M / 78-table dump taken against the live database and
drilled end to end — restore, per-table row counts, triggers — all three checks
passing. Shell syntax checked; lifecycle JSON parsed.
Needs from human: run `gcs_backup_setup.sh` once, grant the VM's service account
`roles/storage.objectAdmin` on `gs://axiom-backups`, create
`/srv/pms/.env.backup` (0600), install the units. Steps are in
`docs/BUILD/BACKUP_RESTORE.md`.

- `backup_db.sh` existed and **nothing ever called it**. No schedule, no offsite
  copy, no evidence any dump had ever been restored. That is the shape of a
  backup story that fails on the day it matters.
- Timer at 02:15 with `Persistent=true`, so a VM that was off overnight still
  backs up on next boot — "we thought it was running" is how gaps get discovered
  during a restore.
- Bucket setup enables **object versioning** (the thing that survives a bad
  script or ransomware; retention alone doesn't), enforces the public-access
  block, and sets lifecycle: NEARLINE at 7d, delete at 35d, old versions at 14d.
- The drill's third check is the one that earns its keep: a restore into a server
  that won't let a non-SUPER user create triggers **succeeds with the audit_log
  triggers simply missing**. You'd recover every row and quietly lose audit
  immutability with no error anywhere.
- Weekly drill runs `--from-bucket` deliberately — restoring the local copy
  proves the local copy is good and says nothing about the copy you'd reach for.
- Scratch DB is `test_restore_drill`, not `pms_restore_drill`: the app's MySQL
  user is scoped to its own DB plus a test prefix (`db/init.sql`), so the drill
  runs under the existing grant with no elevation. A drill needing elevated
  rights is one nobody schedules.
- Gaps stated in the doc rather than left implied: RPO is 24h (no binlog
  shipping), media isn't in the dump, and the drill compares row counts, not
  content.

## C14 — TLS-ready behind one variable (from the CONSTRAINTS block)
Status: DONE
Changed: Caddyfile, docker-compose.prod.yml, config/settings/prod.py,
apps/core/checks.py, apps/core/tests/{test_deploy_checks,test_prod_settings}.py,
docs/BUILD/ENABLE_TLS.md (new)
Verified by: both modes validated against the real `caddy` binary (`validate` +
`adapt`); `check --deploy` run in-container in both modes; prod compose now
parses with `DOMAIN` unset. `pytest apps/core` → 125 passed.
Needs from human: point DNS at the VM, then set `DOMAIN`, `ACME_EMAIL`,
`PUBLIC_APP_URL`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and open
:80 + :443. Steps in `docs/BUILD/ENABLE_TLS.md`.

- The prod stack **could not start at all** without `DOMAIN`/`ACME_EMAIL`
  (`${VAR:?}`), and Caddy would have attempted ACME for whatever it got. Let's
  Encrypt cannot certify a bare IP — which is what this deployment runs on — so
  the committed stack was undeployable in its actual environment.
- `DOMAIN` is now the single switch, read by both halves: empty → Caddy falls
  back to `:80` with no ACME and prod.py derives redirect/cookies/HSTS off; set →
  certificate, `http→https`, and all four Django settings on together. One switch
  because two is one somebody flips halfway.
- Leaving the old always-on posture wasn't an option: `SECURE_SSL_REDIRECT` on
  plain HTTP is an infinite redirect loop, and Secure cookies are never sent, so
  the admin and allauth SSO stop working. Not less secure — **not working**, and
  it would read as the app's fault rather than a missing DNS record.
- Turning them off is a real reduction in security, so it isn't silent: new
  `pms.W003` reports HTTP-only at every `check --deploy`, plus both reverse cases
  (a domain with the redirect off; reset links still built over `http://`, which
  leak a single-use token on the request the redirect only upgrades afterwards).
- Edge HSTS is matched on the **connection** (`http.request.tls.version`), not an
  env var — RFC 6797 forbids it over plain HTTP, and a browser honouring it on
  the bare IP would refuse the host once DNS existed. No second variable, correct
  in both modes permanently.
- Empty override = "follow DOMAIN". Compose passes `${VAR:-}`, so these arrive
  empty on every deploy that doesn't override them, and `env.bool` raises on
  `""` — the stack would have failed to boot because someone declined to override
  a default.
