# MOBILE_MOCK_ADAPTATION.md — porting the `PMS_MOBILE` mock onto our real Expo app

> Step-1 exploration + plan. **No app code changed yet** — this is the plan to review
> before the Step-2 adaptation.

## 1. What the mock is

`PMS_MOBILE` lives at **`/Users/hari/Developer/PMS_MOBILE`** (NOT the repo root, and
NOT the in-repo `Enterprise AI Performance Management/` — that one is a separate
Figma export for the *web* Admin Hub; ignored here).

- **Stack:** a **Lovable-generated web React app** — TanStack Start + TanStack Router
  (file routes) + **Vite + Tailwind v4** (`@tailwindcss/vite`, oklch CSS vars) +
  shadcn/Radix + lucide-react + recharts + react-hook-form + zod + sonner. **It is
  NOT React Native / Expo** — it's a mobile-*styled* web app (rendered inside a CSS
  "phone-frame" on desktop). All data is static (`src/lib/pms-data.ts`).
- **Role:** the **design source-of-truth for look & flow** only. We port its visual
  language + IA into our real Expo app (NativeWind/RN); we do **not** copy its code
  or its fake data — our app keeps the real shared API client, auth, RBAC/flags, HITL.

## 2. Design tokens to adopt (oklch → hex finalised in Step 2)

Indigo primary (hue 258) on a cool near-white / deep-navy base, **Inter**, radius
**14px**, **light + dark** themes. Maps almost 1:1 to our existing web indigo.

| token | light (oklch → ~hex) | dark (~hex) |
|---|---|---|
| primary | `0.48 0.18 258` → ~`#4B49D0` | `#9B97F0` |
| primary-soft / accent | `0.94 0.04 258` → ~`#E7E7FB` | `#2C2C53` |
| background | `0.985…250` → ~`#FAFAFC` | `#13151E` |
| foreground | `0.18…250` → ~`#1C2030` | `#F5F6FA` |
| surface / card | `#FFFFFF` | `#1E212C` |
| surface-2 | ~`#F1F2F6` | `#262A36` |
| muted-foreground | ~`#71758A` | ~`#A6A9B8` |
| border | ~`#E3E5EC` | ~`#363A47` |
| success | `0.62 0.15 155` → ~`#1F9D6B` | `#3CC98C` |
| warning | `0.78 0.15 75` → ~`#E0A33A` | `#E7B85C` |
| destructive | `0.6 0.22 25` → ~`#E5484D` | `#F06A6E` |

Radius scale: `sm/md/lg/xl/2xl/3xl` around 14px (cards use `rounded-2xl`). Font Inter
(load `@expo-google-fonts/inter` in Step 2; system fallback meanwhile).

## 3. Components / layout language to port (into NativeWind RN primitives)

From `src/components/pms/`: **Card** (rounded-2xl, border, bg-card, soft shadow),
**Badge** (pill, tones neutral/primary/success/warning/danger), **Progress** (h-1.5
rounded track + colored bar), **Avatar** (initials, hashed color), **AppHeader**
(sticky: title 17px + subtitle, optional back chevron, notifications bell w/ dot,
ThemeToggle), **BottomNav** (5 tabs, active = filled pill), plus `SectionHeader`
and `ActionRow` patterns from the dashboard. These become RN components
(`View/Text/Pressable` + NativeWind) — **same look, RN under the hood.**

## 4. Screen-by-screen mapping (mock → our screen → REAL endpoint)

| Mock route | Our screen | Real endpoint(s) | Notes |
|---|---|---|---|
| `index` | **Login** | `authApi.login` / `mfaChallenge` / `me` | restyle to mock (gradient, icon inputs, MFA note). Real password+MFA only. |
| `app.index` | **Home / Dashboard** | `me`, `cycles.myScore`, `goals.list({employee})`, `feedback.requestsMine`, `ai.nudges`, `career.roadmap` | hero card = real cycle score/risk; KPI grid + sections from real data |
| `app.goals` | **Goals** | `goals.list`, `goals.recordActual` | tabs Active/Completed/Drafts; record actuals (9.1) |
| `app.assessment` | **My Review + self-assessment** | `reviews.detail`, `reviews.assessments`, `upsertAssessment` | HITL/confidence preserved (9.2) |
| `app.feedback` | **Feedback** | `feedback.requestsMine` / `give` / `myCycles`→`summary` | tabs Received/Given/Requests; anonymity copy (9.3) |
| `app.insights` | **AI** tab | `ai.nudges`, `ai.chat` | real nudges + the read-only chat assistant — NOT a faked "AI summary" |
| `app.approvals` | **Approvals** (manager) | `approvals.inbox`, approve/reject, `goals.approve` | manager-only; RBAC-gated (9.6) |
| `app.notifications` | **Notifications** | derived real counts (nudges/approvals/requests/summaries) | in-app from existing data (9.7) |
| `app.more` | **More** | `me`, `billing.myFeatures`, `logout` + links | identity, features, sign-out, + Career/Review/Approvals/Notifications links |
| (no mock screen) | **Career** (via More) | `career.roadmap` / `progress` / `setProgress` | our planned screen (9.4); reached from More |
| `app.meetings` | **— OMITTED** | none | no backend for 1:1s → not built (see D-decision; no fake screens) |

