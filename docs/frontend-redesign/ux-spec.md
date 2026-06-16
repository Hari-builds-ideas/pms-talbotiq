# UX Specification — Talbotiq PMS (elevation direction)

> **Purpose.** The ideal experience and the path from "works but plain" to
> "world-class" — within the **locked stack** (React + TS + Tailwind + shadcn/ui)
> and the **existing design tokens**. This is a polish/elevation direction, **not a
> re-platform** and **no implementation code**. **§8 (Enterprise UX Review) is the
> centrepiece** — the honest critique + prioritised, actionable path. §9 is design
> inspiration. Grounding: the surveyed `frontend/src/*` + the other four redesign docs.

---

## 1. The problem, stated plainly

The product is **functionally complete and architecturally strong** (state machines,
HITL gates, RBAC/scope, audit trail, a mature error-code mapper, a clean shared
component set). But it **reads as a utilitarian admin panel** — tile-and-table dumps,
modal-driven forms, flat hierarchy, counts instead of insight. The job is to add an
**insight + guidance + craft layer** on top of the solid bones, so it feels like a
premium 2025 HR-SaaS, not an internal tool.

**North-star principles (apply everywhere):**
1. **Insight over data dumps** — lead with "what needs my attention + why", not raw counts.
2. **Guidance over form dumps** — wizards and inline editing, not cramped modals.
3. **Hierarchy over uniformity** — size/weight/colour direct the eye to what matters.
4. **Momentum over dead-ends** — bulk actions, recommended next steps, never a blocked stop.
5. **Trust over opacity** — AI provenance/confidence explained; async work shown as intentional.
6. **Restraint** — one confident accent, generous whitespace, calm palette (the tokens
   already support this; the screens under-use them).

---

## 2. Layout strategy

- **Desktop Admin Hub (primary):** keep the **dark-sidebar + topbar + max-w-[1400px]
  content** shell. Move from "page = one big panel/table" to a **purposeful multi-region
  layout** per screen: a **page header with context + primary action**, a **summary/
  insight band** (the "so what"), then the working area (list/detail/board). Use a
  **detail = master+side-rail** pattern (the Reviews detail already does this well — make
  it the template for JD, succession plan, cycle, roadmap).
- **Responsive tolerance:** the Hub is desktop-first but must **degrade gracefully** on a
  narrow viewport (collapse the sidebar to icons, stack regions, keep tables horizontally
  scrollable with sticky first column). It is not the mobile self-service product.
- **Mobile self-service (separate surface):** employee/manager own-work — bottom-tab,
  large tap targets, native feel. Out of scope here (see `MOBILE_BUILD_PLAN.md`); design
  the Hub for **Manager-and-up**, not for an employee Admin-Hub journey.
- **Density:** offer a **comfortable/compact toggle** on data-heavy screens (reviews,
  goals, audit) — enterprise users live in these.

---

## 3. Information architecture & navigation

- **Keep** the grouped dark sidebar (Workspace / Talent Intelligence / Governance /
  Administration) with active-state — it's clear.
- **Add wayfinding:** breadcrumbs on detail screens (e.g. *Reviews › Q2 Cycle › Reza
  Kahn*); a consistent page-header pattern (eyebrow + title + description + right-aligned
  primary action — `PageHeader` exists, apply it everywhere).
- **Add a global command palette (⌘K):** search people / JDs / reviews / cycles + jump-to
  any screen + run common actions. The single highest-leverage "feels premium" addition;
  composes over `/org/search` + the feature lists.
- **Add a notifications/inbox affordance in the topbar:** a bell with real counts
  (approvals awaiting, feedback requests, summaries to release, nudges) → a dropdown that
  routes to the source. These signals exist only as dashboard tiles today.
- **Make "View all" links name their destination** ("Open Reviews", not "View all").

---

## 4. Component hierarchy (the vocabulary to keep, refine, and add)

**Keep (the foundation is good):** `Panel`, `DataTable`, `PageHeader`, `EmptyState`,
`ErrorState` (kind-aware), `StatusBadge` (single colour authority), `StatCard`, the
`Hitl` family, `NineBoxGrid`, `Stepper`/`Timeline`, `FeatureGate`, the design tokens.

**Refine:**
- `StatCard` → support a **trend/delta** (▲▼ vs last cycle) + an optional **sparkline**;
  vary weight so a "north-star" metric reads larger than a secondary one.
- `Panel` → support a **priority/severity treatment** (a RED-coverage or CRITICAL-nudge
  panel should look different from a routine one) and a **dense list mode** with row
  actions.
