# Frontend Integration Spec — Talbotiq PMS

> **Purpose.** The contract between the frontend and the API: every endpoint
> (method · path · purpose · capability · scope · shape · errors), the TS data
> model + enums, state management, real-time, and the permissions/feature-flag
> visibility model. **Grounding.** The real `frontend/src/lib/api/endpoints.ts`
> (the typed client, 1:1 with the backend) + `apps/*/serializers.py` + `urls.py`
> are the authority. Where this corrects/extends the contract it is **⚠ DRIFT**.
> Mount point: all under `/api/…`. Auth header: `Authorization: Bearer <access>`.

---

## 1. Global request/response conventions

- **Auth:** JWT bearer; the token carries `tenant_id`+`role`+`email`. The frontend
  never sends a tenant id.
- **Pagination:** growth-prone lists return `{count, next, previous, results[]}`
  (`StandardResultsSetPagination`, 50/page, `?page_size=` ≤ 200). **The client must
  read `.results`/`.count`.** Config/sub-detail/small lists return **plain arrays**.
  The per-endpoint shape is marked **[paginated]** or **[array]** below.
- **HTTP status → meaning → handling** (the error-code mapper, `src/lib/errors.ts`,
  already implements this — reuse it):

| Code | Meaning | Frontend handling |
|---|---|---|
| 200/201 | OK | Render. 201 on create. |
| 400 | Bad input (shape) | Field/form error from the body; `errors.ts` extracts field errors. |
| 401 | Unauthenticated / expired | Refresh once (client interceptor); else → login. |
| 403 | **Role** lacks the capability | Hide/disable the action; "not permitted". |
| 404 | Out-of-scope / cross-tenant / not found | "Not yours / not there" — route back to the list; never imply it exists. (Succession: an employee gets 404 on the whole module.) |
| 409 | Illegal state transition / conflict | Re-fetch the entity + re-derive available actions. |
| 422 | Domain validation | Body `{detail, code}` — surface `detail`, key UI off `code` (e.g. `REPORTING_CYCLE`, `HITL_APPROVAL_REQUIRED`, `TARGET_AMBIGUOUS`). |
| 429 | Rate-limited / agent budget exhausted | Honour `Retry-After`; if `upgrade_hint` present, show the upgrade path; disable the trigger until then. |
| 503 | AI seam not configured | "AI not available" (a calm state, not an error) — the manual/deterministic path still works. |

- **The 404 rule:** out-of-scope/cross-tenant is **always 404, never 403** (403 is only
  "your role can't do this action at all").

---

## 2. Auth & identity (`/api/auth/`)

| Method · Path | Purpose | Notes / shape |
|---|---|---|
| POST `/auth/login` | Tenant-qualified login | body `{email, password, tenant_slug}` → `{access, refresh}` or an MFA-required signal; **401** on bad creds (uniform — never leaks which field). |
| POST `/auth/mfa/challenge` | Complete MFA at login | `{code}` → `{access, refresh}`. |
| POST `/auth/mfa/enroll` + `/mfa/enroll/confirm` | Enrol TOTP | → secret/otpauth_url; confirm with `{code}`. |
| POST `/auth/token/refresh` | Rotate access | `{refresh}` → new access. ⚠ DRIFT: handled in the **axios client interceptor** (`src/lib/api/client.ts`), not in `authApi` — claims survive rotation. |
| GET `/auth/me` | Bootstrap identity | → `{id, email, display_name, display, role, tenant_id, tenant_name, tenant_slug, mfa_enabled, manager_id}`. ⚠ DRIFT: `tenant_name`/`tenant_slug` added this run. |
| POST `/auth/logout` | Blacklist refresh + flush session | clear local tokens. |
| `/accounts/…` + POST `/auth/oidc/complete` | OIDC/SSO round-trip | IdP never provisions; unknown identity denied. |

State: store access in memory; never decode the JWT for authz beyond reading `role`
for routing — the server is the only authority.

---

## 3. Billing / entitlements (`/api/billing/`)

