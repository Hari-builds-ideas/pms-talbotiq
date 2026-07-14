# PROD_PROGRESS — unattended production-readiness run

Run driver: `PROD_MASTER.md` → A (branding) → B (onboarding/SSO) → C (payments) →
D (AI robustness) → E (handover). Logged after each file. Branch: `hari/agent-ui-v2`.

---

## PROD_A — Branding ✅ (commit `fafed5c`)

**Goal:** product looks finished and is named **Axiom** everywhere, from ONE place,
fully reversible to the legacy "Talbotiq PMS" identity.

### What changed
- **One central seam** `frontend/src/brand.tsx` — `BRAND` config + `BrandMark`/
  `BrandWordmark` components. A single `const REBRAND = true` flips the whole
  rebrand (name **and** every logo/favicon) back to the legacy leaf mark. The
  display name also honours `VITE_APP_NAME` env override. Legacy values kept as
  the fallback block.
- **Backend name** `settings.APP_NAME` (env `APP_NAME`, default `Axiom`) — drives
  `DEFAULT_FROM_EMAIL` and the 3 email subjects (invite / password reset / email
  change) in `apps/identity/{invite_views,views,profile_views}.py`.
- **Favicon** — real PNG favicons (16/32/180/192/512) generated from the green
  icon mark, wired in `frontend/index.html`; tab title + OG/meta now "Axiom".
- **Logos wired** — login brand panel (white wordmark on dark), sidebar header
  (green mark + short name), the two public auth pages (invite / reset lockups).
  All via the seam; the per-tenant `custom_branding` logo override is untouched.
- **Assets** — human's 4 source PNGs kept at `frontend/public/favicon/`
  (`icon-green/white`, `logo-green/white`); web-optimized derivatives generated
  under `frontend/public/brand/` + root favicons (sips, KB-sized).
- **Avatars** — UI already had initials-fallback avatars (kept). Added bundled
  **branded-initials avatar fixtures** (`apps/core/management/commands/demo_avatars/*.png`)
  seeded onto 6 named ACME demo people in `seed_demo_rich` (deterministic, ACME-only,
  no external fetch, no runtime image dep — the container has no Pillow, so the PNGs
  are pre-generated). Idempotent: never overwrites an uploaded photo.

### Verified
- Frontend `tsc --noEmit` clean; **vitest 132/132** green (incl. axe a11y).
- Backend `manage.py check` clean; **identity suite 70/70** green.
- Live on `http://localhost:8090`: tab title `Axiom · Admin Hub`; favicons +
  `/brand/*` assets all serve 200 `image/png`.
- Reseed OK ("seeded 4 demo avatars" — 2 already had uploads); all 6 named people
  stream their avatar 200 via the authenticated photo endpoint.

### How to REVERT the branding (one step)
Set `REBRAND = false` in `frontend/src/brand.tsx` and `APP_NAME=TalbotIQ PMS` in
the env (or the base.py default). Rebuild the frontend. Full detail in
`docs/PROD_READY_REPORT.md` (written in PROD_E).

### Human to-do
- The real logo source PNGs are in place; to swap them, replace the files under
  `frontend/public/favicon/` and regenerate the derivatives (documented in the
  final report), then `docker compose build frontend`.

### QUESTIONS / decisions made
- Chose to keep the human's 1–2 MB source PNGs in `favicon/` and ship KB-sized
  `sips`-generated derivatives for the actual `<img>`/favicon refs (source PNGs are
  too heavy to serve directly). No decision needed from the human.
