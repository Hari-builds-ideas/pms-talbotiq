# v1 vs v2 — the scope split (read this before changing UI)

v1 is deliberately simplified for non-expert SME users. **Nothing was deleted** — the enterprise
features are hidden behind one central switch and return in v2 with a one-line edit. The backend
endpoints, components, routes, and tests for the hidden features all still exist.

## The one switch: `frontend/src/app/v1.ts`
```ts
export const V1_HIDDEN_PATHS = new Set(["/career", "/succession", "/admin/tenant"]);
export function isHiddenInV1(to: string): boolean { … }   // prefix-aware
export const V1_HIDE_CALIBRATION = true;                  // Analytics nine-box/calibration tab
```
It is consulted in exactly four places: `app/nav.ts` (`navForRole`), the ⌘K palette
(`features/command/CommandPalette.tsx`), `app/router.tsx` (route blocks guarded), and
`features/analytics/AnalyticsPage.tsx` (the calibration tab). It is **product scope**, distinct from the
billing `hasFeature()` lever (per-tenant AI entitlement).

## Scope table
| Feature | v1 status | Where it lives |
|---|---|---|
| Dashboard (per role) | **Live** | `features/dashboard/` |
| Goals & OKRs | **Live, simplified** | `features/goals/GoalsPage.tsx` |
| Reviews (+ AI draft, HITL) | **Live** | `features/reviews/`, `apps/reviews/` |
| 360° Feedback (+ AI summary) | **Live** | `features/feedback/`, `apps/feedback/` |
| Check-ins / Recognition / Approvals | **Live** | `features/{checkins,recognition,approvals}/` |
| Employees / Org chart | **Live** | `features/org/` |
| JD Library + AI generator | **Live** | `features/jd/`, `apps/jd/` |
| Analytics (trends + status distribution) | **Live, simplified** | `features/analytics/AnalyticsPage.tsx` |
| Audit log | **Live** | `features/audit/`, `apps/audit/` |
| Admin: Users & Roles, Entitlements | **Live** | `features/admin/` |
| T-score as the headline number | **Simplified** (status leads) | `components/ScoreBar.tsx` + call sites |
| **Nine-box / calibration grid** | **Deferred to v2 (hidden)** | `components/NineBoxGrid.tsx`, `AnalyticsPage` `CalibrationTab` |
| **Succession** (+ critical roles, bench) | **Deferred to v2 (hidden)** | `features/succession/`, `apps/succession/` |
| **Career roadmaps** | **Deferred to v2 (hidden)** | `features/career/`, `apps/career/` |
| **Raw-JSON tenant config** | **Deferred to v2 (hidden)** | `features/admin/TenantConfigPage.tsx` |

## How to RE-ENABLE each deferred feature (v2)
All are one edit to `frontend/src/app/v1.ts`, then `npm run build` (+ update `app/nav.test.ts` back).
- **Career roadmaps** — remove `"/career"` from `V1_HIDDEN_PATHS`. Restores: the "Career Paths" nav item,
  the `/career` route + `CareerPage`, and the Employee `MyRoadmapTile` on the dashboard. (Backend
  `apps/career/` + endpoints were always live.)
- **Succession + nine-box** — remove `"/succession"`. Restores: the nav item, `/succession` route +
  `SuccessionPage`, the HRBP "Coverage gaps" StatCard + `SuccessionRiskTile`, the Admin "Critical roles"
  StatCard, and re-enables the dashboard succession query (it's `enabled: !isHiddenInV1("/succession")`).
- **Analytics calibration / nine-box tab** — set `V1_HIDE_CALIBRATION = false`. Restores the Calibration
  tab + `NineBoxGrid` + `useCalibration` in `AnalyticsPage.tsx` (all still present).
- **Raw-JSON tenant config** — remove `"/admin/tenant"`. Restores the "Configure" nav + `/admin/tenant`
  route + `TenantConfigPage`. (Consider building friendlier labeled toggles instead of raw JSON for v2.)

## What was SIMPLIFIED (and where the original detail still is)
- **T-score → status-first.** Per-person headline surfaces (Employee dashboard "My performance" card;
  the profile page) now lead with a plain **On track / At risk / Needs attention** badge + a 0–100
  `ScoreBar`; the raw T-score is a small "Score N/100 · 50 = team average" caption with a tooltip. The
  number itself is unchanged (from the scoring engine); it's still shown in the Analytics tables as a
  secondary detail. Component: `frontend/src/components/ScoreBar.tsx` (`performanceLabel`, `ScoreBar`).
- **Goals plain-language.** Each person's goals open with a one-line human lead ("On track this cycle · N
  goals"); per-KPI shows a progress bar + relabels ("actual"→**Progress**, "target"→**Goal**, direction →
  "Higher/Lower is better ↑/↓"); the raw weight/target detail stays on the card. `GoalsPage.tsx`.
- **Analytics.** Leads with the trend + the plain status distribution; the calibration grid is hidden
  (above). `AnalyticsPage.tsx`.

## Tests adjusted to the v1 state (coverage kept, not deleted)
- `frontend/src/app/nav.test.ts` — expects the v1 nav (no Career/Succession/Configure) + a new
  "no role sees a v1-deferred item" test. Restore the old expectations when you re-enable features.
- All hidden components still render in the a11y harness (`src/test/a11y/`) because the components remain.
