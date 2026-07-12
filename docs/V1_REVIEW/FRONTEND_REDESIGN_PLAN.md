# FRONTEND_REDESIGN_PLAN — the Claude Design prompt for the LATER modernization pass

> **AFTER v1.** Reference only — do NOT run this during the v1/production-handover phase.
> Functionality is frozen; this is a visual/UX modernization brief.

---

## The prompt (paste into a Claude design/build session)

You are redesigning the UI of **TalbotIQ PMS**, a multi-tenant, AI-assisted performance-management
SaaS for SMEs (React 18 + TypeScript + Vite + Tailwind + shadcn/ui; tokens in
`frontend/src/styles/globals.css`, mapped in `tailwind.config`). Modernize it into a polished
enterprise SaaS product — think Linear/Notion-level finish with Lattice/15Five domain patterns —
**while preserving ALL existing functionality, routes, data wiring, RBAC gating, and tests.**

**Hard constraints (do not violate):**
1. No functional changes: every page, button, form, query, mutation, and permission gate keeps its
   behavior. Visual/layout/IA polish only.
2. Keep the token architecture: restyle by editing the CSS variables + component classes, not by
   inlining colors. Brand green `#0d5c3a` stays the primary (see BRANDING_LOCATIONS.md).
3. Keep shadcn/ui as the component base; extend variants rather than replacing the library.
4. Accessibility floor is WCAG 2.1 AA — the axe test suite (`src/test/a11y/`) must stay green.
5. The capability-gating pattern (`useAuth().can(...)`, `useScopedPeople()`) and the v1 scope flags
   (`app/v1.ts`) are load-bearing — never bypass them for a visual effect.
6. `tsc` clean + all vitest suites green after every change; the redesign lands as reviewable,
   per-surface commits (shell → dashboard → goals → reviews → …), never one mega-commit.

**What to elevate (in priority order):**
1. **App shell** — sidebar/topbar hierarchy, density, focus states; the persistent right-docked AI
   copilot (already resizable) should feel first-class, not bolted on.
2. **Dashboards** (4 role cockpits) — clearer visual hierarchy: one hero insight per role, calmer
   cards, consistent stat/tile/donut language.
3. **Goals** — keep the %+colored-bar pattern (it's the product's signature simplification); refine
   the expanded details, per-person grouping rhythm, and the create wizard.
4. **Reviews** — the stepper, editor, and evidence panel as one coherent flow; state → color language.
5. **Forms/dialogs** — unify spacing, validation display, and button placement across every dialog.
6. **Empty/loading/error states** — one calm, branded system (EmptyState/skeletons exist; make them
   feel designed, not default).
7. **Micro-interactions** — hover/focus/transition consistency; respect `prefers-reduced-motion`.

**Process:** per surface — (a) screenshot/inventory the current state, (b) propose the redesign as a
described spec (layout, spacing, type scale, color use), (c) implement behind small commits,
(d) verify tsc/vitest/axe, (e) before/after notes. Deliver a final `REDESIGN_REPORT.md` with every
surface's before/after and any token changes.

---

*Why this shape: v1 deliberately prioritized functionality and simplicity (FINAL.md). The bones —
tokens, shadcn, a11y guard, gating hooks — are solid; the gap is visual refinement and rhythm, which
this brief scopes tightly so the redesign can't regress behavior.*
