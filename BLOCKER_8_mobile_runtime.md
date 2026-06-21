# BLOCKER — BUILD_8 / BUILD_9 (mobile): no Expo runtime in this environment

**Status: BLOCKED on environment, not on code or design.** Per BUILD_0's blocker
rule, prior work is left green/committed/pushed and this is documented with a
precise, ready-to-execute plan. BUILD_6 and BUILD_7 are fully complete.

## Why blocked

The entire mobile series is defined — by `MOBILE_BUILD_PLAN.md` §5 and `BUILD_8`
itself — with a **device/simulator acceptance bar**: every phase says *"runs in
the Expo simulator / on a device via Expo Go"*, and the final-push brief states
plainly: *"For mobile, the real bar is 'runs in Expo against the live backend',
not 'compiles'."*

This run executes in a **headless terminal** with:
- no iOS simulator and no Android emulator,
- no physical device / Expo Go,
- no browser (confirmed in BUILD_6 6.1 — `chromium`/`playwright` absent, so even
  `expo start --web` / react-native-web couldn't be rendered or screenshotted),
- no Metro/Expo consumer to **cross-platform-validate** a shared-package extraction.

So the defining verification for **8.2, 8.3, 8.4 and all of BUILD_9 cannot be met
here.** Writing the React Native screens blind (no compile against RN/Expo types,
no run) would be "written, not verified" — which the contract explicitly ranks
below "verified over written," and `done = real + verified`.

## Why I did NOT speculatively refactor the web app's core infra (Phase 8.1)

Phase 8.1 (lift `lib/api/*`, `types`, `enums`, `errors`, auth logic, AI hooks into
a `shared/` workspace) is *web-verifiable* in isolation — BUT its correctness for
mobile (Metro module resolution, the injected SecureStore token store, NativeWind
tokens) can only be validated by the mobile consumer, which can't be built here.
Refactoring the web's most critical infrastructure (the API client + auth/refresh
that the whole app depends on) with **no cross-platform consumer to validate it**
would put the green, verified web app at regression risk for a benefit that can't
be confirmed in this environment. That trade is not worth it unattended. The clean
extraction belongs in the same session that scaffolds + runs the Expo app, so both
sides are validated together (exactly as `MOBILE_BUILD_PLAN.md` Phase 0 frames it:
"extract `shared/` **and wire web + mobile to it**").

## What is already mobile-READY (no new work needed)

- **Endpoints**: every screen's data is already a real, O(1)/cached endpoint
  (verified in `MOBILE_READINESS.md` + the live smoke 47/47). Nothing missing
  except the push device-register endpoint (Phase 8 of the plan, by design later).
- **The platform-agnostic layer** is cleanly separable as-is: `lib/api/endpoints.ts`,
  `lib/api/client.ts` (already uses an abstracted `tokenStore` + `emitForcedLogout`
  seam — see below), `lib/types.ts`, `lib/enums.ts`, `lib/errors.ts`, `ROLE_RANK`,
  `useAIJob`/`useAIAction`, and the `AuthContext` logic.

## Ready-to-execute plan (for the Expo-capable session)

Run this where an Expo simulator or Expo Go device is available.

**Phase 8.1 — shared extraction (do it WITH the mobile scaffold so both validate):**
1. `shared/` workspace (TS). Move `lib/{types,enums,errors}.ts`, `lib/api/{endpoints,client}.ts`,
   `ROLE_RANK`/`hasFeature`, `useAIJob`/`useAIAction`, and the auth state-machine logic.
2. Refactor `client.ts` to a `configureApiClient({ baseUrl, tokenStore, onForcedLogout })`
   seam — the store interface already exists (`getAccess/getRefresh/set/clear`,
   `tokenStore.ts`); web injects its localStorage impl + `import.meta.env` base URL,
   mobile injects an `expo-secure-store` impl + the Expo env base URL. The refresh
   interceptor logic is unchanged.
3. Web imports from `shared` (path alias + re-export shims at `lib/*` so feature
   code is untouched). Gate: web `tsc`+`lint`+`build` + the 43 frontend tests + a
   live login MUST stay green.

**Phase 8.2 — Expo scaffold:** `create-expo-app mobile` (TS), Expo Router, React
Query, RHF+zod, NativeWind on the web indigo tokens; import `shared`; SecureStore
token store; bottom-tab shell (Dashboard/Goals/Feedback/Career/More) + auth bootstrap.

**Phase 8.3 — auth:** login (tenant slug + email + password) → shared flow; MFA
TOTP challenge (a standing enrolled demo account already exists — see seed_demo);
SecureStore tokens; shared refresh interceptor. Demo creds: tenant `acme`,
`admin@acme.test` / `Passw0rd!demo` (HRBP `priya@`, Manager `ada@`, Employee `reza@`).

**Phase 8.4 — My dashboard:** score/risk, goals, nudges, pending feedback, roadmap
snapshot from the existing endpoints; pull-to-refresh; all states; flag-gated.

**BUILD_9 —** the remaining self-service screens (goals/actuals, review+self-assessment,
360 give+summary, career, AI chat, manager extras, notifications, hardening) per
`MOBILE_BUILD_PLAN.md` Phases 2–9.

Acceptance for every phase: `tsc`+`lint`+`build` clean **and** runs in the Expo
simulator/Expo Go against the live backend → commit + push.

## What remains outside this run
- An Expo dev environment (simulator or an Expo Go device on the same network).
- The push device-register endpoint (the one thin backend add, Phase 8 — later).
- EAS build config + store accounts (ship time — out of this series by design).
