# Accessibility — WCAG 2.1 Level AA (desktop Admin Hub)

The brief requires the web front-end to be **WCAG 2.1 Level AA**. This documents what
was audited, what was fixed, the automated guards that keep it from regressing, and —
honestly — what automated testing does **not** cover and still needs a human/assistive-
technology pass.

## Standard targeted
WCAG 2.1, conformance level **AA** (which includes all Level A), for the desktop Admin
Hub: login, dashboard, reviews, goals/KPIs, JD generation, org chart, succession
(nine-box), analytics, calibration/moderation, admin (users + tenant/KPI config), audit,
approvals, feedback, career, and the global shell + ⌘K command palette.

## Automated audit + guards (what runs in CI)

Two test files under `frontend/src/test/a11y/` run in the normal `vitest` suite:

1. **`a11y.test.tsx` — axe-core over the real screens.** Each key screen renders in the
   actual authenticated shell (skip-link + sidebar + topbar + `<main>`) with realistic
   MSW data, and `axe-core` runs at tags `wcag2a, wcag2aa, wcag21a, wcag21aa`. The guard
   asserts **zero** A/AA violations on **14 screens + the command palette opened**.
2. **`contrast.test.ts` — token contrast.** Reads the real color tokens from
   `globals.css` and checks the actual `foreground/background` pairs (including the
   Badge `text-<tone>` on `bg-<tone>-subtle` pattern) compute to **≥ 4.5:1** for normal
   text. 14 pairs, all green.

### Before → after

| Issue (found by the axe pass / contrast computation) | Before | After |
|---|---|---|
| `button-name` — unlabeled `SelectTrigger`s with no value (reviews, analytics, audit) | 4 | 0 |
| `label` — date/text filter inputs not associated (audit) | 2 | 0 |
| `aria-dialog-name` — command palette had no accessible name (Radix Dialog, no title) | 1 | 0 |
| Color contrast < 4.5:1 — status badge tones (success/warning/danger/info/ai/premium) + `muted-foreground` | 7 | 0 |
| **axe A/AA violations across the audited screens** | **7** | **0** |

## What was fixed
- **Names for custom controls.** Every filter `Select` and date/text input that lacked a
  programmatic name got an `aria-label` (audit, analytics, reviews).
- **Command palette.** The cmdk dialog now carries a visually-hidden `DialogTitle` +
  `DialogDescription`, so it has an accessible name (4.1.2).
- **Landmarks + bypass.** Added a **skip-to-main-content** link (first focusable element,
  visible on focus) targeting `<main id="main-content" tabindex="-1">`; the sidebar `<nav>`
  is labelled "Primary". The shell already used `<header>`/`<main>`/`<aside>`.
- **Icon-only buttons.** Topbar controls whose text label is hidden on small screens
  (Ask AI, Preview role, the account menu) now have `aria-label`s so they always have a
  name.
- **Keyboard alternative to the nine-box drag (2.1.1).** Each chip in the calibration
  grid has a **"Move to box" menu** (`ArrowLeftRight` trigger → the nine boxes). Keyboard
  users Tab to it, Enter to open, arrow to a target, Enter to move — no pointer needed.
  Drag still works for pointer users.
- **Visible focus (2.4.7).** The global `:focus-visible` rule was changed from
  `outline: none` to a real `2px` outline in the brand ring color — so bare focusable
  elements (links, skip-link, `[tabindex]` regions) show focus. shadcn controls keep
  their own ring (their utility-layer `outline-none` overrides the base rule).
- **Color contrast (1.4.3).** The semantic tone tokens (`--success/--warning/--danger/
  --info/--ai/--premium`) and `--muted-foreground` were darkened so `text-<tone>` on the
  pale `bg-<tone>-subtle` (and secondary text on the page background) clear 4.5:1.
  White-on-solid `bg-<tone>` usages only gained contrast.
- **Reduced motion (2.3.3/2.2.2).** A `@media (prefers-reduced-motion: reduce)` block
  collapses animations/transitions and forces `scroll-behavior: auto`.

## Honest caveats — what automated testing does NOT cover

axe-core in jsdom catches a real but **partial** slice of AA (names, roles, labels,
landmarks, ARIA, heading order, list semantics, dialog naming). It does **not** render
layout, so the following were handled out-of-band and/or still need a human + AT pass to
claim full conformance:

- **Color contrast** is checked here by computing ratios from the tokens — that covers
  the systematic text/badge pairs, but **not** text over images/gradients, disabled-state
  text, charts, or focus-ring contrast. Those need a rendered-pixel check (e.g. axe in a
  real browser / Lighthouse).
- **Real keyboard & screen-reader walkthrough** (focus order through dialogs/menus, focus
  return on close, live-region announcements for async updates, the cmdk + nine-box flows
  driven by an actual AT) — needs a manual pass with NVDA/JAWS/VoiceOver.
- **Reflow / zoom to 400% / 320px (1.4.10), text-spacing (1.4.12), orientation** — need a
  real browser at the target viewport.
- **Screens behind interaction** (every dialog/sheet/dropdown open state beyond the
  command palette) — the guard audits the loaded screens + the palette; other overlays
  were spot-checked in code but not each exhaustively rendered in the guard.

**Conformance statement (honest):** the audited desktop screens are **automated-AA clean
(axe) with all systematic text-contrast pairs ≥ 4.5:1**, and the listed manual-audit
items remain for a human/AT review before a formal full-conformance claim. This is the
accurate position per the COE brief — we do not claim certified full WCAG 2.1 AA
conformance from automated testing alone.

## Running it
```
cd frontend && npm test            # includes the a11y + contrast guards
npx vitest run src/test/a11y/      # just the accessibility guards
```
