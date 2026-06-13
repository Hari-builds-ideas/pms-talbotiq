# Frontend Contract — 05 · Open Questions & Assumed Defaults

Things genuinely ambiguous for the frontend that I had to assume. Each has my
**assumed default** (what the contract above is written against) so you can correct
it before React starts. None blocks design; several are small backend follow-ups
worth doing for a clean Module 13.

| # | Question | Assumed default (what the contract assumes) | If you disagree |
|---|----------|---------------------------------------------|-----------------|
| 1 | **✅ RESOLVED — Pagination added.** The growth-prone lists now paginate with the shared `{count,next,previous,results}` envelope (50/page, `?page_size=` up to 200, `apps/core/pagination.StandardResultsSetPagination`): **goals list, reviews list + calibration, feedback cycles + own/received items + HRBP summary queue, org search + positions, JD list + JD requests, career own/scoped roadmaps, succession critical-roles + bench + nine-box** (+ the audit console, already paginated). **Left as plain arrays** (config / per-entity sub-lists / small): approval workflows·inbox·routes, integrations, KPI templates, JD templates, JD versions, a review's timeline/assessments, a cycle's requests, my invitations, 1:1 notes, a roadmap's progress, org vacancies/tree, AI nudges, feature-flag maps. | Each endpoint keeps its existing scoping/filtering; pagination just wraps the scoped result. The frontend codes paginated lists against `results`/`count`. |
| 2 | **Date/time + timezone** — timestamps are ISO-8601 (UTC; `USE_TZ`); cycle start/end + 1:1 `meeting_date` are plain dates. There is no per-user timezone preference. | Display UTC→browser-local for datetimes; show plain dates as-is. | If a tenant/user timezone is needed, add it to config + the contract. |
| 3 | **Approval workflow designer** — the backend supports workflow create + activate/deactivate and step definition **at create time** (no PATCH of steps; re-create to change; in-flight routes are snapshotted). | The MVP designer is **create / activate / deactivate / view** + "re-create to edit steps" — config-capable, not a live drag-drop step editor. | If a rich step editor is wanted, that's a frontend build on the same endpoints (re-create on save); no backend change needed. |
| 4 | **Succession on Mobile-Web** — management-only; employees get 404 everywhere. | Succession is **absent from Mobile-Web entirely** and never rendered for an Employee. | (Confirm — this is a privacy guarantee, not really negotiable.) |
| 5 | **Exports** (org `/export`, jd `/export`, analytics `/export`) are **text/JSON only** (no binary PDF/docx — that's Module 14). | The frontend offers "view inline" + "download JSON" / "copy text"; no PDF. | If PDF/print is needed at launch, it's a frontend-side render of the JSON (no new endpoint). |
| 6 | **✅ RESOLVED — `GET /api/billing/my-features` added.** Any authenticated role now reads its OWN tenant feature-flag map `{feature: bool}` (same data as the Admin-only `/feature-flags`; cross-tenant isolated). | UIs pre-disable locked premium controls from this map (no need to discover via 403/503). |
| 7 | **✅ RESOLVED — `GET /api/ai/nudges` added.** Manager-scoped KPI nudges (`VIEW_TEAM_SCORES`): a Manager sees their reporting subtree, HRBP/Admin tenant-wide, an Employee → 403. Returns `[{employee, level, message}]`. | The Hub renders a "team nudges" tile from this; empty when no one's at risk. |
| 8 | **Real-time updates** — there are no websockets/SSE; AI_DRAFTING, route progress, summary generation complete asynchronously. | The frontend **polls / refreshes after actions** (e.g. poll a review in AI_DRAFTING; refresh the route tracker after a decision). | If live push is wanted, that's a backend addition (channels/SSE) — out of MVP. |
| 9 | **Dashboard composition** — there is no single `/dashboard` endpoint. | The frontend **composes** role dashboards client-side from the feature endpoints (+ the approvals inbox count). | If a server-aggregated dashboard is wanted, add an endpoint; otherwise compose client-side. |
| 10 | **✅ RESOLVED — `display_name` added.** `User` now has an optional, nullable `display_name` + a computed `display` (= `display_name` or email fallback). Wired into admin create + `POST /api/admin/users/<id>/display-name`, the `me` response, and the org person card + search. | Render `display` (always populated); edit `display_name`. (See the User entry in `03_data_dictionary.md`.) |
| 11 | **Chat person reference** — the Chat agent resolves a person by an **email** appearing in the free-text query; results are always RBAC-scoped to the caller. | The chat UI is **free-text** (no person-picker required); out-of-scope/cross-tenant targets simply return nothing. | If a structured person-picker is wanted, the frontend can build one over `/api/org/search` and pass the email into the query. |
| 12 | **Calibration grid suppression** — the 9-box calibration grid (HRBP/Admin) shows per-box counts **and** placements (employee + box); min-cohort suppression is NOT applied to calibration (it's over already-management-only 9-box data). | Calibration shows individuals to HRBP/Admin. | If calibration should also suppress small boxes, that's a backend rule change. |
| 13 | **Multi-target career roadmaps** — a user may select multiple distinct targets (one ACTIVE roadmap per target). | The career UI supports **one active target at a time** (simplest), but the API allows several. | If you want a "compare targets" UI, the API already supports listing multiple roadmaps. |
| 14 | **OIDC/SSO UX** — the IdP round-trip is at `/accounts/...` (allauth) and finalises via `POST /api/auth/oidc/complete`. | The SPA does a redirect-based SSO handoff (not embedded); local login + MFA is the primary path for MVP. | Confirm the SSO providers + whether SSO or local-login is the default entry. |

## Summary of recommended backend follow-ups — ✅ ALL BUILT
- **`GET /api/billing/my-features`** (all roles, read-only) — DONE (#6).
- **`GET /api/ai/nudges`** (manager-scoped) — DONE (#7).
- **Pagination** on growth-prone lists — DONE (#1).
- **User `display_name`** (+ `display` fallback) — DONE (#10).

The four pre-frontend gaps are closed. The remaining items above (#2 timezone, #3
designer scope, #4 mobile-succession, #5 exports, #8 real-time, #9 dashboard
composition, #11 chat picker, #12 calibration, #13 multi-target, #14 SSO) are
accepted defaults, not gaps — the backend is now feature-complete for Module 13.
