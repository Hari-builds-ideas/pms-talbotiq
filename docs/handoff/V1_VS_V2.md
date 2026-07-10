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
| Goals & OKRs | **Live, REDESIGNED** (%+bar per goal) | `features/goals/GoalsPage.tsx`, `lib/goalProgress.ts`, `components/ProgressBar.tsx` |
| Reviews (+ AI draft, HITL) | **Live** | `features/reviews/`, `apps/reviews/` |
| 360° Feedback (+ AI summary) | **Live** | `features/feedback/`, `apps/feedback/` |
| Check-ins / Recognition / Approvals | **Live** | `features/{checkins,recognition,approvals}/` |
| Employees / Org chart | **Live** | `features/org/` |
| JD Library + AI generator | **Live** | `features/jd/`, `apps/jd/` |
| Analytics (trends + status distribution) | **Live, simplified** | `features/analytics/AnalyticsPage.tsx` |
| Audit log | **Live** | `features/audit/`, `apps/audit/` |
| Admin: Users & Roles, Entitlements | **Live** | `features/admin/` |
| **T-score** (cohort statistic) | **Removed from the v1 UI (hidden)** | flag `V1_HIDE_TSCORE` in `app/v1.ts`; backend `CycleScore.t_score` + engine untouched |
| **Nine-box / calibration grid** | **Deferred to v2 (hidden)** | `components/NineBoxGrid.tsx`, `AnalyticsPage` `CalibrationTab` |
| **Succession** (+ critical roles, bench) | **Deferred to v2 (hidden)** | `features/succession/`, `apps/succession/` |
| **Career roadmaps** | **Deferred to v2 (hidden)** | `features/career/`, `apps/career/` |
| **Raw-JSON tenant config** | **Deferred to v2 (hidden)** | `features/admin/TenantConfigPage.tsx` |

## How to RE-ENABLE each deferred feature (v2)
All are one edit to `frontend/src/app/v1.ts`, then `npm run build` (+ update `app/nav.test.ts` back).
- **T-score numbers** — set `V1_HIDE_TSCORE = false`. Every T-score display is guarded by this flag
  (`{!V1_HIDE_TSCORE && …}` or `V1_HIDE_TSCORE ? <plain> : <t-score>`), so flipping it restores the
  numbers on the profile, employee cockpit, analytics (individual trend/table + department mean/median),
  the manager dashboard (avg-score card, big number, team column) and the review evidence panel. The
  backend `CycleScore.t_score` and the scoring engine were never touched. *Note:* the profile and
  analytics **trend charts** plot progress % in v1; the T-score data source for those two charts is a
  one-line swap documented in the code (they don't auto-revert with the flag) — everything else does.
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

## What was REDESIGNED / SIMPLIFIED (and where the original detail still is)
- **Goals/OKR — real redesign** (not a re-tag; an earlier tag-only attempt was rejected). Each goal now
  leads with a big **% complete**, a **colored progress bar** (green on track / amber behind / red at
  risk), and a one-word status; the person line reads *"N of M goals on track — X% overall"*. **All**
  technical detail — weight ("How much this counts"), target ("Goal"), the KPI breakdown, direction,
  cycle dates, the approve button — moved behind **Show details**. The pattern copies Lattice/15Five/
  Betterworks (see `docs/GOALS_RESEARCH.md`). The % is computed in `lib/goalProgress.ts` to mirror the
  backend scoring engine; the shared bar is `components/ProgressBar.tsx`. No backend/data-model change —
  KPIs, weights, targets and the create/record/approve flows are all unchanged, just relocated.
- **T-score — removed from the v1 UI** (see the table + re-enable above). v1 shows plain goal progress %
  and status everywhere the T-score used to appear; the statistic itself is intact in the backend.
- **Analytics.** Leads with the per-cycle **progress %** trend + a plain **On track / Behind / At risk**
  distribution; the calibration/nine-box grid and the mean/median T-score are hidden. `AnalyticsPage.tsx`.

## Tests adjusted to the v1 state (coverage kept, not deleted)
- `frontend/src/app/nav.test.ts` — expects the v1 nav (no Career/Succession/Configure) + a new
  "no role sees a v1-deferred item" test. Restore the old expectations when you re-enable features.
- All hidden components still render in the a11y harness (`src/test/a11y/`) because the components remain.
