# Mobile Redesign Plan — from CRUD pages to a product

**Status:** PROPOSAL — anchored on the web redesign + the TQ Constitution (Design Laws / Taste /
Engineering Execution). Awaiting Hari's "one thing" (a mobile reference/mockup) to lock the visual bar,
then build screen-by-screen with his eyes between each.

**Honest diagnosis (owned):** the mobile color reskin (`62b623d`/`74ea96b`) was skin-deep — it changed
the palette and **none** of the real problems. The app is still *pages wired to endpoints*, not a
product: stat-grid dashboard, list-row goals, markdown-blob reviews, a bare chat-box "AI" tab, emoji
iconography, and core features (Reviews/Recognition/Check-ins/AI) hidden under **More**. This plan is a
**recompose**, not a retint. Reskin + recompose ONLY — no backend/API/RBAC/auth/shared-contract/data
change; every fetch + action keeps working. The data layer is the web-verified `@shared` layer.

## North star
"Use the same things" = mirror the **web redesign's** system on mobile: TalbotIQ green/light tokens
(done), **real lucide-equivalent icons** (not emoji), **one hero + reading path per screen**, **honest
data** (T-score shown as a T-score, never a fake /5/%; empty → teach, never fabricate), AI **embedded**
in flows (not a tab). The Constitution governs composition; the web screens are the reference quality bar.

## (a) Icon system — kill emoji  *(certain; do first)*
- Adopt **`@expo/vector-icons` → Feather** (bundled with Expo, mirrors web's lucide stroke-2). No new
  dependency, cross-platform.
- Replace: reactions 👏❤️🎉 → `thumbs-up`/`heart`/`award`; chrome `＋`/`✕`/`→` → `plus`/`x`/`chevron-right`;
  tab-bar + section glyphs → Feather. Add an `Icon` wrapper in `mobile/src/components/ui.tsx`.
- **Mood (1–5):** keep expressive but de-emoji — a labeled segmented control or Feather faces
  (`frown`→`meh`→`smile`), with the value legible. (Confirm with Hari; mood faces are borderline.)

## (b) Information architecture — recut the tabs (no "More" dump)
Mirror the web's everyday set; stop hiding core features. Proposed bottom tabs (≤5, role-aware):
**Home · Goals · Reviews · Recognition · You**. Feedback + Check-ins surface inside Home/flows or a
secondary row; manager extras (Approvals, Team check-ins) gate in for managers. "Career" moves into
**You** (the profile), not a primary tab. No core feature lives behind a generic overflow.

## (c) Per-screen composition (Constitution: one hero, reading path, narrative > raw number)
| Screen | From → To |
|---|---|
| **Home/Dashboard** | 4 stat tiles → a **hero brief** ("what needs you today": pending reviews/feedback/at-risk) + a small momentum strip; real data, honest labels. Not a number grid. |
| **Goals** | list rows + input → PERSON→GOAL→KPI hierarchy with attainment + the **plain-language explainer** (mirrors the web Goals clarity pass). |
| **Reviews** | markdown blob → **designed sections** (summary / strengths / risks / actions / state), never raw text. |
| **AI** | standalone chat tab → **embedded** assist in goals/reviews/check-ins; keep a light Q&A entry, not a primary destination. |
| **Recognition** | repeated cards → moments with avatars + value, real icons, less empty space. |
| **Feedback / Check-ins** | form feel → guided, with real empty states that teach; check-in shows past weeks + manager response. |
| **You (profile)** | new: identity + score (honest T-score) + goals/career snapshot, mirroring the web `/people/:id`. |
| **Empty states** | "Nothing to give" → explain why + the next action. |

## (d) Build order (one screen at a time; bundle-verify each; Hari's eyes between)
1. **Icons + `Icon` primitive** (emoji → Feather) — app-wide, certain.
2. **Tab IA recut** (`(tabs)/_layout.tsx` + routing) — no "More" dump.
3. **Home** hero recompose. 4. **Goals** hierarchy + explainer. 5. **Reviews** sections.
6. **Recognition / Feedback / Check-ins** polish. 7. **You** profile. 8. AI-embed pass.

**Gate per step:** `tsc --noEmit` + `expo lint` clean **and** `expo export` (iOS) bundles; commit + push.
Mobile isn't containerized → **visual check is Hari's** (`cd mobile && npx expo start`), since I can't see
its pixels. If a recompose would break a feature or need fake data → STOP + flag, never drop/invent.

## Need from Hari
Your **"one thing"** — a mobile reference/mockup (even one screen) showing the look + density you want, so
I lock the visual bar before recomposing (the web dashboard mockup played this role for web). With it I'll
finalize this plan and build step 1 (icons) immediately.
