# MOBILE READINESS GATE — Talbotiq PMS (BUILD_5 5.7)

A check + a GO/NO-GO for starting the mobile series (Option B: React Native +
Expo, per `MOBILE_BUILD_PLAN.md`). **This is NOT the mobile build** — mobile is a
separate series that starts only AFTER Hari has reviewed the finished web app.

## Recommendation: **GO** (after Hari's web review)

The backend self-service surface mobile needs exists, is RBAC/scope-bound, and is
now performance-hardened (N+1-free + cached + async-AI + atomic-limits from builds
1–4). The shared TypeScript layer is platform-agnostic and cleanly extractable.
One genuinely new backend endpoint is needed (device-token register for push),
and it's a known LATER add — not a blocker for scaffolding.

## Prerequisite endpoints — verified present + wired

Every mobile self-service screen maps to an existing, wired endpoint
(`frontend/src/lib/api/endpoints.ts`), each made O(1) / cached by builds 1 & 4:

| Mobile screen | Endpoint(s) | Status |
|---|---|---|
| My dashboard | `GET /auth/me`, `GET /billing/my-features`, `GET /ai/nudges`, `goals.list({employee})`, `feedback.requestsMine`, `career.roadmap` | ✅ all present; nudges scope-bound |
| My goals + actuals | `goals.list`, `goals.recordActual` (`/goals/kpis/<id>/actuals`) | ✅ optimistic + 409-aware (BUILD_4) |
| My review + self-assessment | `reviews.detail`, `reviews.upsertAssessment`, `reviews.assessments` | ✅ HITL + state machine intact |
| Request AI draft (manager) | `reviews.requestAiDraft` → poll `aiJobsApi.get` | ✅ async (BUILD_2) — poll pattern reusable |
| Give 360 + my summary | `feedback.give`, `feedback.myCycles` (`/feedback/my-cycles`) → `feedback.summary` | ✅ the discovery read exists |
| Career roadmap + progress | `career.roadmap`, `career.progress`, `career.setProgress` | ✅ advisory; progress upsert |
| Chat / nudges | `ai.chat`, `ai.nudges` | ✅ read-only, RBAC-bound, write-blocked |

**Known thin gap (LATER, not a blocker):** push notifications need a
`POST /api/devices` device-token register endpoint (the only genuinely new
backend). The events to push already exist as data (nudges, approvals-inbox,
feedback-requested, summary-released) — design now, wire at the push phase.

## Shared layer — extractable, platform-agnostic (list; do NOT move yet)

These `frontend/src/lib/` modules are framework-agnostic and should lift into a
`shared/` (or `packages/shared/`) workspace so web + mobile never drift:

- `lib/api/endpoints.ts` — the typed client (1:1 with the backend).
- `lib/api/client.ts` — the axios instance + JWT refresh interceptor. **Inject the
  token store** (web: memory/localStorage; mobile: `expo-secure-store`) so the
  refresh logic is shared and only storage differs.
- `lib/types.ts`, `lib/enums.ts` — the type + label/enum layer.
- `lib/errors.ts` — the kind-aware error-code mapper (400/401/403/404/409/422/429/503).
- RBAC/feature-flag helpers (`ROLE_RANK`/`hasFeature`, in `lib/auth/`).
- The auth state machine — refactor `lib/auth/AuthContext` so the LOGIC is shared
  and only the storage + provider shell differ per platform.
- The async-AI polling hooks (`lib/hooks/useAIJob.ts`, `useAIAction.ts`) — the
  fire→poll→react pattern is reusable on mobile.

UI components (shadcn/Tailwind) do NOT extract — mobile uses NativeWind/RN
primitives against the same design tokens.

## Verdict

**GO to scaffold the mobile series** (Expo + the shared-layer extraction in
Phase 0) — but only after Hari has reviewed the finished web app, per the plan.
No prerequisite is missing that would block Phase 0; the device-register endpoint
is a small, well-understood add at the push phase.
