# FRONTEND_READINESS.md — API inventory for Module 13 (React)

Every backend surface the desktop Admin Hub + responsive mobile-web will consume.
Built tonight as the rule-8 deliverable (the React frontend itself is out of scope).
Authoritative sources for exact payloads: each app's `serializers.py`; this doc is
the map + conventions + capability/scope per endpoint.

## Cross-cutting conventions (apply to EVERY endpoint)
- **Auth:** `Authorization: Bearer <access>` (JWT from `POST /api/auth/login`). The
  tenant + role are embedded in the token and bound server-side — the frontend never
  sends a tenant id. Refresh via `POST /api/auth/token/refresh`.
- **RBAC:** server-side on every endpoint (never trust the frontend). A role lacking
  the capability → **403**.
- **Scope / not-found rule:** an out-of-scope or cross-tenant id → **404** (never a
  403 that would leak existence) — EXCEPT succession, which 404s employees entirely
  (it is invisible to non-management). Plan UI around 404 = "not yours / not there".
- **Errors:** 400 bad input · 401 unauthenticated · 403 role-forbidden · 404
  out-of-scope/not-found · 409 illegal state transition / conflict · 422 domain
  validation (with `{detail, code}`) · 429 rate-limit or agent-budget (with
  `Retry-After` / `upgrade_hint`) · 503 AI seam not configured.
- **Throttling:** per-tenant + per-user (entitlement-driven); 429 + `Retry-After`.
- **Feature flags:** `GET /api/billing/feature-flags` returns the `{feature: bool}`
  map — drive UI enable/disable from it (agents, chat, jd_generator, career_roadmap).
- **Request-ID:** echo `X-Request-ID` for correlation (optional).

## Mount map
| Mount | App | Module |
|------|-----|--------|
| `/api/auth/` | identity | M1 (login/refresh/logout/mfa/me/oidc) |
| `/api/billing/` | billing | M1 + M11 |
| `/api/cycles/`, `/api/goals/` | cycles, goals | M2 |
| `/api/reviews/` | reviews | M3 |
| `/api/feedback/` | feedback | M4 |
| `/api/approvals/` | approvals | M5 |
| `/api/jd/` | jd | M6 |
| `/api/org/` | org | M7 |
| `/api/succession/` | succession | M8 (management-only; employees → 404) |
| `/api/career/` | career | M9 |
| `/api/admin/` | administration | M11 (Admin) |
| `/api/audit/` | audit | M11 (read-only console) |
| `/api/analytics/` | analytics | M-Analytics |
| `/api/integrations/` | integrations | M12 (Admin) |
| `/api/ai/` | ai | M10 (Chat) |
| `/healthz`, `/readyz` | core | liveness/readiness |

## Endpoints by module (capability · scope · notes)

### M9 — Career (`/api/career/`) — employee-visible
- `POST /target` · select_target_role · employee own / mgr+ reports · body `{employee?, target_jd?|target_position?}` (exactly one target; JD must be PUBLISHED) → `{selection, roadmap}`
- `GET /roadmap` · view · own roadmaps
- `GET /roadmaps[?employee=]` · view · scoped list
- `GET /roadmaps/<id>` · view · 404 out-of-scope
- `GET /roadmaps/<id>/skill-gap` · view · live gap (NO succession data)
- `POST /roadmaps/<id>/regenerate` · manage · refresh deterministic
- `POST /roadmaps/<id>/enrich` · manage · AI seam → **503** until M10 live
- `GET,POST /roadmaps/<id>/progress` · view / manage · tier progress

### M11 — Billing/Entitlements (`/api/billing/`) — Admin
- `GET /entitlement` · `POST /upgrade` · `PATCH /seats` (MANAGE_TENANT)
- `GET /feature-flags` · `GET /upgrade-prompt` (MANAGE_ENTITLEMENTS)

### M11 — Admin Hub (`/api/admin/`) — Admin only
- `GET,POST /users` · manage_users_roles · create `{email, role, manager?, password?}`
- `POST /users/<id>/role|deactivate|reactivate|reporting-line` · manage_users_roles (cycle → 422)
- `GET,PUT /tenant-config` · manage_tenant_config · `{settings:{}}`

### M11 — Audit Console (`/api/audit/`) — HRBP + Admin, READ-ONLY
- `GET /logs?actor=&action=&target_type=&target_id=&date_from=&date_to=&page=&page_size=` · view_audit_console · paginated (`results`/`count`); POST/PUT/DELETE → 405

### M-Analytics (`/api/analytics/`)
- `GET /individual[?employee=]` · view_individual_analytics · own / scoped trend
- `GET /department?head=&cycle=` · view_department_analytics (NEVER employee) · **min-cohort < 5 → aggregate-only (individuals suppressed)**
- `GET /calibration?cycle=` · view_calibration_grid · HRBP/Admin 9-box grid
- `GET /export?head=&cycle=&format=json|text` · view_department_analytics

### M12 — Integrations (`/api/integrations/`) — Admin only
- `GET /` · `GET,PUT /<kind>` (JIRA|SLACK) · manage_integrations · body `{enabled, config, secret_ref}` — NO secret value is ever sent/returned (only the env-var NAME)

### M10 — Chat Assistant (`/api/ai/`)
- `POST /chat` · use_chat + `requires_entitlement("chat")` · body `{query}` → read-only,
  RBAC-bound answer (returns only what the caller may see; write intents blocked);
  503 if no LLM provider, 429 if chat budget exhausted

### Earlier modules (M1–M8) — see each app's `urls.py` + `docs/BUILD_NOTES.md` API sections
- **M1 auth:** `/api/auth/{login,token/refresh,logout,mfa/*,me,oidc/complete}`
- **M2 goals/cycles:** cycles CRUD + recompute + scores; goals CRUD (weighted, =100 rule) + approve; KPI CRUD; OWN actual-update; templates
- **M3 reviews:** list/create + detail + timeline + assessments + transitions
  (start-edit/submit/approve/reject/finalize/request-ai-draft) + calibration read
- **M4 feedback:** cycles CRUD + open/close/summarize; invitations; give; continuous;
  mine/received; subject anonymised view + released summary; HRBP review/approve; 1:1 notes
- **M5 approvals:** workflow CRUD + activate; inbox; route tracker; steps approve/reject
- **M6 jd:** JD CRUD + versions/export; lifecycle (save-draft/submit/approve/revise/archive);
  generate (503 seam); templates; requests
- **M7 org:** `/tree`, `/people/<id>`, `/search`, `/export`, `/vacancies`; positions
  CRUD + fill/close/link-jd; `/reassign`
- **M8 succession (management-only, employees → 404):** dashboard; critical-roles CRUD +
  knowledge-risk/archive/bench/generate; bench readiness; nine-box; plans detail/
  action-item/publish/enrich (503 seam)

## Frontend build notes
- **Admin Hub (desktop):** billing/entitlements + feature-flags + upgrade-prompt;
  admin user/role/tenant-config; audit console (filter + paginate); integrations config;
  analytics dashboards + calibration grid.
- **Mobile-web (responsive):** self-service — own goals + actuals, own review, give
  feedback, own career roadmap + progress, chat.
- **Gate UI on `feature-flags`** (don't show locked agents/JD-gen/career-AI); show the
  upgrade prompt from `/api/billing/upgrade-prompt`.
- **HITL surfaces** (reviews, feedback summaries, succession plans, AI drafts) are all
  PENDING_HUMAN_REVIEW until a human approves — render the review/approve actions.
- Exact field shapes: read the per-app `serializers.py` (all read shapes are explicit
  + read-only; inputs are minimal).
