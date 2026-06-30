# Phase 1 — Dashboard build sheet (ready; executes on foundation approval)

Recompose `features/dashboard/DashboardPage.tsx` to the mockup, **wired to real data**, with
**honest metric labels** (Hari's rule: a T-score must read as a T-score — never disguised as a "/5"
or a "%"). Manager view = the mockup's reference; the other roles get the same composition shape with
their own real tiles. Reskin + recompose only; every existing query/action/AI surface stays wired.

## Honest-label rule (decides every score tile)
The product's performance metric is a **T-score** (≈50 = cohort average, sd 10) + **risk_status**
(SAFE / AT_RISK / CRITICAL). There is **no 1–5 performance rating**. The only real 1–5 is **check-in
mood**. So:
- T-score values are shown as the raw T-score with a label that says so (e.g. value **`52.3`**, hint
  **"Team avg · T-score (50 = cohort avg)"**). Never "/5", never a fake "%".
- Real percentages (goals on track, review completion) keep "%": they ARE percentages.
- Mood keeps "/5": it IS a 1–5 scale (labeled "check-in mood", not "engagement score").

## Per-tile map (tile → real source → honest label → empty/flag)

### 5 KPI cards (new `DashboardKpiCard` = StatCard + delta + `Sparkline`)
1. **Team avg score** — mean team `CycleScore.t_score` (scope-filtered). Value `52.3`; hint
   "T-score · 50 = cohort avg"; sparkline = per-cycle team mean; delta = Δ vs prior cycle ("+1.8 vs
   last cycle"). *Not "%".*
2. **Goals on track** — `goalsApi.list({cycle})` + KPI attainment; value real `%` (this is a true
   percentage); delta vs prior cycle if available. Define "on track" = KPIs meeting/exceeding target
   pace (reuse `AttainmentBar` logic).
3. **Reviews completed** — `reviewsApi.list({cycle})` → `N / M` finalized vs total + progress bar.
4. **Team mood** (N3, replaces "Engagement") — avg `checkinsApi.team()` mood, value `4.3 / 5`,
   labeled **"Team mood · check-in avg"** (mood IS 1–5 → honest). Empty if no check-ins.
5. **At-risk employees** — `aiApi.nudges()` CRITICAL/AT_RISK count (`agent2`); "—" + upgrade hint
   when the feature is off (existing pattern). Red sparkline.

### Performance Overview block
- **Average T-score + trend** — per-cycle team mean (`analyticsApi.department(me, cycle)` /
  `cyclesApi.scores`), recharts line (reuse/adapt `TrendChart`). Header value `52.3`, label "Average
  T-score"; delta "+1.8 vs last cycle". *Not "4.2/5".*
- **Score distribution donut** (`ScoreDonut`) — count of team scores **re-banded to the real metric**
  by risk/T-score range (e.g. ≥60 strong / 50–60 on-track / 40–50 watch / <40 at-risk), colored
  green/amber/red per the spec score bands. Center = real "N employees". Legend labels the T-score
  ranges, not "4.5–5.0".

### My Tasks rail (`TasksRail`) — compose REAL pending work
Merge, newest/most-urgent first: `approvalsApi.inbox` (approve steps — have due dates → priority by
proximity) + `reviewsApi.list` active states (finalize/approve) + `feedbackApi.requestsMine` PENDING
(give feedback) + `aiApi.staleGoals` (nudge). Each row links to where you act. Priority badge derived
from due-date proximity where present, else omitted. (No "1:1 meeting" tasks — no source; never
invented.) Empty state = "You're all caught up."

### Lower zone
- **Team Performance table** — `cyclesApi.scores(cycle)` (T-score + risk) + person role + per-person
  goals (`goalsApi.list({employee})` → N/M on track). Columns: Employee · Role · **T-score** (labeled
  header) · Trend (Δ vs prior cycle, ↑/↓; empty if no prior) · Goals (N/M) · → profile (N2). Score is
  the raw T-score; header says "T-score".
- **Team Competency radar** — **no backing data** → on-brand **empty state** ("Competency scoring
  isn't available yet"), styled like the mockup card. Not fabricated.
- **Announcements** (N4) — a single **real active-cycle status** line from `cyclesApi.list` /
  `feedbackApi.cycles` (e.g. "Q2 review cycle is open · reviews due {date}"); empty if none. No static
  marketing copy.

### Header
- Greeting "Good morning, {first name}" (`me.display` + client time-of-day) + subtitle. **Period
  selector** = real cycle picker (`cyclesApi.list`; each cycle = a period); default latest/active.
  Date = client date.

## New components (additive, spec tokens, recharts brand-green)
`Sparkline` (mini line), `ScoreDonut` (donut + center count), `DashboardKpiCard` (StatCard + delta +
sparkline), `TasksRail`, `AnnouncementsRail`, `CompetencyRadarCard` (renders radar only with real
data, else empty state). Reuse `TrendChart`, `StatusBadge`, `PersonName`, `EmptyState`, `Panel`.

## Resolved (backend-confirmed)
- **`cyclesApi.scores(cycle)` is team-scoped** (`CycleScoresView`, `VIEW_TEAM_SCORES`,
  `apps/cycles/views.py:115`): MANAGER → reporting subtree + self; HRBP/ADMIN → full tenant. So this is
  the right source for the KPI aggregate, the distribution donut (count + bands), and the Team table.
- **Managers CANNOT list cycles** — `GET /cycles/` needs `MANAGE_CYCLES` (HRBP+/Admin,
  `apps/cycles/views.py:33`). So derive the active cycle from **team goals** (`goalsApi.list` → manager
  scope returns the team's goals → `results[0].cycle`), exactly like the employee cockpit derives from
  own goals. The period selector for a manager reflects the derived cycle(s), not a `/cycles/` call.
- **Cross-cycle deltas** ("vs last quarter", the table Trend column) need a prior cycle id; since
  managers can't list cycles, the delta **degrades to an empty/neutral state** when no prior cycle is
  derivable — honest, never fabricated. (HRBP/Admin can list cycles → can show the trend.)

## Confirm-at-build (minor)
- `CycleScore` serializer fields (t_score, risk_status, employee name) — read `shared/types.ts` at
  build to bind the table/KPI columns exactly.
- The T-score band cut points for the donut (pick sensible, label them clearly as T-score ranges).

## Gate
tsc/lint/build green + vitest pass; keep all existing dashboard queries/actions; commit+push; recreate
container; STOP for Hari's visual approval before Phase 2 (Goals).
