# BRANDING_LOCATIONS — where name / logo / favicon / colors live (identify-only)

For the later branding pass. **Nothing changed in this run** — this is the map.

## App name ("Talbotiq PMS" / "TalbotIQ")
- `frontend/index.html:21` — `<title>Talbotiq PMS · Admin Hub</title>`; `:11` description meta;
  `:15` `og:title` (+ the other OG/Twitter metas in the same head block).
- `frontend/src/app/shell/Sidebar.tsx:31` — sidebar lockup text "TalbotIQ" (`:89` falls back to
  `me.tenant_name`, so the in-app header shows the REAL tenant name once logged in).
- `frontend/src/features/auth/LoginPage.tsx:83` — "Talbotiq PMS" on the brand panel; `:105` the
  "© Talbotiq · Multi-tenant · Enterprise-grade" footer line.
- `frontend/src/features/auth/PasswordResetPages.tsx` — the same lockup on the reset pages.
- Backend email copy: `apps/identity/views.py` (`_send_reset_email`) — subject "Reset your TalbotIQ PMS
  password"; `DEFAULT_FROM_EMAIL` display name in `.env`.

## Logo mark
- The mark is the lucide **`Sprout`** icon everywhere, via `APP_ICON` —
  `frontend/src/app/nav.ts:140-141` (`export const APP_ICON = Sprout`). Consumed by
  `Sidebar.tsx:28` and directly imported in `LoginPage.tsx` / `PasswordResetPages.tsx` / `Topbar.tsx`.
  Swapping the mark = change `APP_ICON` (and the two direct `Sprout` imports) to the real logo component/SVG.

## Favicon
- `frontend/public/favicon.svg` — brand-green sprout placeholder (a designer asset should replace it);
  referenced from `frontend/index.html`.

## Color system
- **Tokens:** `frontend/src/styles/globals.css` — the CSS-variable palette; brand green is
  `--primary: 154 75% 21%  /* #0d5c3a */` (line 30) plus the success/warning/danger/ai/sidebar/chart
  variables in the same `:root` block.
- **Mapping:** `frontend/tailwind.config.*` maps Tailwind color names → those variables
  (`primary`, `sidebar`, `ai`, etc.). Components consume only the token names, so a rebrand is
  primarily a `globals.css` palette edit.
- `frontend/index.html:` `theme-color` meta (`#0d5c3a`).

## Typography
- Inter, loaded/declared in `frontend/src/styles/globals.css` + Tailwind `fontFamily` config.

## Backend / deploy surfaces
- `render.yaml` service names (`talbotiq-pms-api`, `talbotiq-mysql`, `talbotiq-redis`);
  `DEPLOY_DEMO.md`/docs mention the name; `mobile/` still ships Expo starter icons
  (mobile branding is a v2 task — `docs/handoff/MOBILE.md`).
