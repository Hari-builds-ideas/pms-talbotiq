# Mobile audit — before and after (A0 inventory, A11 verification)

Measured, not guessed. Every number below came from a real headless Chromium
walking the real application: the full Docker stack (`docker compose up mysql
redis web frontend`), the **production** SPA build served by nginx on
`http://127.0.0.1:8090`, talking to the real Django API same-origin. Seeded
tenant `acme`, real logins for all four roles.

Two viewports: **390×844** (iPhone 14) and **360×800** (common Android).

Measurement harness: for each route the page was asked for its own geometry —
`documentElement.scrollWidth` vs `innerWidth`, every element whose
`getBoundingClientRect().right` exceeded the viewport, every interactive element
under 44×44, every text node under 14px, every input under 16px, table widths,
and Recharts container dimensions.

> The first attempt ran against the MSW mock layer and was discarded: the mock
> layer has **zero** feedback handlers (90 handlers against 196 real endpoints),
> so `/api/feedback/requests/mine` fell through to Vite, returned `index.html`,
> and crashed the app. That crash is not a product bug — but what it exposed is
> (finding 1 below). The audit was redone against the real backend.

---

## Severity summary

**P1 — content is unreachable or the layout is broken.** `/settings`,
`/admin/users`, `/audit`, `/reviews`, `/jd`.
**P2 — usable but wrong.** `/`, `/goals`, `/recognition`, `/checkins`,
`/admin/billing`.
**P3 — cosmetic or minor.** `/approvals`, `/feedback`, `/org`, `/analytics`,
`/help`.

---

## Findings, in fix order

### 1. A component error anywhere in the shell white-screens the whole app — P0

`AppLayout` wraps only `<Outlet/>` in `<ErrorBoundary>`. `Topbar` and `Sidebar`
sit **outside** it, and there is no boundary above `AppLayout` either. When
`usePendingCount()` in `Topbar.tsx:60` hit a response that was not an array, it
threw `TypeError: (requests.data ?? []).filter is not a function`, React
unmounted the entire tree, and `#root` was left empty — a white screen with no
recovery path and no way back to a working page.

`?? []` guards `null`/`undefined` only. It does not guard "the server sent an
object", "a proxy returned an HTML error page", or "this endpoint started
paginating". Any of those is a full outage of the SPA, not a degraded panel.

Reproduced live; captured via `window.reportError`. This is the most severe
finding in the audit and is not mobile-specific.

### 2. The topbar's right-hand controls are off-screen and untappable — P1

On **every route, for every role, at both viewports**:

```
header width      390
header scrollWidth 487        →  97px unreachable (127px at 360)
  ├ menu button        w=16   right=36
  ├ search button      w=299  right=347
  └ right cluster      w=128  right=487   ← ends 97px past the screen edge
```

The right cluster holds **notifications, Ask AI, and the account menu — which is
the only route to Sign out**. On a phone it is simply not reachable. The header
has `overflow` hidden by the shell, so nothing scrolls sideways to reveal it;
the controls are silently gone. This is why "panels do not fit the viewport" and
why "request desktop site" does not help — the layout is not too wide, the
elements are positioned outside it.

Cause: classic flexbox `min-width: auto`. The search button is
`max-w-xl flex-1` but carries no `min-w-0`, so it refuses to shrink below the
intrinsic width of its content (icon + "Search employees, OKRs, goals…" + the
`⌘K` kbd), pushing everything after it off the edge.

### 3. `/settings` is 578–608px wider than the screen — P1

The single worst route, for all four roles. Also carries **9 inputs under 16px**,
so iOS zooms the page on every field focus.

### 4. Four data tables break the layout — P1

`/reviews`, `/admin/users`, `/audit`, `/jd` each render a `<table>` wider than
the viewport, at both sizes and for every role that can reach them. These are
exactly the `@tanstack/react-table` views named in A6.

### 5. Touch targets far below 44×44 — P2

Worst counts: `/recognition` 252, `/goals` 208, `/settings` 71, `/admin/users`
66. The shell itself is a repeat offender on every route:

| Control | Measured | Required |
|---|---|---|
| Toggle navigation (hamburger) | **16×32** | 44×44 |
| Notifications bell | 36×36 | 44×44 |
| Ask AI | 36×36 | 44×44 |
| Open account menu | 44×40 | 44×44 |
| Skip to main content | 32×16 | 44×44 |

The hamburger being 16px wide matters most: it is the only way to open
navigation on a phone.

### 6. Inputs under 16px cause iOS zoom — P2

`/settings` 9, employee `/` 7, `/checkins` 4, `/audit` 3, `/admin/users` 1,
`/admin/billing` 1. Each one zooms the viewport on focus and does not zoom back.

### 7. Text under 14px is pervasive — P2/P3

`/goals` 1117 nodes, `/recognition` 512, `/admin/users` 365, `/reviews` 316,
`/audit` 270. Sizes observed: 10px, 11px, 12px, 13px.

