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

