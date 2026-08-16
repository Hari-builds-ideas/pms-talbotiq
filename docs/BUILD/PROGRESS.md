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