### 8. Sidebar drawer is half-implemented — P2

Measured with the drawer open at 390px:

| Behaviour | State |
|---|---|
| Closed on mount at mobile width | ✅ already correct |
| Overlays content, `position: fixed`, backdrop present | ✅ already correct |
| Closes on route change | ✅ already correct |
| Occupies 65.6% of a 390px screen when open | ⚠️ by design, acceptable |
| **Focus moves into the drawer when opened** | ❌ focus stays on the toggle |
| **Focus is trapped while open** | ❌ not implemented |
| **Escape closes it** | ❌ does nothing |
| Desktop collapse preference persisted | ❌ not persisted |

The drawer breakpoint is `lg` (1024px), not `md` (768px) as A2 specifies — so
tablets get the phone treatment. Recorded as a deliberate deviation to confirm.

### 9. The greeting uses the browser's timezone, not the user's — P2

`DashboardPage.tsx:37` reads `new Date().getHours()`. There are only three bands
and no "Good night" at all. With the browser in UTC and the user in IST, 00:05
local reads as 18:35 → "Good evening" at midnight, exactly as reported.
`identity.User.timezone` exists but **is not returned by `/api/auth/me`**, so
the client currently has no way to do this correctly.

### 10. AI feature icons — no broken assets found

`brokenImages` was empty on every route and `svgCount` was 11–16 per page, so
`lucide-react` is importing and rendering. The reported "AI icons do not render"
is most likely finding 2: the **Ask AI button is one of the controls positioned
off-screen** (right=437 on a 390px viewport). To be confirmed after the topbar
fix.

### 11. Charts are fine

`/analytics` Recharts containers measured 308×220 at 390px — not slivers, no
horizontal overflow. A8 needs a min-height guard and tick-density reduction, not
a rescue.

---

## Per-route measurements (before)

Off-screen px = furthest element right edge minus viewport width. Wide tables =
tables wider than the viewport / total tables.

| Route | VP | Roles | Off-screen px | Wide tables | <16px inputs | <44px targets | <14px text | Severity |
|---|---|---|---|---|---|---|---|---|
| `/admin/users` | 360 | adm | 250 | 1/1 | 1 | 66 | 365 | P1 |
| `/admin/users` | 390 | adm | 220 | 1/1 | 1 | 66 | 365 | P1 |
| `/audit` | 360 | adm | 307 | 1/1 | 3 | 13 | 270 | P1 |
| `/audit` | 390 | adm,hrb | 277 | 1/1 | 3 | 13 | 270 | P1 |
| `/reviews` | 360 | adm,emp | 255 | 1/1 | 0 | 15 | 316 | P1 |
| `/reviews` | 390 | adm,emp,hrb,man | 262 | 1/1 | 0 | 15 | 316 | P1 |
| `/settings` | 390 | adm,emp,hrb,man | 578 | 0/0 | 9 | 71 | 224 | P1 |
| `/settings` | 360 | emp | 608 | 0/0 | 9 | 71 | 223 | P1 |
| `/jd` | 390 | adm,hrb,man | 180 | 1/1 | 0 | 15 | 44 | P1 |
| `/goals` | 360 | adm,emp | 127 | 0/0 | 0 | 208 | 1117 | P2 |
| `/goals` | 390 | adm,emp,hrb,man | 97 | 0/0 | 0 | 208 | 1117 | P2 |
| `/recognition` | 390 | adm,emp,hrb,man | 97 | 0/0 | 0 | 252 | 512 | P2 |
| `/` | 360 | adm,emp | 127 | 0/0 | 7 | 21 | 75 | P2 |
| `/` | 390 | adm,emp,hrb,man | 97 | 0/1 | 7 | 28 | 126 | P2 |
| `/admin/billing` | 390 | adm | 97 | 0/0 | 1 | 18 | 90 | P2 |
| `/checkins` | 390 | adm,emp,hrb,man | 97 | 0/0 | 4 | 15 | 35 | P2 |
| `/checkins` | 360 | emp | 127 | 0/0 | 4 | 14 | 35 | P2 |
| `/approvals` | 360 | adm | 127 | 0/0 | 0 | 15 | 39 | P3 |
| `/approvals` | 390 | adm,hrb,man | 97 | 0/0 | 0 | 16 | 41 | P3 |
| `/feedback` | 390 | adm,emp,hrb,man | 97 | 0/0 | 0 | 16 | 29 | P3 |
| `/feedback` | 360 | emp | 127 | 0/0 | 0 | 11 | 13 | P3 |
| `/help` | 390 | adm | 97 | 0/0 | 0 | 14 | 27 | P3 |
| `/org` | 360 | adm | 127 | 0/0 | 0 | 24 | 57 | P3 |
| `/org` | 390 | adm,hrb,man | 97 | 0/0 | 0 | 24 | 57 | P3 |
| `/analytics` | 360 | adm | 127 | 0/0 | 0 | 10 | 12 | P3 |
| `/analytics` | 390 | adm,hrb,man | 97 | 0/1 | 0 | 10 | 43 | P3 |

