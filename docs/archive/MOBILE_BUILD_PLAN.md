# MOBILE_BUILD_PLAN.md — the Talbotiq PMS mobile app (plan only)

> This is a **decision-complete build plan**, written so a future autonomous run
> can execute it the way the web `*_build.md` files drove the web build. It does
> **not** build anything — the mobile app is a separate run. The web product is
> finished; this is what mobile should be.

---

## 1. Decision framing — what to build

Two viable shapes:

| Option | What it is | Pros | Cons |
|--------|-----------|------|------|
| **A. Responsive mobile-web** | Make the React web app usable in a phone browser | Fastest; one codebase; no app store | No native feel; no push notifications; not in the App/Play stores; the Admin Hub is desktop-first and would need heavy responsive rework |
| **B. React Native + Expo** (recommended) | A true native iOS+Android app from one TypeScript codebase | One codebase → both platforms; **reuses the web's React + TS + API client + types + auth logic**; native feel + push; built in VS Code/Cursor with Claude Code (Xcode/Android Studio only at build/submit time); secure native token storage | A multi-session build; a release pipeline (EAS) + store accounts at ship time |

### Recommendation: **React Native + Expo (Option B).**
Why:
- **One codebase, both platforms.** Expo + RN compiles to iOS and Android from the same TypeScript — no separate native apps.
- **Maximum reuse of what already exists.** The web app already has a typed API client (`frontend/src/lib/api/endpoints.ts`), a complete type layer (`frontend/src/lib/types.ts`, `enums.ts`), an error-code mapper (`errors.ts`), RBAC/feature-flag logic (`ROLE_RANK`, `hasFeature`), and auth/refresh (`AuthContext` + the axios client). These are **platform-agnostic** and should be **extracted into a shared package** so web and mobile never drift.
- **Built with Claude Code, not Xcode.** Day-to-day development + the Expo simulator run in the editor. Xcode/Android Studio are only needed at native build/submit time (handled by EAS in the cloud — you may not need them locally at all).
- **Native essentials** mobile needs: secure token storage (`expo-secure-store`, **not** localStorage), biometric unlock, and push notifications (the KPI nudges + "feedback requested" + "summary released" events map perfectly to push later).

**Interim option:** if app-store presence isn't needed yet, a responsive-web pass on the self-service screens is the faster stop-gap — but it's throwaway relative to B. **Final call is Hari's**; this plan assumes B.

---

## 2. Scope — mobile is the SELF-SERVICE surface (not the Admin Hub)

Mobile is for the **Employee** and **Manager** doing their own work on the go.
The management/desktop surfaces stay web-only.

**IN (employee + manager self-service):**
1. **Login + MFA** (tenant slug + email + password; MFA challenge if enrolled).
2. **My dashboard** — my goals at a glance, my latest cycle score/risk, my nudges, pending feedback requests, my roadmap snapshot.
3. **My goals & KPIs** — view my goals/KPIs, **record actuals** (own-only).
4. **My review** — view my finalized review; submit my **self-assessment**.
5. **Give 360 feedback** — respond to invitations (the giver surface).
6. **My 360 summary** — my released summary (uses the new `/feedback/my-cycles` discovery endpoint).
7. **My career roadmap** — tiers + skill gap + mark per-tier progress; select/change target.
8. **AI chat** — the read-only, RBAC-bound assistant.
9. **Notifications** — nudges / approvals-awaiting (managers) / feedback requests / summary released.
10. **(Manager extras)** — my team's nudges, approve my reports' goals, act on my approval inbox, request an AI review draft for a report.

**OUT (stays on desktop/web):** succession & talent, department/calibration analytics, the org chart editor, JD library authoring, admin (users/tenant/entitlements/integrations), the audit console. These are management/governance surfaces — explicitly not mobile.

---

## 3. Architecture

