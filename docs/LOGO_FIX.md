# LOGO_FIX — Axiom sidebar logo render bug

Name stays **Axiom** (`REBRAND = true`); this was a logo/image render fix only.

## What was actually broken (root cause)

**Not** the Axiom assets — every brand PNG under `frontend/public/favicon/` serves
**200** (Vite copies `public/` correctly). The bug was **stale demo data + a
non-defensive `<img>`**:

- The ACME demo tenant had a fake custom-branding logo:
  `tenant_branding.logo_url = "https://cdn.acme.test/logo.png"` (a placeholder CDN
  that doesn't resolve), plus `primary_color = "#112233"`. This was leftover from
  earlier org-settings testing (it is NOT in `seed_demo_rich`).
- The sidebar header rendered that URL as
  `<img src={logo_url} alt="Organization logo">`. Because `cdn.acme.test` fails to
  load, the browser showed the **broken-image glyph + the alt text** — truncated to
  **"Orgar…"** in the 36 px mark box — sitting next to / over the "Axiom" wordmark.
  The real Axiom mark never showed because the (broken) tenant-logo branch took
  precedence over it.

## What I changed

1. **`frontend/src/app/shell/Sidebar.tsx`** — new `SidebarBrand` component:
   - Default: the Axiom mark (`BrandMark` → `/favicon/icon-green.png`) + "Axiom".
   - A tenant's own logo (white-label `custom_branding`) still overrides it, BUT
     with **`alt=""`** (decorative — the wordmark text is adjacent) and an
     **`onError` fallback** that swaps to the Axiom mark if the tenant logo fails.
     A broken/unreachable tenant logo can now **never** render a broken image or
     leak alt text over the wordmark. Removed the `alt="Organization logo"`.
2. **`frontend/src/brand.tsx`** — the `AXIOM` asset paths now load the **real files
   from `/favicon/`**: `icon-green.png` / `icon-white.png` (square mark, light/dark)
   and `logo-green.png` / `logo-white.png` (wordmark, light/dark). Sidebar uses the
   green icon; the login brand panel (dark) uses the white wordmark.
3. **`frontend/index.html`** — browser-tab favicon is the green Axiom icon:
   `/favicon-32x32.png` + `/favicon-16x16.png` (crisp small sizes, generated from
   `icon-green.png` in PROD_A) + `/favicon/icon-green.png` (512, full-res source) +
   apple-touch-icon. Title back to `Axiom · Admin Hub`.
4. **Dev data** — cleared the fake `logo_url` + `primary_color` from the ACME
   `TenantConfig` so the demo shows clean Axiom branding immediately (the code
   fallback in #1 handles it regardless; this just removes any broken-image flash).
5. Restored **`REBRAND = true`** + `APP_NAME=Axiom` (base.py default + `.env.example`)
   — the name is Axiom again.

Public-asset handling (item 3 of the request) needed **no fix** — `public/favicon/`
and `public/brand/` already resolve at runtime (confirmed 200 below).

## Verified live (http://localhost:8090, after `docker compose build frontend` + recreate)

- Tab title: `Axiom · Admin Hub`.
- Every brand image URL returns **200 image/png** (not 404):
  `/favicon/icon-green.png`, `/favicon/icon-white.png`, `/favicon/logo-green.png`,
  `/favicon/logo-white.png`, `/favicon-16x16.png`, `/favicon-32x32.png`,
  `/apple-touch-icon.png`.
- The built bundle references all four `/favicon/*.png` brand files; the string
  `"Organization logo"` no longer appears in the bundle (count 0).
- ACME `/api/auth/me` → `tenant_branding: null` (no broken logo) → sidebar shows the
  Axiom mark + "Axiom", no overlap, no "Orgar…", no broken-image icon.
- Tests green: frontend `tsc` clean + vitest **132/132**; identity **74/74**.

## Retest steps (for you)

1. `docker compose build frontend && docker rm -f pms-frontend-8090 && \
   docker run -d --name pms-frontend-8090 --network pms-talbotiq_default -p 8090:80 \
   pms-talbotiq-frontend:latest` (already done).
2. Open **http://localhost:8090** → browser tab shows the green Axiom icon.
3. Log in (`acme` / `admin@acme.test` / `Passw0rd!demo`) → the **sidebar top-left**
   shows the Axiom mark + "Axiom" cleanly — no overlap, no "Orgar" text, no broken
   image. The **login screen** brand panel shows the white Axiom wordmark.
4. Direct-load each asset, e.g. `curl -I http://localhost:8090/favicon/logo-green.png`
   → `200`.

## Note / optional follow-up

The `/favicon/` originals are large (icon ≈1.3 MB, wordmark ≈2 MB) because they load
straight from your source files as you asked. They're cached after first load; if you
later want lighter payloads, point `brand.tsx` at the small `/brand/*` derivatives
(already generated, same images downscaled) — a one-line change, no visual difference.
