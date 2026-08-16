# BUILD_8 — Mobile foundation — REPORT

**Status: BLOCKED on the Expo runtime (environment), not on code/design.** See
`BLOCKER_8_mobile_runtime.md`. The web app + backend remain green and committed;
nothing was left half-wired.

## The honest situation

BUILD_8 (and BUILD_9) build a **React Native + Expo** app whose every phase, per
`MOBILE_BUILD_PLAN.md` §5 and the BUILD_8 spec, is accepted by **running in the
Expo simulator / on a device via Expo Go against the live backend** — the final-
push brief is explicit: *"the real bar is 'runs in Expo', not 'compiles'."*



This run is a **headless terminal**: no iOS simulator, no Android emulator, no
device/Expo Go, no browser (so not even `expo start --web`), and no Metro/Expo
consumer to cross-platform-validate a shared extraction. The defining verification
for 8.2–8.4 + BUILD_9 is therefore unreachable here.

## Decision (D21)

- **Did NOT** speculatively refactor the web app's core infrastructure (the API
  client + auth/refresh) for Phase 8.1's `shared/` extraction. It is web-verifiable
  in isolation, but its mobile correctness (Metro resolution, the SecureStore token
  store, NativeWind) can only be validated by the mobile consumer — which can't be
  built here. Risking the green, verified web app for a benefit that can't be
  confirmed in this environment is the wrong unattended trade. The extraction
  belongs in the same session that scaffolds + runs Expo, so both sides validate
  together (as `MOBILE_BUILD_PLAN.md` Phase 0 itself frames it).
- **Wrote** a decision-complete, ready-to-execute plan (`BLOCKER_8_mobile_runtime.md`)
  so an Expo-capable session executes the whole mobile foundation fast.

## What is already mobile-ready (verified)

- **Every screen's data** is a real, O(1)/cached endpoint — verified in
  `MOBILE_READINESS.md` and re-confirmed by the BUILD_6 live smoke (47/47).
- **The platform-agnostic layer** (`lib/api/endpoints.ts`, `lib/api/client.ts` —
  already on an abstracted `tokenStore` + `emitForcedLogout` seam — `lib/types.ts`,
  `lib/enums.ts`, `lib/errors.ts`, `ROLE_RANK`/`hasFeature`, `useAIJob`/`useAIAction`,
  the `AuthContext` logic) is cleanly extractable with no behaviour change.
- A standing **MFA-enrolled demo account** exists for the mobile MFA path (seed_demo).

## Verification
- **[n/a]** No code was changed in this build, so the web frontend + backend remain
  exactly as they were at the end of BUILD_7 (frontend tsc/lint/build clean, 43
  vitest; backend 1171 passed, 2 deselected). Nothing to regress.

## What remains (the Expo-capable session)
The full plan is in `BLOCKER_8_mobile_runtime.md`: 8.1 shared extraction (with the
injectable-client diff), 8.2 Expo scaffold, 8.3 auth (+MFA), 8.4 My dashboard, then
BUILD_9 (the remaining screens + hardening). Needs: an Expo simulator or an Expo Go
device. Everything backend-side it needs already exists (except the push
device-register endpoint, by design later).