| Method · Path | Cap | Shape |
|---|---|---|
| GET `/billing/my-features` | **any role** | `{feature: bool}` for THIS user's tenant — the visibility source the whole UI gates on. ⚠ DRIFT: clarifies 00_overview's "non-admins can't read the map". |
| GET `/billing/feature-flags` | Admin | same map (admin billing screen). |
| GET `/billing/entitlement` | Admin | `{seat_count, feature_packs[], unlocked_agents[], tier_label}`. |
| GET `/billing/upgrade-prompt` | Admin | `{current_packs, tier_label, feature_flags, locked_features[], upgrade{pack, would_unlock[], note}}`. |
| POST `/billing/upgrade` | Admin | `{pack}` → flips premium flags instantly (seats unchanged). Conceptual; no payment. |
| PATCH `/billing/seats` | Admin | `{seat_count}` (≥0). |

---

## 4. Goals, KPIs, cycles (`/api/goals/`, `/api/cycles/`)

| Method · Path | Cap · scope | Shape / rules |
|---|---|---|
| GET `/cycles/` | view_team_scores | **[array]** PerformanceCycle list. |
| GET `/cycles/<id>/scores` | view_team_scores | **[array]** CycleScore (Manager TEAM / HRBP+ TENANT). |
| GET `/cycles/<id>/scores/me` | view_own | own CycleScore or null. |
| POST `/cycles/<id>/recompute` | Manager+ | idempotent recompute of the whole cohort. |
| GET `/goals/` `?employee=&cycle=` | view_own_goals (scoped) | **[paginated]** Goal {title, description, objective, weight, status, cycle, employee, approved_by/at}. |
| GET `/goals/<id>` | scoped | Goal (nested KPIs). |
| POST `/goals/` | manage_reports_goals (Manager+) | `{employee, cycle, title, weight, kpis[{name, weight, target_value, direction, unit}]}`. **422** if KPI weights ≠ 100 or active goal weights ≠ 100; `target_value` > 0. |
| POST `/goals/<id>/approve` | approve_goals | → `goal.approved`. |
| POST `/goals/kpis/<id>/actuals` | update_own_actuals | `{value}` — **own only** (a peer's → 404). |
| (KPI templates) | manage_kpi_templates (HRBP+) | list + instantiate. |

**Validation the UI must mirror:** live running-sum of KPI weights and active-goal
weights to exactly 100.00 (Decimal, 2dp; 99.99/100.01 → 422). Helper:
`src/lib/weights.ts` (`weightsSumTo100`).

---

## 5. Reviews (`/api/reviews/`)

| Method · Path | Cap | Notes |
|---|---|---|
| GET `/reviews/` `?cycle=&state=&employee=` | manage_reviews (scoped) | **[paginated]** ReviewSerializer. |
| POST `/reviews/` | manage_reviews | `{employee, cycle}` — requires an ACTIVE cycle; reviewer defaults to the actor. |
| GET `/reviews/<id>` | scoped | Review {employee, reviewer, cycle, state, draft_body, final_body, human_reviewer, approved_at, finalized_at, rejected_reason, source, confidence_score, citations}. |
| GET `/reviews/<id>/timeline` | scoped | **[array]** transitions {from,to,action,actor,at}. |
| GET/POST `/reviews/<id>/assessments` | submit_self_assessment / submit_assessment | SELF by subject; MANAGER/PEER/UPWARD by Manager+. |
| POST `/reviews/<id>/start-edit` | manage_reviews | → EDITING. |
| POST `/reviews/<id>/submit` (alias `/save-draft`) | manage_reviews | `{draft_body}` → PENDING_HUMAN_REVIEW. |
| POST `/reviews/<id>/request-ai-draft` | run_ai_review_draft | Agent 1. **503** if not configured; **403** if no `agent1` (FULL_AI). |
| POST `/reviews/<id>/approve` | approve_review | → APPROVED (sets human_reviewer). |
| POST `/reviews/<id>/reject` | approve_review | `{reason}` required → REJECTED (422 `REJECTION_REASON_REQUIRED`). |
| POST `/reviews/<id>/finalize` | finalize_review | → FINALIZED (or enters a review route). 422 `HITL_APPROVAL_REQUIRED` if not approved. |
| GET `/reviews/calibration` `?cycle=&state=` | calibrate_reviews (HRBP/Admin) | ⚠ DRIFT: the frontend uses **`/analytics/calibration`** instead — this reviews endpoint is **unused** (harmless duplicate; cleanup candidate). |

---

## 6. 360° Feedback (`/api/feedback/`)

| Method · Path | Cap | Notes |
|---|---|---|
| GET `/feedback/cycles` | manage_feedback_cycle (Manager+, scoped) | **[paginated]** FeedbackCycle. |
| POST `/feedback/cycles` | manage_feedback_cycle | `{subject, min_volume?}` → DRAFT. |
| POST `/feedback/cycles/<id>/open` | " | → COLLECTING. |
| POST `/feedback/cycles/<id>/close` | " | → CLOSED + runs summarize; returns `{cycle, summary: result}`. |
| POST `/feedback/cycles/<id>/summarize` | " | re-run Agent 3 (CLOSED only; **503** no provider). |
| GET/POST `/feedback/cycles/<id>/requests` | " | invitations {giver, relationship, status}. |
| POST `/feedback/cycles/<id>/give` | give_feedback | `{body, marked_sensitive?}` — invitation is the authz; giver server-set. |
| GET `/feedback/requests/mine` | give_feedback | **[array]** my invitations. |
| POST `/feedback/requests/<id>/decline` | give_feedback | → DECLINED. |
| GET `/feedback/mine` / `/received` | give_feedback | **[paginated]** my given / received (received is **giver-less**). |
| GET `/feedback/cycles/<id>/anonymized` | view_own_feedback_summary | the egress payload (CLOSED only; pseudonyms, volumes, `insufficient_groups`, **zero giver ids**). |
| GET `/feedback/cycles/<id>/summary` | view_own_feedback_summary | the subject's RELEASED summary; **403 `SUMMARY_NOT_RELEASED`** until released; 404 if none. |
| **GET `/feedback/my-cycles`** | view_own_feedback_summary | ⚠ NEW (this run): own-subject cycle discovery → `[{…cycle, summary_id, summary_status, summary_released}]` **[paginated]**. Lets "My 360" find the summary with no pasted id. |
| GET `/feedback/summaries/review` | approve_feedback_summary (HRBP+) | **[paginated]** the HOLD/PENDING queue. |
| POST `/feedback/summaries/<id>/approve` | approve_feedback_summary | → RELEASED. |
| GET/POST `/feedback/one-on-ones` + `<id>` | manage_one_on_one | participants ONLY (even Admin → 403). |

FeedbackSummary shape: `{sections{strengths,growth,themes,risks}|null, status, anonymity_passed, sensitive, volume_total, insufficient_groups[], insufficient_volume, confidence_score, generated_at, released_at}`.

---

## 7. Approvals (`/api/approvals/`) — all **[array]**

`GET /inbox` (steps assigned to me; SEQUENTIAL = only the active step) · `GET/POST
/workflows` + `/workflows/<id>/activate|deactivate` (configure_approval_workflow,
HRBP/Admin) · `GET /routes/<id>` + `GET /routes?artifact_type=&artifact_id=` ·
`POST /steps/<id>/approve` `{comment?}` / `POST /steps/<id>/reject` `{comment}`
(act_on_approval_step; engine enforces the assignee → 403; out-of-order/decided → 409).

---

## 8. JD Library (`/api/jd/`)

`GET /?status=&q=` **[paginated]** (non-managers see PUBLISHED only; a draft → 404) ·
`POST /` `{title, level, department}` → DRAFT · `GET /<id>` · `GET /<id>/versions`
**[array]** · `/<id>/save-draft` (`{body}` or `{inputs}`) · `/<id>/submit` · `/<id>/approve`
· `/<id>/revise` · `/<id>/archive` (manage_jd_library) · `/<id>/generate` (generate_jd;
**503** seam / **422** `INVALID_JD_INPUT` / **403** no `jd_generator` FULL_AI) ·
`GET/POST /requests` **[paginated]** + `/requests/<id>/fulfil|decline`.

---

## 9. Org chart (`/api/org/`)

`GET /tree` (nodes+edges+roots+rollups; scoped) · `GET /people/<id>` (404 out-of-scope)
· `GET /search?q=` **[paginated]** · `GET /export` · `GET /vacancies` **[array]** ·
`GET/POST /positions` **[paginated]** + `/positions/<id>` · `/positions/<id>/fill|close|
link-jd|unlink-jd` (manage_positions; fill a filled → 409; link a non-PUBLISHED JD →
422) · `POST /reassign` `{user, new_manager}` (reassign_reporting_line; a loop → **422
REPORTING_CYCLE**).

---

## 10. Succession (`/api/succession/`) — MANAGEMENT-ONLY (employee → 404 everywhere)

`GET /dashboard` (view_succession) · `GET/POST /critical-roles` **[paginated]** +
`/critical-roles/<id>/knowledge-risk|archive` (manage_critical_roles, HRBP+) ·
`GET/POST /critical-roles/<id>/bench` **[paginated]** + `/bench/<id>/readiness`
(manage_bench) · `GET/POST /nine-box` **[paginated]** (assess_nine_box) ·
`POST /critical-roles/<id>/generate` (generate_succession_analysis, HRBP+) ·
`GET /plans/<id>` + `/plans/<id>/action-item` + `/plans/<id>/publish`
(publish_succession_plan, HRBP+) · `POST /plans/<id>/enrich` (Agent 4 → **503** /
a new AI plan). Publish only from PENDING (409 `ILLEGAL_PLAN_TRANSITION`).

---

## 11. Career (`/api/career/`)

`POST /target` `{employee?, target_jd? | target_position?}` (select_target_role; exactly
one target → 422 `TARGET_AMBIGUOUS`; JD must be PUBLISHED → 422 `TARGET_NOT_PUBLISHED`)
→ `{selection, roadmap}` · `GET /roadmap` **[paginated]** (own) · `GET /roadmaps?employee=`
**[paginated]** (scoped) · `GET /roadmaps/<id>` · `GET /roadmaps/<id>/skill-gap` ·
`POST /roadmaps/<id>/regenerate` (manage_career_roadmap) · `POST /roadmaps/<id>/enrich`
(Agent → **503**; `career_roadmap` FULL_AI) · `GET/POST /roadmaps/<id>/progress`
`{tier_index, status}`. ⚠ GAP: **no "accept AI roadmap → ACTIVE" endpoint** (see
architecture-map §4.9). The client (`careerApi`) was completed this run.

---

## 12. Analytics (`/api/analytics/`)

`GET /individual?employee=` (view_individual_analytics; own-scoped for Employee) ·
`GET /department?head=&cycle=` (view_department_analytics, Manager+ — **Employee →
403**; `cycle` required → 400; **`suppressed:true` + aggregate-only when cohort < 5**)
· `GET /calibration?cycle=` (view_calibration_grid, HRBP/Admin) · `GET /export?head=&
cycle=&format=json|text`.

---

## 13. Admin · Audit · Integrations · AI

- **Admin (`/api/admin/`):** `GET/POST /users` **[array]** + `/users/<id>/role|
  deactivate|reactivate|reporting-line|display-name`; `GET/PUT /tenant-config`. Admin
  only (manage_users_roles / manage_tenant_config). 422 EMAIL_TAKEN / UNKNOWN_ROLE;
  reassignment cycle-checked.
- **Audit (`/api/audit/logs`):** `?actor=&action=&target_type=&target_id=&date_from=&
  date_to=&page=&page_size=` **[paginated]** (view_audit_console, HRBP+). **No write
  surface (POST/PUT/DELETE → 405).**
- **Integrations (`/api/integrations/`):** `GET /` **[array]** + `GET/PUT /<kind>`
  (JIRA|SLACK, manage_integrations, Admin). `secret_ref` = an env-var NAME, **never a
  token value**; not-configured → 404.
- **AI (`/api/ai/`):** `POST /chat` `{query}` (use_chat + entitlement `chat`) →
  `{status, intent, answer, data?}` — `status` ∈ ok | blocked (write intent); 503 not
  configured; 429 budget. `GET /nudges` **[array]** (Manager+; Employee → 403) →
  `[{employee, level, message}]`.

---

## 14. The TypeScript data model + enums

The authoritative types live in `src/lib/types.ts`; enums in `src/lib/enums.ts`. Key
unions a designer/engineer must know:

- **Role** `EMPLOYEE | MANAGER | HRBP | ADMIN` (+ `ROLE_RANK` for `atLeast` gating).
- **FeatureKey** `agent1 | agent2 | agent3 | agent4 | agent5 | chat | jd_generator |
  career_roadmap`; **FeaturePack** `STARTER | FULL_AI`.
- **Review.state** `DRAFT | AI_DRAFTING | PENDING_HUMAN_REVIEW | EDITING | APPROVED |
  REJECTED | FINALIZED`; **source** `MANUAL | AI`.
- **Goal.status** `DRAFT|ACTIVE|ACHIEVED|MISSED|ARCHIVED`; **CycleScore.risk_status**
  `ON_TRACK|AT_RISK|CRITICAL`; **Kpi.direction** `INCREASING|DECREASING`.
- **FeedbackCycle.status** `DRAFT|COLLECTING|CLOSED`; **FeedbackRequest** rel
  `SELF|MANAGER|PEER|UPWARD`, status `PENDING|SUBMITTED|DECLINED`; **FeedbackSummary.
  status** `PENDING_HUMAN_REVIEW|HRBP_HOLD|APPROVED|RELEASED`.
- **JobDescription.status** `DRAFT|PENDING_HUMAN_REVIEW|IN_REVIEW|PUBLISHED|ARCHIVED`.
- **Position.status** `OPEN|FILLED|CLOSED`.
- **Succession:** readiness `READY_NOW|READY_SOON|DEVELOPING|NOT_READY`; coverage
  `RED|AMBER|GREEN`; criticality `HIGH|CRITICAL`; SuccessionPlan.status `DRAFT|
  PENDING_HUMAN_REVIEW|PUBLISHED`.
- **DevelopmentRoadmap.status** `DRAFT|ACTIVE|ARCHIVED`; **source** `DETERMINISTIC|AI`;
  RoadmapProgress `NOT_STARTED|IN_PROGRESS|DONE`.
- **ApprovalRoute/Step.status** `PENDING|IN_PROGRESS|APPROVED|REJECTED|ESCALATED|SKIPPED`.

Status→colour is centralised in `components/StatusBadge.tsx` (`STATUS_VARIANT`) — the
single source of badge semantics; reuse it for any new status.

---

## 15. State management (current + recommended)

- **Server state:** **React Query** (already used) — query keys per feature, invalidate
  on mutation. Keep this; standardise key conventions + invalidation in the redesign.
- **Auth/session:** a React context (`AuthContext`) holds `me` + the feature-flag map
  (loaded once via `my-features`) + `atLeast`/`hasFeature`. The axios client holds the
  access token in memory + a refresh interceptor.
- **Global UI:** the chat panel is a context provider; toasts via `sonner`.
- **Local/ephemeral:** RHF + zod for forms; component `useState` for dialogs/filters.
- **Cached/derived:** `useDirectory` resolves user UUIDs → display names (so screens
  show names without threading them through every payload).

## 16. Real-time

**No websockets/SSE.** Async work (AI_DRAFTING, route progress, summary generation)
completes server-side; the frontend **polls / refetches after actions**. Redesign
guidance: make this *feel* live — poll an AI_DRAFTING review with a "generating…"
skeleton, refetch the route tracker after a decision, optimistic-update mutations and
invalidate. A websocket/SSE layer would be a backend addition (out of scope).

## 17. Permissions / feature-flag visibility model

1. **Role gating (UX):** `atLeast(min)` via `ROLE_RANK` (RoleGate routes, nav items).
   The server independently enforces; UI gating is for clarity, not security.
2. **Scope:** never assume; an out-of-scope detail/action returns 404 → route back.
3. **Feature flags:** `hasFeature(key)` from the `my-features` map. A locked premium
   feature renders **disabled + "Upgrade to unlock"** (FeatureGate), never hidden;
   admins get an upgrade link, others "ask your admin". A 503 on an AI surface is the
   "not configured yet" calm state (distinct from "locked").

## 18. Known gaps / cleanups (for the redesign backlog)
- **Career:** no "accept AI roadmap → ACTIVE" endpoint (the AI roadmap stays DRAFT).
- **Duplicate calibration:** `/reviews/calibration` is unused (UI uses
  `/analytics/calibration`) — remove or document.
- **No `/dashboard` aggregate endpoint** — dashboards compose client-side (fine, but a
  premium "command center" may want a thin aggregate read).
- **No notifications endpoint** — counts are derived from inbox/requests/summaries/
  nudges; a unified notifications read would clean up the shell affordance.
- **Push/device-token endpoint** — needed when mobile lands (see `MOBILE_BUILD_PLAN.md`).