- `DataTable` → **column visibility + saved views + a date-range filter primitive**; an
  optional **board (Kanban) view** for status-driven entities (reviews, JDs, cycles).
- `HitlBanner`/`ConfidenceBadge` → a **confidence explainer** (a tooltip: what 65% means +
  why — thin evidence vs model response) and a **consistent placement** across reviews/
  JD/summary/succession/career.

**Add:**
- **CommandPalette** (⌘K), **NotificationMenu** (topbar), **PageBreadcrumbs**.
- **InsightBand / AlertStrip** — a per-screen "what needs attention" region.
- **Wizard** (multi-step, progress) — for goal creation, review setup, cycle setup,
  workflow design (replaces cramped modals).
- **Gauge / ProgressRing** (goal attainment, roadmap progress-to-target), **MiniBarChart/
  Sparkline / StackedBar** (analytics, risk distribution), **Heatmap** (succession coverage).
- **DiffView** (draft-vs-final review, JD version compare), **CommentThread** (reviews/JD).
- **PersonChip** (avatar + name + role, hover card) — standardise person rendering.

---

## 5. Interaction patterns

- **Selection + bulk:** row multi-select on lists → a contextual action bar ("Approve 3
  reviews", "Release 2 summaries", "Record actuals for my team"). Today every action is
  1:1 — the single biggest friction for managers/HRBP.
- **Editing:** prefer **inline edit** (a row → expand/edit in place) and **wizards** over
  modals for creation; reserve modals for confirmations + single-field actions.
- **Filtering/search:** every list gets persistent, URL-encoded filters (so a view is
  shareable/bookmarkable) + a free-text search; the audit console needs a date range.
- **Shortcuts:** ⌘K palette; `j/k` row nav + `Enter` to open on dense lists; `e` edit,
  `a` approve on a focused review (power-user affordances).
- **Async work:** show **optimistic UI** on mutations + invalidate on settle; an
  `AI_DRAFTING` review shows a **"generating…" skeleton** and **auto-polls** (no "check
  back later"); the route tracker refetches after a decision.

## 6. Feedback patterns

- **Toasts (`sonner`):** keep concise success/error toasts (kind-titled via `errorTitle`);
  add an **undo** affordance where safe (e.g. deactivate user).
- **Validation:** inline, **as-you-type** where there's a rule (the KPI/goal weight
  running-sum to 100; password rules; TOTP length) — not only on submit.
- **Errors:** the kind-aware `ErrorState` is good — apply it consistently; map 429 to a
  **countdown + upgrade hint**, 503 to a **calm "AI not configured"** (distinct from
  "locked by plan"), 409 to **"this changed — refreshed"** with an auto re-fetch.
- **HITL/confidence (the product's signature):** make it **unmistakable and consistent** —
  a draft is always badged "Draft — pending review", provenance (`source`) + confidence
  always shown, a sub-floor confidence always warns, and the human gate (Approve/Reject/
  Publish/Release) is a **first-class, prominent** action, never buried. This is where the
  product can feel *more* trustworthy than competitors — lean into it.
- **Progress/celebration:** a finalized review / published plan / 100%-weighted goal set /
  released summary deserves a brief positive confirmation (a checkmark moment), not silence.

## 7. Empty, loading, and recoverable states

- **Empty/first-run:** every screen uses the actionable `EmptyState` (icon + what-this-is
  + a "create your first…" action) — several screens still inline "No X yet" text; fix.
  Add a genuine **first-run/onboarding** for a new tenant (no cycle, no users) that guides
  the admin through setup. Keep the **"AI not configured" calm state** where the key is
  absent.
- **Loading:** **skeletons that match the final layout** (not spinners) everywhere;
  progressive load (render the shell + summary band first, stream lists in).
- **Recoverable errors:** every error offers a path (retry / back-to-list / refresh) — the
  global `ErrorBoundary` (added) catches render faults with a calm fallback that keeps the
  shell usable.

---

## 8. ⭐ ENTERPRISE UX REVIEW (the centrepiece) — current state, honest critique, prioritised fixes

**What it is:** a complete HR/performance system with strong backend bones.
**What it feels like:** an internal admin panel — table-heavy, tile-heavy, modal-driven,
flat. **Why it feels plain vs premium**, and exactly what to do:

### 8.1 Cross-cutting weaknesses (fix these and the whole app lifts)
1. **No insight layer — counts, not stories.** Dashboards show "3 pending approvals", not
   "your team is on track; 2 red flags this week, here's what to do". → **Redesign role
   cockpits as a command center:** a north-star metric row (with trend) → a **pinned
   "needs you" band** (urgency-sorted: summaries to release, reviews to approve, RED
   coverage, critical nudges) with **one-click actions** → trend/insight tiles → quick
   links. Make severity visible (a RED item looks RED).
2. **No bulk / smart actions.** Everything is 1:1. → **Multi-select + a contextual bulk
   bar** on reviews/feedback/goals/users; "approve all in cycle", "record team actuals".
3. **Modal-heavy, cramped creation.** New goal/review/cycle/workflow are form-dump modals.
   → **Wizards** with a progress indicator + inline validation; inline edit for small changes.
4. **Table-/tile-monotony.** Almost every screen is a `DataTable` or a tile grid. → add
   **board (Kanban) views** for status-driven entities, **timeline** views for dated ones,
   and **viz** where numbers live (see below).
5. **Weak async UX.** "Page will update automatically" after an AI draft. → **streaming /
   "generating…" states + auto-poll + optimistic mutations**; a **notification center** for
   completed background work.
6. **No data-viz.** Analytics are bars+tables; dashboards are counts. → **sparklines, trend
   arrows, stacked risk bars, attainment gauges, a succession coverage heatmap**, all in
   the token palette.
7. **Thin wayfinding.** No breadcrumbs, no global search/command palette, "View all" is
   vague, no topbar notifications. → add all four (§3).
8. **Inconsistent HITL placement + unexplained confidence.** Strong on Reviews, varied
   elsewhere; "65%" unexplained. → a **single HITL pattern** + a **confidence explainer**.
9. **Plain empty/first-run + no onboarding.** → consistent `EmptyState` + a new-tenant
   setup flow.
10. **No collaboration.** No comments/@mentions on reviews/goals/JDs. → **comment threads**
    (a clear premium differentiator; needs a thin backend later — flag it).

### 8.2 Per-area critique + the specific recommendation
- **Dashboard / cockpit (Tier 1, WEAK):** flat tiles, truncated lists, no urgency. →
  command-center layout (8.1#1); pinned "needs you" with bulk actions; trends on `StatCard`.
- **Goals & KPIs (Tier 1, WEAK):** form-dump dialog, one-by-one actuals, no progress viz. →
  goal-creation **wizard** with a **live weight bar**; **batch actuals**; **attainment
  gauges**; "what changed" after recompute; surface at-risk goals.
- **Career roadmap (Tier 1, WEAK):** abstract tiers, no next steps, all-or-nothing enrich,
  DRAFT-vs-ACTIVE AI ambiguity. → **progress-to-target ring**; concrete per-tier next
  steps + (later) learning resources; resolve the AI-accept gap; let the user adopt AI
  tiers selectively.
- **Reviews (Tier 1 UX, arch STRONG):** async/opaque AI, cramped assessments, no compare.
  → streaming/optimistic AI draft; clearer SELF/MANAGER assessment grouping + timestamps;
  **draft-vs-final + self-vs-manager DiffView**; comment threads; bulk review-the-cycle.
- **Approvals designer (Tier 2):** numbered-list designer, no notifications. → a **visual
  step builder**; surface "your step" + time-left on the tracker; inline inbox approval;
  email/Slack reminders (backend).
- **360 Feedback (Tier 2):** no response tracking, one-button release. → a **cycle
  dashboard** (response rate, reminders, summary preview); a real **release review** (read
  sections + confidence + edit) not a single button.
- **Succession (Tier 2, WEAK):** no bench-depth preview, non-interactive 9-box, no plan
  detail. → **coverage heatmap**; **click-to-drill 9-box cells**; a real **plan detail**
  view; a "covered in N years?" scenario.
- **JD Library (Tier 2):** textarea editor, one-shot AI, opaque versions. → a structured
  (rich-list) editor; **re-generate with a refined prompt**; **version DiffView**.
- **Org chart (Tier 2):** no connectors/search, no analytics, vacancies lack context. →
  proper tree connectors + search/jump; org analytics (headcount/bench); show
  successor-readiness on a vacancy.
- **Analytics (Tier 3, WEAK):** bars+tables, confusing T-axis (>100), no comparison. →
  **sparklines + trend arrows + goal line**, fix the axis, **YoY/cohort compare**, a
  "what changed" narrative; keep the <5 suppression explicit + tasteful.
- **Tenant Config (Tier 3, WEAK):** raw JSON. → **typed form fields** with hints/defaults.
- **Billing (Tier 3):** no usage story. → **seat utilization + AI-usage/TokenLedger cost**
  + per-feature descriptions; clearer upgrade before/after.
- **Integrations (Tier 3, WEAK):** no test, no event log. → **"test connection"**, field
  help/examples, a pushed-events log.
- **Audit (refine):** no date range, raw actions, unlinked targets. → date-range filter,
  humanised actions, link the target, export.
- **Chat (Tier 3, WEAK):** no streaming/history/personalisation. → **stream**, role/data
  suggested prompts, session history, explain scope + why a write is blocked.
- **Login (refine):** generic, dead SSO button, no recovery. → polish the first
  impression, hide/enable SSO honestly, add recovery; inline validation.

### 8.3 Prioritised roadmap (what to build first)
- **Tier 1 (biggest lift, do first):** (a) **role-cockpit command-center redesign** +
  topbar notifications + ⌘K palette (the "feels premium" core); (b) **bulk actions**
  across reviews/feedback/goals; (c) **goal-creation wizard + weight bar + attainment
  gauges**; (d) **review AI streaming/optimistic + DiffView**; (e) **career
  progress-to-target + concrete tiers**.
- **Tier 2:** approvals visual designer + notifications; 360 cycle dashboard + real
  release review; succession coverage heatmap + drill-in 9-box + plan detail; JD
  structured editor + version diff; org connectors/search/analytics.
- **Tier 3:** analytics viz + comparison; typed tenant-config form; billing usage story;
  integrations test+log; chat streaming/history; login polish; comment threads
  (needs a thin backend).
- **Cross-cutting, throughout:** consistent HITL + confidence explainer; skeletons
  everywhere; consistent `EmptyState` + first-run; density toggle; breadcrumbs; trend viz.

**What NOT to change:** the design tokens, the kind-aware error handling, the HITL
architecture, RBAC/scope gating, the explicit state machines, the audit trail, the shared
component contracts. This is elevation on solid bones — preserve them.

---

## 9. Design inspiration (enterprise HR / performance SaaS) — references + why

As inspiration to study, **not to copy**, all achievable in React + Tailwind + shadcn/ui:

- **Lattice & Culture Amp (direct category peers).** *Why:* the gold standard for making
  performance/feedback feel **human and insight-led** — review/feedback flows that read as
  narratives, gentle empty states, clear "what's next". Borrow: the command-center
  dashboard, the review experience, the calm tone.
- **Linear (workflow craft).** *Why:* the bar for **speed, keyboard-first, command palette
  (⌘K), and status-driven views**. Borrow: ⌘K, board/list view toggles, optimistic UI,
  dense-but-legible lists, the "fast and intentional" feel — perfect for the manager/HRBP
  power user.
- **Stripe Dashboard (data + trust).** *Why:* the bar for **dense data made calm and
  scannable** — restrained palette, strong typography hierarchy, tasteful charts, clear
  primary actions. Borrow: the summary-band + detail pattern, the chart styling, the
  number/tabular treatment (the tokens already lean this way).
- **Notion (structured editing + flexible content).** *Why:* the bar for **inline editing
  and structured documents** — apply to the JD editor and review body (structured fields
  that read as a clean document, not raw textareas).
- **Workday / SuccessionWizard (the incumbent to beat).** *Why:* study what makes legacy
  HR feel **heavy and dated** (deep menus, modal mazes, table dumps) — and do the opposite.
  The current Hub risks "Workday circa 2015"; the redesign's job is to feel a generation
  newer.

**Patterns to adopt (stack-consistent):**
- **Navigation:** persistent grouped sidebar (keep) + breadcrumbs + a ⌘K command palette +
  a topbar notification menu.
- **Layout:** page header → summary/insight band → working area (list / master-detail /
  board). Master-detail with a side-rail for every rich entity.
- **Interaction:** keyboard-first, multi-select + bulk bars, inline edit, wizards for
  creation, optimistic mutations + auto-poll for async.
- **Visual:** one confident accent (the blue), semantic status colours (have them),
  generous whitespace, rounded-2xl cards with subtle (not heavy) shadows, tabular numerals
  for all figures, sparklines/gauges/heatmaps for the numbers that matter.
- **AI surfaces:** make HITL + confidence the trustworthy signature (provenance, an
  explainer, a prominent human gate) — a genuine differentiator vs legacy HR tools.

---

## 10. How these five docs fit together
`architecture-map.md` (domain + IA) → `frontend-spec.md` (endpoints/types/states) →
`screen-inventory.md` (what exists vs weak) → `user-workflows.md` (the journeys + gaps) →
**`ux-spec.md`** (this — the elevation direction + the prioritised path). Build Tier-1
first; it is where "works but plain" becomes "world-class".
