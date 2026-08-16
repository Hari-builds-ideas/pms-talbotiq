# V1_B_POLISH.md — make it look premium for the demo

**Branch:** main. **Merge:** auto on green. Autonomous.
**Goal:** the demo should look finished and premium the moment it loads — the things that are missing
for a real demo: branding, favicon, logo, polish, good empty states.

## 1. Branding & identity
- Add a proper **favicon** (the TalbotIQ / Talpire mark) so the browser tab looks real, not a default.
- Ensure the **logo** renders crisply in the sidebar and on the login screen (SVG if available; clean
  fallback otherwise).
- Set the page **title** and meta (app name, description) so the tab and any share preview look
  professional.
- Confirm the brand color system (green #0d5c3a, light canvas, Inter, etc.) is applied consistently —
  no leftover default/placeholder colors.

## 2. Login screen
- Make the login screen look premium: centered brand lockup, clean card, the product name + a one-line
  tagline. First impression matters for a demo.

## 3. Empty states
- Every screen that can be empty gets a calm, branded empty state with a one-line "what this is / what to
  do" — never a blank panel or a raw "no data". Honest, not fabricated.

## 4. Consistency pass
- Consistent spacing, card style, button style across all kept v1 screens (post-simplification).
- No visual "cliff" between the polished dashboards and the other screens — they should feel like one
  product.
- Loading states: clean skeletons/spinners, not layout jumps.

## 5. Micro-polish
- Sensible page titles per route.
- Hover/focus states consistent.
- Mobile-web responsiveness of the web app at demo screen sizes (the presenter may resize).

## Rules
- Visual only — do not touch data, RBAC, HITL, or logic.
- If a brand asset (logo/favicon source) doesn't exist in the repo, generate a clean, simple placeholder
  mark in the brand color and note in PROGRESS_V1.md that a final asset should replace it — do not block.
- Keep tests green.

## Done when
- The app loads with a real favicon, crisp logo, premium login, consistent branding, and calm empty
  states everywhere. It looks finished. Logged in PROGRESS_V1.md.