- **Stack:** Expo (managed workflow) + React Native + TypeScript. React Query for server state (same as web), React Hook Form + zod for forms (same as web), Expo Router (file-based) for navigation.
- **Shared layer (extract once, import from both):** create `packages/shared/` (or a `shared/` workspace) holding the **platform-agnostic** modules lifted from `frontend/src/lib/`:
  - `api/endpoints.ts` + `api/client.ts` (the axios instance + refresh interceptor — inject the token store so web uses memory/localStorage and mobile uses SecureStore),
  - `types.ts`, `enums.ts` (roles, feature keys, status maps),
  - `errors.ts` (the error-code mapper — reuse verbatim),
  - `weights.ts` and any other pure helpers,
  - the auth state machine (refactor `AuthContext` so the *logic* is shared and only the storage + provider shell differ per platform).
  Name them explicitly so web and mobile import the same source — **drift is the enemy**.
- **Token storage:** `expo-secure-store` for access/refresh (Keychain/Keystore-backed). Never `AsyncStorage`/localStorage for tokens.
- **Same conventions as web (do not reinvent):** RBAC via `ROLE_RANK`/capabilities, feature-flag gating via `hasFeature` + the premium upsell, the full **error-code mapping** (400/401/403/404/409/422/429/503 + network) with the same calm copy, **HITL** treatment (AI is always a draft + confidence + human action), and the same 429 Retry-After / 503 "AI unavailable, manual path works" handling.
- **States everywhere:** loading skeletons, empty/first-run, error-by-code, offline (React Query cache + a clear offline banner), pending-HITL, locked-by-flag, 404-out-of-scope.
- **Push notifications:** design now, wire later — `expo-notifications` + a device-token register endpoint (thin backend add); map to the existing nudge / approval / feedback / summary events.
- **Offline:** read-only screens cache via React Query persistence; writes (record actual, give feedback, self-assessment) queue with optimistic UI + retry.

---

## 4. Reuse map — every mobile screen → existing backend endpoint

The backend already supports the whole self-service surface (verified live this
run). Endpoints are the ones the web client calls today:

| Mobile screen | Backend endpoint(s) | Notes |
|---------------|--------------------|-------|
| Login / MFA | `POST /api/auth/login`, `POST /api/auth/mfa/challenge`, `GET /api/auth/me` | `me` now returns `tenant_name`/`tenant_slug` |
| My dashboard | `GET /api/auth/me`, `GET /api/billing/my-features`, `GET /api/ai/nudges`, `GET /api/goals/?employee=me`, `GET /api/feedback/requests/mine`, `GET /api/career/roadmap` | nudges are scope-bound |
| My goals & KPIs | `GET /api/goals/`, `POST /api/goals/kpis/<id>/actuals` | record actual is own-only |
| My review + self-assessment | `GET /api/reviews/?employee=me`, `GET /api/reviews/<id>`, `POST /api/reviews/<id>/assessments` (SELF) | view finalized + submit self-assessment |
| Give 360 feedback | `GET /api/feedback/requests/mine`, `POST /api/feedback/cycles/<id>/give`, `POST /api/feedback/requests/<id>/decline` | invitation is the authorization |
| My 360 summary | **`GET /api/feedback/my-cycles`** → `GET /api/feedback/cycles/<id>/summary` | **the A1 endpoint built this run** — the discovery read mobile needs |
| My career roadmap | `GET /api/career/roadmap`, `GET /api/career/roadmaps/<id>/skill-gap`, `GET/POST /api/career/roadmaps/<id>/progress`, `POST /api/career/target` | enrich is Full-AI gated |
| AI chat | `POST /api/ai/chat` | read-only, RBAC-bound, write-blocked |
| Manager: team nudges / approvals / report goals | `GET /api/ai/nudges`, `GET /api/approvals/inbox`, `POST /api/approvals/steps/<id>/approve|reject`, `POST /api/goals/<id>/approve`, `POST /api/reviews/<id>/request-ai-draft` | manager scope |
| Notifications | reuse nudges + approvals-inbox + requests-mine counts; **push** needs a thin `POST /api/devices` token-register endpoint (the only genuinely new backend) |

**Thin backend additions mobile will need:** (1) a device-token register endpoint for push (later); (2) optionally a `goals/?employee=me` convenience already covered by scope. Everything else exists.

---

## 5. Phased build plan (mirror the web gating discipline)

Each phase: typecheck + lint + build clean **and** runs in the Expo simulator → commit + push → if a push is rejected don't force, write a BLOCKER. Write a morning report at the end of each run.