---

## Method notes

- Navigation between routes used `history.pushState` + a `popstate` event rather
  than a full reload, because the access token is held in memory only; a reload
  drops it and every route measures as a redirect to `/login`.
- `overflowX` reads `false` almost everywhere. That is not good news — the shell
  sets `overflow-hidden`, so oversized content is **clipped rather than
  scrollable**. "Off-screen px" is the honest metric, not `scrollWidth`.
- Charts, tables and touch targets were measured after a 2s settle per route so
  React Query had returned.


---

## A11 — after (verified)

Same harness, same two viewports, same four roles, re-run against a rebuilt
production image once PHASE A was complete.

| Route | VP | Off-screen px | Wide tables | <16px inputs | Under-sized targets |
|---|---|---|---|---|---|
| `/` | 360 | 127 → **0** | 0 | 7 → **0** | 21 → **4** |
| `/` | 390 | 97 → **0** | 0 | 7 → **0** | 28 → **4** |
| `/admin/billing` | 390 | 97 → **0** | 0 | 1 → **0** | 18 → **2** |
| `/admin/users` | 360 | 250 → **19** | 1 → **0** | 1 → **0** | 66 → **0** |
| `/admin/users` | 390 | 220 → **0** | 1 → **0** | 1 → **0** | 66 → **0** |
| `/analytics` | 360 | 127 → **0** | 0 | 0 | 10 → **0** |
| `/analytics` | 390 | 97 → **0** | 0 | 0 | 10 → **0** |
| `/approvals` | 360 | 127 → **0** | 0 | 0 | 15 → **0** |
| `/approvals` | 390 | 97 → **0** | 0 | 0 | 16 → **0** |
| `/audit` | 360 | 307 → **0** | 1 → **0** | 3 → **0** | 13 → **0** |
| `/audit` | 390 | 277 → **0** | 1 → **0** | 3 → **0** | 13 → **0** |
| `/checkins` | 360 | 127 → **0** | 0 | 4 → **0** | 14 → **0** |
| `/checkins` | 390 | 97 → **0** | 0 | 4 → **0** | 15 → **0** |
| `/feedback` | 360 | 127 → **0** | 0 | 0 | 11 → **0** |
| `/feedback` | 390 | 97 → **5** | 0 | 0 | 16 → **0** |
| `/goals` | 360 | 127 → **0** | 0 | 0 | 208 → **0** |
| `/goals` | 390 | 97 → **0** | 0 | 0 | 208 → **0** |
| `/help` | 390 | 97 → **0** | 0 | 0 | 14 → **3** |
| `/jd` | 390 | 180 → **0** | 1 → **0** | 0 | 15 → **0** |
| `/org` | 360 | 127 → **0** | 0 | 0 | 24 → **0** |
| `/org` | 390 | 97 → **0** | 0 | 0 | 24 → **0** |
| `/recognition` | 390 | 97 → **0** | 0 | 0 | 252 → **0** |
| `/reviews` | 360 | 255 → **0** | 1 → **0** | 0 | 15 → **0** |
| `/reviews` | 390 | 262 → **0** | 1 → **0** | 0 | 15 → **0** |
| `/settings` | 360 | 608 → **0** | 0 | 9 → **2** | 71 → **0** |
| `/settings` | 390 | 578 → **0** | 0 | 9 → **2** | 71 → **0** |

### Totals

| Metric | Before | After |
|---|---:|---:|
| Off-screen content (px, summed over route/viewport) | 4796 | **24** |
| Under-sized touch targets (<44px, no hit area) | 1249 | **13** |
| Tables wider than the viewport | 6 | **0** |
| Inputs under 16px (iOS zoom) | 29 | **2** |

393 controls now carry a 44x44 hit area via `.tap-target` rather than being
resized, so the desktop layout is byte-identical.

### What is deliberately still on the list

Four residuals, all measured and none of them blocking:

- **`/admin/users` at 360px — 19px over.** Fits at 390px; only the narrower
  Android width clips, and the card layout itself is correct. Worth a look at the
  card's two-column grid at the very narrow end.
- **`/feedback` at 390px — 5px over.** The tab strip. It now scrolls rather than
  pushing the page, so nothing is unreachable; the strip is simply 5px wider than
  the viewport before it scrolls.
- **`/settings` — 2 inputs under 16px.** Both are checkboxes. iOS only zooms on
  text entry, so these do not trigger it; they are counted because the harness
  measures every input.
- **13 under-sized targets** across `/`, `/admin/billing` and `/help`. Each is a
  short inline text link inside prose, where a 44px hit area would overlap the
  line above or below it.

### Not re-tested here

The greeting fix (A4) is covered by unit tests against a pinned clock rather than
this walk — the harness would only ever observe whatever time it ran at. See
`frontend/src/lib/greeting.test.ts`.
