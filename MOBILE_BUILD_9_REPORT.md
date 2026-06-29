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

- **[typecheck]** `npx tsc --noEmit` — **clean**, against the installed Expo **v56** React Native types
  (so the code compiles against the real RN/Expo/Expo-Router/React-Query/NativeWind APIs, per
  `mobile/AGENTS.md`).
- **[lint]** `npx expo lint` — **clean** (the lint gate is now initialised; 0 errors, 0 warnings).
- **[isolation]** `git diff` confirms **only `mobile/` changed** — the web app and the 1327-test
  backend are byte-for-byte untouched (no regression risk; `shared/` consumed read-only).
- **NOT done — the device run.** This environment has **no iOS simulator, no Android emulator, no
  device/Expo Go, and no browser** — so "runs on a device against the live backend" (BUILD_8/9's
  acceptance bar) **cannot be met here**. That is **your** step (below). "Compiles + lints" is real
  progress but is NOT "runs."

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

The mobile app is **built and compiles/lints clean**, additively, with zero risk to the working web
app or backend. It is **not yet device-verified** — that needs your phone/simulator (the one thing
this environment can't provide). Everything is committed + pushed.
