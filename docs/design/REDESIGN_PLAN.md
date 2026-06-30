# PMS Frontend Redesign Plan — Mockup × TalbotIQ Spec × TQ Constitution

**Status:** PROPOSAL — awaiting Hari's approval. No screens built yet.
**North star:** the attached **dashboard mockup** — match it. **Where the mockup and the Constitution
conflict, the mockup wins.**
**Scope:** Visual + IA redesign of the **existing, working web frontend** (`frontend/`, served on
`:8080`). Reskin + recompose only.
**Out of scope (do NOT touch):** backend, APIs, the AI gateway, agentic-chat behavior, RBAC matrix,
auth/SSO, tenant isolation, HITL gates, data contracts/shapes. Every existing button, data fetch, AI
feature, and the chat keeps working **exactly** as today.
**Iron rule:** the dashboard renders **REAL data from existing endpoints**. The mockup's sample
names/numbers (Arjun, 87%, Priya Sharma, 4.2/5, the radar, the announcements) are **layout
placeholders only** — never hardcoded. Each tile wires to its real source; **no real source → proper
empty state + a flag in `HARI_ATTENTION_NEEDED_redesign_dashboard_data.md` → never fabricated.**

---

## 0. Inputs & how the three combine

I read all three inputs, the `frontend-design` skill, and the **actual code** (`tailwind.config.ts`,
`styles/globals.css`, `app/shell/*`, `nav.ts`, `components/ui/*`, `features/dashboard/DashboardPage.tsx`,
`shared/src/api/endpoints.ts`, the 18 route screens) + the prior RESKIN / RW history.

| Input | Governs |
|---|---|
| **Dashboard mockup** (attached) | The visual + layout **north star** — the exact thing to match. **Wins over the Constitution on conflict.** |
| **TalbotIQ Design Spec** | The **visual language / tokens** the mockup is built from (green `#0d5c3a`, white 16px cards, soft shadow ladder, Inter + JetBrains Mono, `.card/.badge`/Button/Input look, lucide stroke-2, 150ms motion, recharts in brand green + score-banded green/amber/red). |
| **TQ Constitution** | **Composition discipline** — one hero, narrative-over-raw-number, no nested cards, real empty/loading/error states, per-role IA, eye-path. Applied **except where the mockup overrides.** |

**The lever that makes this fast & safe:** the app is already 100% token-driven (`hsl(var(--x))` in
`globals.css`). The prior RESKIN reskinned the *whole app in one commit* by re-pointing those
variables. I do the same → the green/light system lands app-wide in the foundation phase, all ~44
files still compiling. I keep the HSL-variable *mechanism*; the spec's hexes are the *targets*.

**Starting point today:** indigo `#5B5BD6` + **near-black dark sidebar** + Plus Jakarta Sans, shadcn/ui
+ Radix kit, recharts, per-role nav already cut by the RW track. This redesign replaces the *visual*
direction and re-groups the sidebar to the mockup; it preserves all wiring + per-role visibility.

---

## (a) Token & component map → TalbotIQ spec + mockup

### Color — re-point the HSL variables in `globals.css` (one edit → whole-app reskin)
Targets = TalbotIQ hexes as HSL channels; exact channels **WCAG-AA-verified in the foundation phase**
(subtle-bg + darkened-tone text ≥ 4.5:1, the discipline already in the file).

| Variable | Today | → Target | Hex |
|---|---|---|---|
| `--background` | `240 20% 96%` | `138 24% 95%` | `#eff5f0` canvas |
| `--foreground` | `240 25% 6%` | `222 47% 11%` | `#0f172a` |
| `--card` | `0 0% 100%` | `0 0% 100%` | white |
| `--primary` / `--ring` | indigo | `154 75% 21%` | **`#0d5c3a`** |
| `--accent` (hover tint) | indigo tint | `150 50% 96%` | `#f0faf5` |
| `--border` / `--input` | `240 14% 90%` | `140 18% 89%` | `#dde8e0` |
| `--input-background` | filled | `0 0% 100%` | white inputs (spec) |
| `--success` | emerald | `142 76% 36%` (+AA) | `#16a34a` |
| `--warning` / `--premium` | amber/gold | `32 95% 44%` (+AA) | `#d97706` |
| `--danger` | red | `0 72% 51%` (+AA) | `#dc2626` |
| `--info` | cyan | `221 83% 53%` (+AA) | `#2563eb` |
| `--ai` | loud violet | quiet/on-brand retune | — (both docs: AI is invisible) |
| `--sidebar*` | near-black | **light** surface, green active | per mockup |
| `--chart-1` | indigo | `154 75% 21%` | brand green primary series |
| `--chart-2..5` | rainbow | on-brand greens + amber + slate | quiet |

