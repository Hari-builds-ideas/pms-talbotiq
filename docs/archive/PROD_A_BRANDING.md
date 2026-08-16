# PROD_A_BRANDING.md — favicon, logo, app name, profile photos

**Goal:** the product looks finished and correctly named everywhere. The human will drop in final images;
build the seam so swapping them is trivial, and ship clean defaults now.

## 1. App name — everywhere
- The chosen product name is **Axiom** (formerly TalbotIQ/Talpire). Set it consistently across: browser
  tab title + meta (index.html), the login screen, the sidebar header, email templates ("From" name +
  subject prefixes), and any "TalbotIQ"/"Talpire"/placeholder occurrences. Use ONE canonical name from
  settings (`APP_NAME=Axiom`) so it's changed in one place. Grep the whole repo for hardcoded old/
  placeholder names and route them through the setting. (Keep the internal package/module names as-is to
  avoid churn; this is a user-facing display-name change only.)

## 2. Favicon
- Add a real favicon (ico + png sizes + apple-touch-icon) wired in index.html so the browser tab shows
  the brand mark, not a default. Put the source at a known path (e.g. `frontend/public/favicon.*`) so the
  human swaps the file and it just works.

## 3. Logo
- Ensure the logo renders crisply on the login screen and in the sidebar (prefer SVG; provide a clean PNG
  fallback). Reference it from one place. Put it at a known path (e.g. `frontend/src/assets/logo.svg`) the
  human can replace.
- If no final logo asset exists yet, generate a clean, simple placeholder mark for **Axiom** in the brand
  color (green #0D5C3A) as an SVG so nothing looks broken, and note in the report that the human will drop
  in the real "Axiom" logo/favicon PNGs (or SVG) at the documented paths. When the human's real assets are
  present at those paths, use them.

## 4. Profile photos (seed + display)
- The profile-photo upload must work end to end (validate type/size, store under MEDIA_ROOT, serve via
  the authenticated scope-checked endpoint) — this was fixed earlier; verify it still works.
- Add sensible DEFAULT avatars so every person shows something clean when no photo is set: generate
  initials-based avatars (first+last initial on a brand-colored circle) as the fallback in the UI.
- In `seed_demo_rich`, assign a few demo people a generated/placeholder avatar so the demo looks populated
  (deterministic, ACME-only, no external fetch). The human can drop real photos in later via the seam.

## Rules
- Visual/config only — do not touch data, RBAC, HITL, or logic.
- One source of truth for name + asset paths so the human swaps images/name without hunting.
- Keep tests green.

## Done when
- App name is consistent everywhere from one setting; real favicon; crisp logo (login + sidebar);
  working photo upload + clean initials-fallback avatars; a few seeded demo avatars. Swappable via
  documented paths. Logged in PROD_PROGRESS.md.
