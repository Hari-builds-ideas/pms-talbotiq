# BUILD_8 — Mobile foundation: shared layer + Expo scaffold + auth + shell (Phase 0–1)

> Read BUILD_0_READ_FIRST.md AND MOBILE_BUILD_PLAN.md AND MOBILE_READINESS.md first. Build 3 of the
> final push — this STARTS the mobile app (it does not finish it; mobile is multi-session per the plan).
> All BUILD_0 rules apply. The web app must already be stable (BUILD_6) before this runs. Do NOT break
> the existing web app while extracting the shared layer — the web build/tsc/lint must stay green at
> every step. Almost zero LLM calls.

This build delivers Mobile Phases 0 and 1 from MOBILE_BUILD_PLAN.md: the shared layer extraction, the
Expo scaffold, secure auth, the app shell + bottom-tab nav, and the first real screen (My dashboard).
Subsequent mobile screens are BUILD_9.

---

## Phase 8.1 — Extract the shared layer (web keeps working)

Per MOBILE_READINESS.md, lift the platform-agnostic modules into a shared workspace so web + mobile
import ONE source and never drift. Decide monorepo layout in DECISIONS.md (default: a `shared/` workspace
the existing `frontend/` and the new `mobile/` both import).
- Move/expose, WITHOUT changing behaviour: `lib/api/endpoints.ts` (typed client), `lib/api/client.ts`
  (axios + JWT refresh interceptor — refactor so the TOKEN STORE is injected: web uses its current
  store, mobile will use expo-secure-store), `lib/types.ts`, `lib/enums.ts`, `lib/errors.ts` (error-code
  mapper), the RBAC/feature-flag helpers (`ROLE_RANK`/`hasFeature`), the auth state machine logic
  (refactor `AuthContext` so the LOGIC is shared, only the storage + provider shell differ), and the
  async-AI polling hooks (`useAIJob`/`useAIAction`).
- The WEB app now imports these from the shared location. Run the full web build/tsc/lint + the existing
  frontend tests — they MUST stay green (this is a refactor, not a rewrite). Fix any import fallout.
- Do NOT move UI components (shadcn/Tailwind are web-only; mobile uses NativeWind/RN primitives).

**Verify [test]+[build]:** web frontend tsc+lint+build clean and all existing frontend tests green AFTER
the extraction (prove no web regression); the shared package builds/types on its own. Commit
`BUILD_8 8.1 — extract shared API/types/auth layer`.

## Phase 8.2 — Expo scaffold (Phase 0 of the mobile plan)

- `create-expo-app` (TypeScript) in `mobile/` (managed workflow); Expo Router (file-based); React Query;
  React Hook Form + zod; NativeWind wired to the SAME design tokens as web (indigo palette, type) for
  brand consistency. Import the shared layer.
- Secure token storage via `expo-secure-store` (NOT AsyncStorage/localStorage) — wire it as the injected
  token store for the shared axios client + auth logic.
- App shell + bottom-tab navigation (Dashboard / Goals / Feedback / Career / More per the plan) + the
  auth bootstrap (restore token → me → route) + the shared error-code mapper + a theme.

**Verify [build]+[live]:** the app builds and runs in Expo (simulator or Expo Go); typecheck/lint clean;
the shell + tabs render; a protected tab with no token routes to login. Capture how it was run in
PROGRESS.md. Commit `BUILD_8 8.2 — Expo scaffold + shell + secure storage`.

## Phase 8.3 — Auth on mobile (login + MFA + refresh)

- Login screen: tenant slug + email + password → the shared login flow; MFA challenge if enrolled (the
  existing TOTP challenge). Tokens stored in expo-secure-store; the shared refresh interceptor handles
  401→refresh→retry; a reused/expired refresh → re-login (same semantics as web).
- All states: loading, invalid creds (the error mapper's messages), MFA required, network error/offline.
- RBAC/feature-flag gating available to mobile screens via the shared helpers.

**Verify [live]:** log in against the running backend from the device/simulator (use the seed_demo creds
+ workspace); a protected route requires auth; refresh works; MFA path works if a demo account is
enrolled (enrol one idempotently in seed if needed). Capture the live login transcript. Commit
`BUILD_8 8.3 — mobile auth (login + MFA + refresh)`.

## Phase 8.4 — My dashboard (Mobile Phase 1)

- The employee/manager self-service dashboard: my latest cycle score/risk, my goals at a glance, my
  nudges, pending feedback requests, my roadmap snapshot — each from the existing endpoints
  (`/auth/me`, `/billing/my-features`, `/ai/nudges`, `goals.list({employee:me})`, `feedback.requestsMine`,
  `career.roadmap`), all O(1)/cached from builds 1 & 4. Pull-to-refresh; real loading/empty/error states;
  feature-flag gating (FULL_AI vs STARTER) via the shared helper.

**Verify [live]:** the dashboard shows real data for an employee and a manager against the running
backend; states work; pull-to-refresh works. Capture in PROGRESS.md. Commit `BUILD_8 8.4 — mobile My
dashboard`.

---

## End of BUILD_8
Write `BUILD_8_REPORT.md`: the shared-layer extraction (and PROOF the web app didn't regress), the Expo
scaffold + auth + dashboard, how it was run/verified live, what mobile screens remain (BUILD_9), test
counts, [test]/[live]/[build] honesty, commit list. Then proceed to BUILD_9.