## 5. Reconciliation decisions (safe defaults — will log in DECISIONS.md)

1. **Bottom tabs adopt the mock's IA:** **Home · Goals · Feedback · AI · More**
   (replacing my current Dashboard/Goals/Feedback/Career/More). Career, Review,
   Approvals, Notifications become stacked screens reached from More / Home cards /
   the header bell — matching the mock.
2. **"AI" tab = real assistant, not a fake summary.** The mock's "AI Insights"
   (summary/strengths) has no backing endpoint; fabricating it would violate
   real-wiring-only. The AI tab shows real **nudges** + the **chat** assistant
   (`ai.chat`), styled like the mock's insights cards.
3. **Meetings/1:1s: omitted** — no backend exists; we don't ship mock-only screens.
   The dashboard's "Upcoming 1:1s" section is replaced with a real section (pending
   feedback / roadmap snapshot); the More "1:1 Meetings" item is dropped.
4. **Login: real password + MFA only.** Styled exactly like the mock (gradient, icon
   fields, "keep me signed in", MFA note). **SSO + Biometric** buttons from the mock
   are deferred (not wired) — shown disabled-with-"soon" or omitted (default: omit to
   avoid dead buttons).
5. **KPI grid uses only real metrics** we have (cycle score, goal-completion, pending
   feedback, nudge count). Mock-only KPIs (Peer Recognition, 1:1 Adherence) are
   dropped or swapped for real ones.
6. **Dark mode adopted:** NativeWind `dark:` variants + a ThemeToggle in the header/More,
   persisted (SecureStore/async), defaulting to system. (Nice-to-have; light is the baseline.)

## 6. What the mock has that we don't / vice-versa
- **Mock has, we add (look):** the cohesive token system, the hero cycle card, KPI
  grid, section rhythm, pill tabs, dark mode, polished login.
- **Mock has, we DON'T build:** 1:1 meetings (no backend), the fabricated AI summary,
  SSO/biometric (deferred).
- **We have, mock doesn't:** real auth + refresh + SecureStore, RBAC/feature-flag
  gating, HITL/confidence treatment, the full error-by-code/empty/offline states,
  Career (roadmap), and every screen wired to the verified backend.

## 7. Plan (Step 2 — phased, each "runs in Expo SDK 54" then commit; STOP for device check)

- **8.2b — Design system + shell restyle:** port tokens into `tailwind.config.js`
  (+ Inter, dark mode), build the RN primitives (Screen, Card, Badge, Progress,
  Avatar, AppHeader, BottomNav), re-skin the tabs to **Home/Goals/Feedback/AI/More**,
  and **restyle Login to match the mock** (keeping the real password+MFA flow).
  Keep SDK 54, the `@shared` Metro resolver, SecureStore. → re-scan checkpoint.
- **8.4 — Home/Dashboard** in the mock's layout, **real data** (hero score, KPIs,
  pending, goals, feedback, AI banner). → checkpoint.
- **BUILD_9 (9.1–9.7)** — Goals, Review+self-assessment, Feedback, AI (nudges+chat),
  Career, Approvals (mgr), Notifications — each in the mock's look on real endpoints,
  with all states. Meetings omitted. → checkpoint per screen.
- **9.8 — hardening:** offline banner/queued writes, RN tests for risky screens, dark
  mode polish, full live pass.

Invariants held throughout: SDK 54 (your Expo Go), `pmsshared` resolution, SecureStore,
the real shared client/auth/RBAC/HITL, no mock-only screens, commit+push per phase,
device run as the acceptance bar.
