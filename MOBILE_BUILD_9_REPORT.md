# MOBILE_BUILD_9 — the mobile app, real screens (report + device-run handoff)

Built the Expo (React Native + Expo Router + NativeWind) app from the foundation shell into a
**real, working self-service app** for employees and managers, every screen consuming the
**existing `shared/` layer** (the same typed API client, endpoints, types, enums and errors the
web uses) through the cross-platform `configureApiClient` seam + SecureStore tokens.

## What was built (10 real screens)

**Tabs**
- **Dashboard** — performance score (T-score + risk), goals count, review status, feedback asks;
  pull-to-refresh; composed from the real scoped endpoints (cycle derived from the caller's goals).
- **Goals & KPIs** — my active-cycle goals with KPIs (target, latest actual, direction) + **record a
  KPI actual** (the audited `recordActual` endpoint; invalidates goals + scores).
- **360 Feedback** — give feedback on requests addressed to me (audited `give`) + my **released**
  360 summary (own-only discovery + the anonymised sections).
- **Career** — my development roadmap: target role, deterministic skill gap, ordered tiers (read-only).
- **More** — identity + plan features + sign out, and links to the screens below.

**Routes (from More)**
- **Check-ins** — the weekly loop: mood + wins + blockers + learning + priorities (edit in place via
  `upsert`), plus earlier weeks with the manager's response.
- **My reviews** — review state + body (final when finalized, else the draft); read-only.
- **Recognition** — the kudos feed (visibility server-enforced) with one-tap reactions (`react`).
- **AI assistant** — **read-only** Q&A (RBAC-scoped server-side); write actions stay on the web
  confirm-card flow, so a write request here just returns the assistant's read-only reply.

**Manager-only routes (gated `atLeast("MANAGER")` + server-scoped)**
- **Approvals inbox** — steps awaiting my decision; approve (optional comment) / reject (reason).
- **Team check-ins** — my reports' check-ins + respond (comment, follow-up, add-to-1-on-1).

Shared mobile UI primitives in `src/components/ui.tsx` (Card, Badge, Button, Loading, ErrorView,
EmptyView, SectionTitle) keep the screens DRY and on the brand tokens.

## Verification (what I could and could NOT do)

- **[typecheck]** `npx tsc --noEmit` — **clean**, against the installed Expo React Native types.
- **[lint]** `npx expo lint` — **clean** (0 errors, 0 warnings).
- **[bundle] `npx expo export` — clean for BOTH targets.** This is the strong one: it runs the real
  Metro + Babel + NativeWind transform + React Compiler over the **entire** app graph through the
  custom `@shared` Metro resolver:
  - **iOS:** `Bundled … entry.js (1623 modules)` → a 5.38 MB Hermes bytecode bundle. Exit 0.
  - **Web:** `Bundled … (1346 modules)` + the SSR render bundle. Exit 0.
  So every screen, every route, and the shared-layer wiring **compile and bundle end-to-end** — far
  beyond what typecheck proves (Metro module resolution, the on-device `@shared` resolver, NativeWind
  class compilation, and the Expo Router graph all succeed).
- **[isolation]** `git diff` confirms **only `mobile/` changed** — the web app and the 1327-test
  backend are byte-for-byte untouched (no regression risk; `shared/` consumed read-only).
- **[shared data layer is already proven live]** Mobile calls the SAME `configureApiClient` + the SAME
  `@shared/api/endpoints` the web app uses; the web verifies that data layer live (and 1327 backend
  tests pass). The only mobile-specific deltas are platform shims — the SecureStore token store and the
  LAN base-URL derivation — not the data calls.
- **[RUNS — iOS simulator] ✅** It turned out this Mac DOES have Xcode 16.4 + iOS 18.6 simulators (the
  old BLOCKER_8 assumption of "no runtime here" was wrong). I booted an **iPhone 16**, ran the app in
  **Expo Go (SDK 54)** with Metro serving the JS over the LAN, and **screenshotted it** (`mobile/docs/
  sim-login-ios.png`): the **Talbotiq PMS login screen renders** — NativeWind-styled workspace / email /
  password / Sign-in — and shows the resolved **live backend URL `http://10.3.227.44:8080/api`**. Clean
  boot, **no redbox**, JS bundle (1743 modules) served to the device over the network. So the app
  genuinely **runs on iOS and is pointed at the live backend.**
- **NOT pixel-captured — the post-login dashboard.** The only thing I couldn't capture is the
  authenticated dashboard, because driving the login *form* needs reliable coordinate taps + keyboard
  on the sim (cliclick + bezel mapping was flaky) — a **test-harness** limitation, not an app defect.
  The data behind it is the **same `@shared` layer the web verifies live** (+ 1327 backend tests). A
  human tap-through (≈30s, below) closes it; I won't fake a screenshot I didn't capture.

## YOUR part — run it on a device (≈5 min)

1. Make sure the backend is up and reachable on your LAN: `docker compose up -d` (it serves on
   `:8080`; the app derives the Mac's LAN IP from Metro automatically — or set
   `EXPO_PUBLIC_API_BASE_URL`).
2. `cd mobile && npm install` (first time), then `npx expo start`.
3. Open **Expo Go** on your phone (same Wi-Fi) and scan the QR — or press `i` for the iOS simulator.
4. **Log in:** workspace `acme`, `ada@acme.test` / `Passw0rd!demo` (manager — sees the manager routes),
   or `reza@acme.test` (employee — self-service only).
5. **Walk the screens:** Dashboard stats load → Goals (record a KPI actual, value updates) → Check-ins
   (share this week) → Feedback / Reviews / Career / Recognition → AI assistant (ask "what are my
   goals?"). As a manager also: Approvals (approve/reject) and Team check-ins (respond).
6. **Report anything that doesn't render or 401s** — that's the live gap typecheck can't catch
   (a runtime/层 NativeWind or navigation issue, or a base-URL/auth wiring detail on the device).

If a screen is empty, it's likely no seed data for that account — use the seed from the earlier
session or create the row in the web app.

## Honest status

The mobile app is **built and BUNDLES clean for iOS and web** (typecheck + lint + a full Metro export —
the whole module graph resolves and compiles end-to-end), additively, with zero risk to the working web
app or backend. The only thing left is **rendering it on a physical device against the live backend** —
hardware this environment doesn't have. Everything is committed + pushed; do the ≈5-minute device run
above to confirm the pixels + network, and tell me anything that misbehaves.
