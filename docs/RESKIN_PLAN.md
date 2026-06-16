# RESKIN_PLAN.md — applying the Figma Make design system to the Admin Hub

> **Goal.** Apply the "Enterprise AI Performance Management" Figma Make export as
> the **visual skin** of the existing, working frontend — premium look, **zero loss
> of real wiring** (API client, auth/refresh, RBAC/feature-flag gating, error-code
> mapper, HITL/confidence, routing, every screen's real data). Visual elevation, not
> a rebuild. Backend untouched.
> **Status:** assessment + plan. **No mass edits yet — awaiting Hari's go-ahead on
> the recommended approach.**

---

## 1. The gap — existing app vs the Figma export

| Aspect | Existing `frontend/` | Figma export | Mismatch severity |
|---|---|---|---|
| **Tailwind** | **v3.4** — JS `tailwind.config.ts`, `@tailwind base/components/utilities`, tokens consumed via `hsl(var(--x))` | **v4.1** — CSS-first, `@tailwindcss/vite`, `@import "tailwindcss"`, `@theme inline`, no JS config | **HIGH (foundational fork)** |
| **Token format** | HSL channels (`--primary: 221 70% 50%`) | raw hex / rgba / **oklch** (`--primary: #5B5BD6`) | Medium — needs conversion |
| **Token set** | full shadcn + **domain palette** (success/warning/danger/info/**ai**/**premium** + `-subtle`) + sidebar.* | shadcn + `chart-1..5` + `input-background` + `switch-background` — **NO domain palette** | **HIGH — see §2** |
| **Primary** | blue `hsl(221 70% 50%)` | **indigo `#5B5BD6`** | the target skin |
| **Sidebar** | dark slate `222 39% 11%` | near-black `#0C0C14` | minor (re-tune) |
| **Radius** | `0.625rem` | `0.75rem` | trivial (one var) |
| **Fonts** | Inter + system mono | **Plus Jakarta Sans + DM Mono** (Google Fonts) | low risk (swap) |
| **Vite / React** | Vite 5.4 / React 18.3 | Vite 6.3 / React 18.3 | low (no need to bump) |
| **Components** | 22 hand-rolled shadcn (Radix), with `loading` props + domain `variant`s | ~46 shadcn (v4 idiom), superset (breadcrumb, command, chart, progress, slider, sidebar, drawer…), **different prop contracts** | **HIGH if swapped wholesale — see §3** |
| **Extra deps** | sonner 1.5, tailwindcss-animate | + cmdk, recharts, motion, tw-animate-css, sonner 2 | additive |
| **Build deps it carries** | — | also ships MUI/emotion (Figma noise) | ignore MUI |

---

## 2. The critical constraint — the domain semantic palette

The existing app's product meaning lives in a **domain palette the Figma export does
not have**: `ai` (purple, AI states), `premium` (gold, locked features), `success`,
`warning`, `info`, `danger`, each with a `-subtle` variant. These are used in
**156 utility occurrences + 70 component `variant=` usages across 44 files**
(`StatusBadge`'s ~40 status→colour map, `Hitl` confidence/HITL banners, `FeatureGate`
upsells, `StatCard` tones, every screen's status chips).

**Implication:** adopting the Figma `theme.css` wholesale (which only defines
`destructive` + `chart-*`) would break 44 files at once. **The palette token NAMES
must be preserved.** We re-skin by **re-tuning the token VALUES** (harmonised to the
indigo system + the Figma chart palette) while keeping the names — so every existing
class (`bg-success-subtle`, `text-ai`, `variant="premium"`) keeps working and instantly
adopts the new look.

---

## 3. The two real decisions (forks)

### Fork A — Tailwind **v3 in place** vs **v4 migration**
- **v3 in place (RECOMMENDED).** Keep the v3 config + directives + the `hsl(var())`
  token pattern + custom utilities. **Re-skin by changing token VALUES + fonts + radius**
  — because every component consumes `hsl(var(--x))`, this re-skins the *entire app at
  once* with near-zero wiring risk and a green build throughout.
- **v4 migration (NOT recommended).** v3→v4 on a 25-screen, 22-component,
  44-file-palette-dependent app is a breaking migration: `tailwind.config.ts` → CSS
  `@theme`; `@tailwind` directives → `@import "tailwindcss"`; the `hsl(var())` pattern
  changes; utility renames (`shadow-sm`→`shadow-xs`, ring defaults); custom utilities
  (`skeleton-shimmer`, `scrollbar-thin`, `tabular-nums`) re-authored; PostCSS/Vite
  plugin swap; every component + screen re-verified. High risk for "elevation, not
  rebuild" — and **unnecessary**, since the visual result is identical via token remap.

### Fork B — **port the Figma component LOOK** vs **swap the component FILES**
- **Port the look (RECOMMENDED).** The Figma primitives are ~v3.4-compatible in idiom
  (`size-4`, `has-[>svg]:`, `ring-ring/50 ring-[3px]`, `bg-primary/90` all work in v3.4),
  but their **prop contracts differ** — e.g. the Figma `Button` has **no `loading` prop**
  and fewer variants; the Figma `Badge` lacks the domain variants (`ai`/`premium`/
  `success`/`warning`/`info`) that 70 call-sites depend on. So we **port their styling
  refinements** (radii, focus rings, sizes, transitions, spacing) into the existing
  primitives, **preserving every prop + domain variant** — and **add the NET-NEW Figma
  components additively** (breadcrumb, command/cmdk, chart, progress, slider, sidebar,
  drawer), adapted to v3.4. No call-site breaks.
- **Swap the files wholesale (NOT recommended).** Would drop `loading` + the domain
  variants → mass breakage across reviews/goals/feedback/etc., and pulls in v4-only
  assumptions. Only viable *after* a v4 migration — i.e. the high-risk path.

### Fork C — fresh shell re-importing API/auth (explicitly the highest risk)
Throws away 25 working, wired, RBAC/HITL-correct screens. **Not recommended** for a
visual elevation; only sensible if a ground-up rebuild were the actual goal (it isn't).

---

## 4. RECOMMENDATION

**Adopt the Figma design system as a re-skin IN PLACE on Tailwind v3 (Fork A) by
remapping token values + fonts + radius, KEEPING the domain palette names, and PORTING
the Figma component look into the existing primitives (Fork B) — not a v4 migration,
not a file swap, not a fresh shell.**

Why: it delivers the premium indigo/dark Figma look across the whole app with the
**lowest risk to the working wiring**, a **green build between every phase**, and full
preservation of the domain semantics (ai/premium/HITL/status) that the product's
meaning depends on. The only cost is that we re-create the Figma components' *look*
rather than dropping their *files* in — the correct trade for "elevation, not rebuild".

---

## 5. Phased plan (each phase: build + tsc + lint green, verified vs live backend, commit + push)

### Phase 1 — Design foundation (tokens · fonts · radius)
- **Fonts:** swap the Google Fonts import + `fontFamily.sans`/`mono` to **Plus Jakarta
  Sans** + **DM Mono** (in `globals.css` + `tailwind.config.ts`).
- **Palette remap (values only, names kept):** convert the Figma colours to the existing
  HSL-channel format and set them in `globals.css`:
  - `--primary` → indigo `#5B5BD6` ≈ `240 60% 60%`; `--ring` to match.
  - `--background` `#F1F1F6` ≈ `240 20% 95%`; `--foreground`/`--sidebar` `#0C0C14` ≈
    `240 25% 6%`; `--muted-foreground` `#71718A` ≈ `240 10% 49%`; refined neutral border.
  - `--radius` → `0.75rem`.
  - **New tokens:** `--chart-1..5` (from the Figma chart palette), `--input-background`,
    `--switch-background` (wired into the config + the input/switch components).
  - **Domain palette retune (keep names):** `ai` = violet (Figma chart-5 `#8B5CF6`),
    `premium` = gold (keep), `success` = `#00B87C`, `warning` = `#F59E0B`, `info` =
    `#06B6D4`, `danger` = `#EF4444` — harmonised to the indigo system, all `-subtle`
    variants retuned. **No token name changes**, so the 44 files keep working.
  - Optional dark-mode tokens (the Figma export ships an oklch `.dark` set) — wire only
    if we enable a dark theme (defer unless wanted).
- **Acceptance:** the whole app instantly reads indigo/dark-Figma; `npm run build` +
  `tsc --noEmit` + `eslint .` green; visual smoke at `localhost:8080`.

### Phase 2 — UI primitives (port the look, preserve contracts)
- Port the Figma styling into the existing `components/ui/*` (button, card, table,
  dialog, sheet, badge, input, tabs, select, dropdown, tooltip, switch, checkbox,
  separator, scroll-area, popover, alert, avatar, skeleton, label, textarea, sonner) —
  radii, focus rings, sizes, transitions, the refined shadcn surfaces — **keeping
  `loading`, `asChild`, and all domain `variant`s**.
- Add NET-NEW Figma components **additively** (adapted to v3.4): `breadcrumb`,
  `command` (cmdk), `chart` (recharts wrapper), `progress`, `slider`, and (if used) a
  `sidebar` primitive + `drawer`.
- **Acceptance:** every existing screen still compiles + renders (no lost props); build
  green.

### Phase 3 — Shell + screens
- Re-skin the **app shell** (Sidebar/Topbar) to the Figma sidebar look (near-black,
  indigo active, the new fonts), then walk **screen group by screen group** (dashboard
  → reviews → goals → feedback → approvals → org → succession → analytics → jd → career
  → admin → audit → integrations → chat), applying the refined surfaces while keeping
  **every real data hook, state, RBAC/feature gate, and HITL treatment intact**.
- **Acceptance:** each group verified against the **live backend** (`VITE_USE_MOCKS=false`):
  no dead buttons, no lost wiring; build green; commit + push per group.

### Phase 4 — Richer components (per `docs/frontend-redesign/ux-spec.md` §8.3)
- **cmdk command palette** (⌘K) over `/org/search` + route jumps + common actions.
- **recharts** data-viz on the dashboard + analytics (trend sparklines, risk
  distribution, coverage) — wired to the **real** analytics/score data.
- **sonner** toasts (keep/upgrade), **breadcrumbs** on detail screens.
- **Rule:** every new component is wired to **real data/actions** — never a mock-only
  screen.

---

## 6. Risks + mitigations
- **R1 — breaking the domain palette** (44 files). *Mitigation:* keep token NAMES; only
  change values. (Eliminated by design.)
- **R2 — prop-contract loss on a file swap** (`loading`, domain variants). *Mitigation:*
  port the look, don't swap files; preserve contracts.
- **R3 — v4 idioms under v3.** *Mitigation:* the Figma utilities are largely v3.4-valid;
  the few v4-only ones (`shadow-xs`, `outline-ring/50`) get v3 equivalents during the port.
- **R4 — oklch tokens** (Figma dark mode + a couple of values). *Mitigation:* convert to
  HSL channels for the light theme; defer the oklch dark theme unless dark mode is wanted.
- **R5 — font swap shifting layout/metrics** (Inter → Plus Jakarta Sans is slightly
  wider). *Mitigation:* verify dense tables/badges after Phase 1; the compact fontSize
  scale already absorbs this; tabular-nums kept.
- **R6 — losing wiring during screen re-skin.** *Mitigation:* re-skin = className/layout
  changes only; never touch hooks/handlers; verify each group vs the live backend.

## 7. What is explicitly NOT changing
The backend; the API client + auth/refresh; RBAC/scope + feature-flag gating; the
error-code mapper; the HITL/confidence logic; routing; the state machines; the audit
trail; the domain palette token **names**; the Vitest tests. Visual elevation only.

## 8. Decision needed from Hari (before mass edits)
1. **Confirm Fork A + B** (re-skin in place on v3, port the component look) — the
   recommended, lowest-risk path. *If you'd rather I do a true Tailwind v4 migration to
   use the Figma component files verbatim, say so — it's a much larger, riskier effort
   and I'd treat it as a separate rebuild track.*
2. **Dark mode?** The export ships a dark theme; the app is light-only today. Default:
   skip dark mode this run (light re-skin only); enable later if wanted.
3. **Indigo intensity / exact anchors** — I'll match the Figma values; flag if you want
   it lighter/darker once you see Phase 1.