- **Phase 0 — Scaffold & shared layer.** `create-expo-app` (TS), Expo Router, React Query, RHF+zod, NativeWind (Tailwind-for-RN) wired to the **same design tokens** (palette/type) as web. Extract `shared/` (api client + types + enums + errors + auth logic) and wire web + mobile to it. SecureStore token storage. App shell + **bottom-tab nav** + auth bootstrap + the error-mapper + a theme. *Acceptance:* login works against the live API on a device via Expo Go; tokens persist securely; a protected tab 401→login.
- **Phase 1 — My dashboard.** The cockpit: score/risk, nudges, requests, roadmap snapshot. *Acceptance:* real data, all states, pull-to-refresh.
- **Phase 2 — My goals & record actuals.** List + record actual (optimistic, offline-queued). *Acceptance:* an actual posts and the score reflects after recompute.
- **Phase 3 — My review + self-assessment.** View finalized review; submit self-assessment; HITL/confidence rendering if a draft is visible.
- **Phase 4 — 360: give + my summary.** Respond to invitations; **my released summary via `/my-cycles`**; anonymity/threshold copy; suppressed-group state.
- **Phase 5 — Career.** Roadmap + skill gap + per-tier progress + target select; enrich gated by `career_roadmap` flag.
- **Phase 6 — AI chat.** Read-only assistant; grounded answers; write-blocked; out-of-scope empty.
- **Phase 7 — Manager extras.** Team nudges, approvals inbox act, approve report goals, request a report's AI review draft.
- **Phase 8 — Notifications + push.** In-app notification center from existing counts; then `expo-notifications` + the device-register endpoint.
- **Phase 9 — Hardening + release.** Tests (the shared layer is already web-tested; add RN component tests for the risky screens), accessibility, EAS build config, store assets.

---

## 6. Design

- **Mobile-first patterns:** bottom tab bar (Dashboard / Goals / Feedback / Career / More), large tap targets (≥44pt), thumb-reachable primary actions, native gestures, pull-to-refresh, sheets for forms.
- **Brand consistency:** reuse the web palette/type tokens (slate + blue, purple=AI, gold=premium, Inter) via NativeWind so web and mobile look like one product.
- **AI surfaces:** the same draft-vs-final treatment — a PENDING badge + confidence + a clear "a human decides" framing; never present AI as final.

---

## 7. Build / run / release notes (honest)

- **Dev:** Expo Go on a real phone (scan a QR) or the iOS/Android simulator — instant reload, no Xcode needed for day-to-day work.
- **Store binaries:** **EAS Build** (Expo's cloud) compiles signed iOS/Android binaries — you don't need a Mac/Xcode locally for this.
- **Accounts (only at release, not for dev):** an **Apple Developer Program** membership ($99/yr) for the App Store and a **Google Play Developer** account ($25 once) for Play. Needed only when you submit, not while building.
- **Effort:** this is a **multi-session build** (Phases 0–9), not one run. Phase 0 (scaffold + shared layer + auth) is the biggest single step because it sets up the shared package and the native plumbing; subsequent screen phases are fast because the backend + types + client already exist.

---

## 8. Open questions for Hari (safe defaults chosen)

1. **Option A vs B?** *Default: B (Expo/RN).* Switch to A only if you need something in a phone browser this week and can throw it away later.
2. **Push notifications now or later?** *Default: design now, wire in Phase 8.* Requires the one new backend endpoint (`POST /api/devices`).
3. **MFA on mobile?** *Default: support the existing TOTP challenge; add biometric unlock (FaceID/TouchID) as a convenience on top.*
4. **Offline writes?** *Default: queue record-actual / give-feedback / self-assessment with optimistic UI; everything else is read-online.*
5. **Monorepo vs separate repo?** *Default: a monorepo workspace (`/frontend` web + `/mobile` + `/shared`) so the shared layer is a real import, not a copy.* If you prefer a separate repo, publish `shared/` as a private package.
6. **Which goes first if time is short — Employee or Manager scope?** *Default: Employee self-service (Phases 1–6) first; Manager extras (Phase 7) second.*
