# Mobile — status: deferred to v2 (backend-ready, frontend needs work)

Mobile is **not part of the v1 handoff scope.** It exists as a real Expo app that already talks to the
live backend, but it has not had the v1 simplification/brand pass and is not demo-polished. This doc is
so the next person knows exactly where it stands and where to start — nothing here is a blocker for v1.

## What's already there (`mobile/`)
- An **Expo + Expo Router + React Native** app (TypeScript, NativeWind/Tailwind, React Query, react-hook-form).
- It **shares the web's data layer**: `mobile/src/lib/api.ts` wires the same `@shared/api/client` and the
  same `shared/src/types.ts` the web app uses — so endpoints, request/response types, and auth are already
  in sync with the backend. Tokens are stored in the OS keychain (`expo-secure-store`,
  `secureTokenStore.ts`), and a forced-logout handler mirrors the web.
- **Working auth + screens**: `login.tsx`, a tab IA (`(tabs)/` → home, goals, career, feedback, more), plus
  `approvals`, `checkins`, `team-checkins`, `recognition`, `reviews`, and an agent `chat.tsx`.
- **Backend host auto-discovery**: on a device, `localhost` is the phone, so `api.ts` derives the Mac's LAN
  IP from the Metro host and targets `:8080` (override with `EXPO_PUBLIC_API_BASE_URL`).

## Why "backend-ready"
The backend is a plain JSON API with server-side RBAC and tenant isolation — it does not care whether the
client is web or native. Mobile reuses the exact same `@shared` client + types, so **there is no
mobile-specific backend work**: every endpoint the web app uses is already available to mobile.

## Why "frontend needs work" (the v2 to-do)
- It **hasn't had the v1 simplification pass** — the status-first/plain-language decisions in
  `V1_VS_V2.md` (T-score demotion, plain Goals labels, hidden succession/career/calibration) are **not**
  reflected in the mobile screens. Career is even still a visible tab.
- **No brand pass** — the app icon/splash are still Expo starter assets; the `mobile/README.md` is still the
  `create-expo-app` boilerplate.
- **No test suite** (web has vitest; mobile has none yet) and it hasn't been run through a device QA sweep.
- Not wired into the demo deploy (the free demo is web-only).

## Where to start (v2)
1. Run it against a local backend: `cd mobile && npm install && npx expo start` (backend up via
   `docker compose up -d`); log in with the demo accounts from `DEVELOPER_SETUP.md`.
2. Mirror the v1 scope: apply the same hide/simplify decisions as `frontend/src/app/v1.ts` (hide
   career/succession/calibration; lead with status, not T-score). Consider a shared scope module so web +
   mobile can't drift.
3. Brand + polish: real icon/splash from the TalbotIQ mark, replace the boilerplate README, then a device
   QA pass and a minimal test setup.

**Bottom line:** the hard part (a secure, tenant-safe API + a shared typed client) is done and shared;
mobile v2 is a focused frontend effort, not new backend work.