**Score bands (recharts + score text)** per spec `scoreColor()`: **≥75 green · ≥55 amber · else red** —
reuse `success`/`warning`/`danger`; no new tokens. (NB scale caveat — see the data-gaps flag.)

### Type / radius / shadow / motion / icons
- **Fonts:** `@import` + `fontFamily` → **Inter** (sans) + **JetBrains Mono** (mono). (Inter = the
  app's pre-RESKIN face; this is a revert.)
- **Radius:** `--radius: 0.625rem` (**10px**) → buttons/inputs `rounded-lg`; cards/modals `rounded-2xl`
  (**16px**); badges/pills full.
- **Shadow:** re-point the `boxShadow` ladder to the spec's feather-soft values (card rest → `md` hover
  → `xl` modals); add the green `primary-sm/md` button-hover glow.
- **Motion:** keep calm ~150–200ms (already the app's discipline). `prefers-reduced-motion` respected.
- **Icons:** already **lucide stroke-2** — matches the spec. No change.

### Component map — port the look onto the existing primitives (no parallel kit; the RESKIN approach)
Restyle each shadcn/custom primitive to the TalbotIQ look, **preserving every prop/variant**:
`Button` (green fill, 10px, soft green focus glow) · `Card`/`Panel` (white, 16px, `#dde8e0` border,
soft shadow; **no nested cards**) · `Badge`/`StatusBadge` (pill tones) · `Input/Textarea/Select` (white,
green focus ring, uppercase field-label) · `Tabs` (green pill tabs) · `Dialog/Sheet` (16px, `shadow-xl`,
blur scrim) · `Table`/`DataTable` (uppercase muted header, hover rows, tabular-nums) · `Toaster`
(white/soft) · `TrendChart`/`NineBoxGrid`/`CoverageHeatmap` (brand-green recharts + score bands) ·
`StatCard` (the mockup KPI card: label → big value → delta + sparkline) · `Hitl`/`AIJobBanner` (quiet
AI) · `Avatar`/`PersonName` (green initials) · `PageHeader` (green kicker → bold title → muted sub +
right action — the mockup greeting + period selector).

**New primitives the mockup needs (additive, built from spec tokens):** `Sparkline` (tiny recharts line
in the KPI cards), `ScoreDonut` (recharts donut for Score Distribution), `CompetencyRadar` (recharts
radar — *only rendered when real data exists; otherwise empty state*), `TasksRail`, `AnnouncementsRail`.

---

## (b) Sidebar IA per role (mockup's sections → real routes)

Adopt the mockup's shell verbatim: **left sidebar**, logo lockup top-left, sectioned groups, brand-green
active item, **Quick Actions pinned bottom-left**; top bar = global search (⌘K) · notifications · help ·
user identity+role. **Principle kept from RW + Constitution:** a role sees **only** what it can use —
**no dead links**; hiding is UX, server RBAC unchanged (defense in depth).

The mockup lists several **aspirational nav items with no backing route** (1:1 Meetings, PIP &
Improvement, Teams, Skills & Competencies, Reports, Engagement, Benchmarks). Per the no-dead-links rule
I **do not** create routes for them — they're flagged (see the data-gaps doc; decision **N1**). Below
maps the mockup's 4 sections onto the **real** routes, marking each item's lowest role.

| Section (mockup) | Item → route | Lowest role | Note |
|---|---|---|---|
| *(top)* | **Dashboard** `/` | Employee | |
| **PERFORMANCE** | Goals & OKRs `/goals` | Employee | mockup "Goals & OKRs" |
| | Reviews `/reviews` | Employee | |
| | Feedback `/feedback` | Employee | |
| | Check-ins `/checkins` | Employee | ← stands in for mockup "1:1 Meetings" (closest real feature) |
| | Recognition `/recognition` | Employee | real route; not in mockup — kept here |
| | Approvals `/approvals` | Manager | manager action; mockup omits — placed here |
| | ~~1:1 Meetings, PIP & Improvement~~ | — | **no route → flag N1** |
| **TALENT** | Employees `/org` | Manager | Org/people surface = mockup "Employees" |
| | Career Paths `/career` | Employee | |
| | Succession `/succession` | HRBP | Constitution "Advanced" set, correctly placed (not a "More" dump) |
| | JD Library `/jd` | HRBP | real route; placed in Talent |
| | ~~Teams, Skills & Competencies~~ | — | **no route → flag N1** |
| **INSIGHTS** | Analytics `/analytics` | Manager | |
| | Audit `/audit` | HRBP | real route; placed in Insights |
| | ~~Reports, Engagement, Benchmarks~~ | — | **no route → flag N1** |
| **SETTINGS** | Configure `/admin/tenant` | Admin | mockup "Configure" |
| | Integrations `/admin/integrations` | Admin | |
| | System Settings `/admin/users` (+ Entitlements `/admin/billing`) | Admin | mockup "System Settings" |
| *(bottom)* | **Quick Actions** (button) | Employee | opens existing create flows (new goal, give recognition, check-in…) — composed from real actions, role-filtered |

**Per role, the sidebar shows only its slice** (Employee: Dashboard + the Employee-level PERFORMANCE/
TALENT items; Manager adds Approvals/Analytics/Employees; HRBP adds Succession/JD/Audit; Admin adds
SETTINGS). Identical visibility to today's correct RW cut — only chrome + grouping change. Contained to
`app/shell/*` + `nav.ts`; **no route/RBAC/backend change.**

---

## (c) Dashboard per-tile data-source map  ← the crux

The mockup is a **manager/leader** dashboard. Below, each tile → its real source, or → empty-state +
flag. **No tile is fabricated.** ✅ real/composable · ⚠ flag (no source or metric/scale gap). Full
detail + proposed resolutions in `HARI_ATTENTION_NEEDED_redesign_dashboard_data.md`.

| Tile (mockup) | Real source | Verdict |
|---|---|---|
| Greeting "Good morning, {name}" | `authApi.me` (`me.display`) + client time-of-day | ✅ (already wired) |
| Date · Period selector "This Quarter" | client date · `cyclesApi.list` (period = real cycle) | ✅ (period→cycle mapping to confirm) |
| **KPI: At Risk Employees** | `aiApi.nudges` CRITICAL/AT_RISK count (`agent2`); "—" + upgrade when off | ✅ (already in Manager cockpit) |
| **KPI: Reviews Completed N/M** | `reviewsApi.list({cycle})` → finalized vs total | ✅ composable |
| **KPI: Goals On Track %** | `goalsApi.list({cycle})` + KPI attainment (existing `AttainmentBar` logic); `aiApi.staleGoals` for off-track | ✅ composable (pin the "on track" formula) |
| **KPI: Team Performance %** | `cyclesApi.scores(cycle)` team aggregate | ⚠ metric: real scores are **T-scores, not %** — adapt label/derivation, don't invent a % |
| **KPI: Engagement Score /5** | *no engagement feature* | ⚠ **no source** — propose: avg team **check-in mood** (`checkinsApi.team`, real 1–5) **or** empty; Hari decides |
| **Perf Overview: Avg Score + trend** | `analyticsApi.department(head,cycle)` / per-cycle `cyclesApi.scores` (Apr–Jun = cycles) | ✅ data real — ⚠ **scale**: show real **T-score**, not a 1–5 rating (none exists) |
| **Perf Overview: Score Distribution donut** | `cyclesApi.scores(cycle)` (count + buckets) | ✅ data real — ⚠ **re-band** to real metric (T-score ranges / risk_status), not the mockup's 1–5 bands |
| **My Tasks rail** | compose real pending: `approvalsApi.inbox` + `reviewsApi.list` (active) + `feedbackApi.requestsMine` + `aiApi.staleGoals`; priority from due-date proximity | ✅ composable (1:1-meeting tasks have no source → simply not shown, never invented) |
| **Team Performance table** | `cyclesApi.scores(cycle)` (score + risk) + person role + `goalsApi.list({employee})` (goals N/M); Trend = delta vs prior cycle | ✅ composable — score shown as real T-score; trend empty if no prior cycle |
| **Team Competency radar** | *no competency-rating feature on these axes; no company-avg* | ⚠ **no source → empty state**, flagged; do **not** fabricate the radar |
| **Announcements rail** | *no announcements feature* | ⚠ **no source** — propose: empty **or** a single real "active cycle" status line from `cyclesApi`/`feedbackApi.cycles`; Hari decides |
| Top bar: global search | `orgApi.search` (the ⌘K palette already does this) | ✅ (already wired) |
| Top bar: notifications badge | *no notifications endpoint* | ⚠ **no source** — propose: compose a count from pending approvals + feedback + reviews, **or** hide the badge; Hari decides |
| Top bar: identity + role | `authApi.me` | ✅ |

---

## (d) Screen-by-screen build order

**Per screen:** match the mockup's visual language + the Constitution's composition; keep every data
fetch / action / AI surface / chat wired to **real** data; `tsc`+`lint`+`build` green + vitest passing;
commit + push; recreate the frontend container; **STOP, tell you exactly what to open, and WAIT for your
visual approval** before the next screen. I can't see pixels — your eyes between screens are the gate.
If a layout change would break a feature or require fake data → **STOP and flag**, never drop/ invent.

| # | Screen | File(s) | Intent |
|---|---|---|---|
| **0** | **Foundation** | `globals.css`, `tailwind.config.ts`, `app/shell/{Sidebar,Topbar,AppLayout}.tsx`, `nav.ts`, `components/ui/*` | Re-point tokens (green/light/Inter/10px/16px), restyle primitives, **build the mockup's sidebar + top bar** (sections, green active, logo, Quick Actions, search/notifications/help/identity). Whole app shifts on-brand; everything still green. Big-bang reskin commit. |
| **1** | **Dashboard** | `features/dashboard/DashboardPage.tsx` (+ tiles/cockpit, new `Sparkline`/`ScoreDonut`/`CompetencyRadar`/`TasksRail`) | Build the mockup composition (greeting hero · period selector · 5 KPI cards w/ sparklines+deltas · Performance Overview avg+trend+donut · My Tasks · Team table · Competency radar · Announcements) **wired per the (c) map** — real data, real empty states, flags honored. Manager view first (the mockup); other roles get the same shell with their real tiles. |
| **2** | **Goals & OKRs** | `features/goals/GoalsPage.tsx` (+`WeightBar`,`AttainmentBar`) | mockup/spec look; goals as living outcomes; AI drafter intact. |
| **3** | **Reviews** | `features/reviews/{ReviewsListPage,ReviewDetailPage}.tsx` | narrative/evidence before rating; AI summary as sections, never raw markdown; HITL/approval intact. |
| **4** | **Employee Profile** | `/org` PersonSheet → richer profile, or new `/people/:id` *(decision N2)* | the Constitution Ch.12 growth narrative composing existing endpoints only. |
| **5** | Recognition | `features/recognition/RecognitionPage.tsx` | moments/stories, not a form; give-flow intact. |
| **6** | Feedback (360) | `features/feedback/FeedbackPage.tsx` | tabs as in-screen pill sub-nav; HITL release intact. |
| **7** | Check-ins | `features/checkins/CheckInsPage.tsx` | the weekly loop / 1:1 surface; AI summaries stay. |
| **8** | Career Paths | `features/career/CareerPage.tsx` | growth journey; AI enrichment intact. |
| **9** | Analytics / Approvals | `features/{analytics,approvals}/*` | recharts → brand green + score bands; nine-box restyle; decision-first. |
| **10** | Succession · JD · Audit | `features/{succession,jd,audit}/*` | coverage heatmap + nine-box + tables to spec; succession employee-404 untouched. |
| **11** | Settings (Configure/Integrations/System) | `features/admin/*` | dense tables/forms to spec; entitlement gates intact. |
| **12** | Chat + global polish | `features/chat/{ChatPanel,ProposalCard}.tsx`, `command/CommandPalette.tsx` | quiet-AI styling; chat behavior unchanged. |

---

## Gates, guardrails, decisions

- **Quality gate (every screen):** `npm run typecheck` + `lint` + `build` clean **and** `test` (vitest)
  passing. Existing behavior tests stay green; only reskin-driven snapshot/class assertions move.
- **Functional invariant:** no fetch/mutation/AI call/RBAC gate/HITL/flag removed or rewired. Break a
  feature to make layout cleaner → STOP & flag (your rule).
- **Real-data invariant:** never hardcode mockup placeholders; missing source → empty + flag.
- **Isolation:** changes confined to `frontend/` (+ `docs/design/`). Backend, `shared/` contracts,
  `mobile/` untouched (`git diff` confirms per commit).
- **Commits:** conventional, ≤72-char summary (pro-workflow hook; use `git commit -F`). Push per screen;
  never push red. Recreate the frontend container; report what to open; wait.

**Decisions for you (in `HARI_ATTENTION_NEEDED_redesign_dashboard_data.md`):**
- **N1** — the 7 mockup nav items with no route: omit (recommended, no dead links) vs. show disabled
  "Coming soon".
- **N2** — Employee Profile: new `/people/:id` (recommended) vs. recompose the Org PersonSheet.
- **N3** — Engagement Score: derive from check-in mood vs. empty.
- **N4** — Announcements: empty vs. a real active-cycle status line.
- **N5** — Notifications badge: composed pending-count vs. hide.
- **N6** — performance scale: the product is **T-score + risk**, not 1–5; confirm I render the real
  metric (adapt labels) rather than invent a 1–5 rating. *(A literal 1–5 rating = a backend change,
  out of scope.)*

I'll proceed on the recommended option for each unless you say otherwise — except **N6**, which I want
explicit confirmation on before building the Dashboard, since it shapes every score tile.

---

## What I need to start
Approve (or adjust) this plan + **N6** (and N1–N5 if you have preferences). On approval I execute
**Phase 0 (Foundation)** — tokens + the mockup's sidebar/top-bar shell — prove the whole app shifts to
the green/light TalbotIQ language with everything still green, recreate the container, and stop for your
first visual look before the Dashboard.
