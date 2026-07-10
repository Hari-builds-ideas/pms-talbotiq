# PROGRESS_V1 — unattended simplify → deploy → handoff run

Branch `hari/agent-ui-v2`. Working A→B→C→D per `V1_MASTER.md`. Iron rules: never break a working feature,
real data only, deferred features HIDDEN-not-deleted (+ how to re-enable), tests green + commit per change,
free-tier only. Ambiguities → simplest choice for a non-expert + logged under QUESTIONS. Log updated after
each phase; final `V1_HANDOFF_REPORT.md` at the very end.

## Status
- [x] **A — Simplify** — done. Deferred features hidden (code kept), T-score demoted, goals plain lead, reseeded. 4 commits (A1–A4). tsc + 118 vitest green.
- [ ] **B — Polish** (favicon, logo, premium login, brand consistency, calm empty states)
- [ ] **C — Deploy demo** (render.yaml + vercel.json + DEPLOY_DEMO.md; wire Gemini provider; free tier)
- [ ] **D — Handoff docs** (docs/handoff/ — 8 docs, code-grounded)

## Log
### Setup
- Read `V1_MASTER.md` + the 4 build files. Confirmed: no Gemini provider yet (Phase-C code gap to fill by
  mirroring `apps/ai/openai_provider.py`); no `render.yaml`/`vercel.json` yet. Recon of the Phase-A
  frontend surface in progress.

### Phase A — Simplify (done)
- **A1** `feat(v1): hide career, succession, calibration, raw tenant-config` — added central
  `frontend/src/app/v1.ts` (product-scope switch, NOT the billing lever); nav, ⌘K palette, router
  (route blocks guarded, imports/components kept), and AnalyticsPage calibration tab all consult it.
- **A2** `feat(v1): remove succession + career tiles from dashboards` — HRBP "Coverage gaps" +
  SuccessionRiskTile, Admin "Critical roles", Employee roadmap tile guarded; succession query disabled.
- **A3** `feat(v1): demote T-score behind plain status + 0-100 bar` — new `ScoreBar` + `performanceLabel`
  (On track / At risk / Needs attention). Employee "My performance" card + profile lead with the plain
  status; T-score is a "Score N/100 · 50 = team average" caption with a tooltip.
- **A4** `feat(v1): plain per-person lead line on Goals` — one-line human answer above the OKR detail;
  builds on existing Progress/Goal relabels + StatusBadge + AttainmentBar.
- Reseeded ACME (211 people) so every kept screen looks full.

## QUESTIONS (for Hari — decided the simplest thing and kept going)
- **Goals lead line:** spec suggested "On track to hit 3 of 4 goals." A precise "X of Y goals on track"
  needs per-goal attainment threaded to the person header (not currently there). I used the simplest
  honest lead — the person's overall status in words + goal count ("On track this cycle · 2 goals").
  Refinement (per-goal Ahead/On-track/Behind counts) is a small follow-up if you want the exact phrasing.
- **T-score demotion scope:** demoted on the per-person headline surfaces (employee dashboard card,
  profile). The Analytics tables and the manager team-table keep the T-score as a *secondary* column
  (they already show the StatusBadge alongside) — those are "insights" screens where the number is
  acceptable as detail. Flag if you want it demoted there too.
- **Test note:** the frontend suite (118) is green; a stray `npx vitest` at repo-root (wrong cwd) showed
  2 failures from a non-frontend config — unrelated to these changes; will confirm during the C/D pass.

## Hidden features & how to re-enable (v2)
All hidden via `frontend/src/app/v1.ts` — **code, routes, endpoints, components and tests are all
retained.** To restore a feature for v2:
- **Career roadmaps** — remove `"/career"` from `V1_HIDDEN_PATHS` in `app/v1.ts`. (Nav item, `/career`
  route + `CareerPage`, and the Employee `MyRoadmapTile` return automatically.)
- **Succession + nine-box + critical roles** — remove `"/succession"`. (Nav, `/succession` route +
  `SuccessionPage`, HRBP "Coverage gaps" + `SuccessionRiskTile`, Admin "Critical roles", and the
  succession dashboard query all re-enable.)
- **Analytics calibration / nine-box tab** — set `V1_HIDE_CALIBRATION = false`. (`CalibrationTab` +
  `NineBoxGrid` + `useCalibration` are still in `AnalyticsPage.tsx`.)
- **Raw-JSON tenant-config** — remove `"/admin/tenant"`. (Nav "Configure" + route + `TenantConfigPage`.)
Everything is one edit to `app/v1.ts`; no code was deleted. Full detail in docs/handoff/V1_VS_V2.md (Phase D).
