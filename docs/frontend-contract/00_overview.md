# Frontend Contract — 00 · Overview & Global Conventions

This contract specifies **what** the frontend must render and handle (data, states,
actions, errors, permissions) — **not how it should look**. Visual design (colour,
layout, components) is the frontend team's job. Everything here is derived from the
actual backend code (serializers, views, urls, the RBAC matrix, the state machines).

Companion files: `01_screens.md` (screen inventory), `02_state_machines.md`,
`03_data_dictionary.md`, `04_role_journeys.md`, `05_open_questions.md`. The
endpoint map + payload index lives in `docs/FRONTEND_READINESS.md`; exact field
shapes live in each app's `serializers.py` (named per screen).

---

## The two surfaces

| Surface | For | Primary roles |
|--------|-----|---------------|
| **Desktop Admin Hub** | Management + configuration work (multi-pane, data-dense) | HRBP, Admin, Manager |
| **Mobile-Web (responsive)** | Self-service (single-task, on-the-go) | Employee, Manager |

A Manager uses **both**: the Hub for team management (reviews, approvals, bench,
analytics) and Mobile-Web for their own self-service (own goals, own review, own
career roadmap, chat).

### Screen reachability by role × surface
Legend: **D** = Desktop Hub, **M** = Mobile-Web, — = not reachable.

| Feature area | EMPLOYEE | MANAGER | HRBP | ADMIN |
|---|---|---|---|---|
| Auth / MFA | M | D·M | D | D |
| Dashboard (role-scoped) | M | D·M | D | D |
| Goals & KPIs (own) | M | D·M | D·M | D·M |
| Goals & KPIs (team manage/approve) | — | D | D | D |
| Reviews (own, read finalized) | M | M | M | M |
| Reviews (manage/draft/approve) | — | D | D | D |
| Review calibration | — | — | D | D |
| 360 Feedback — give / requests | M | M | M | M |
| 360 Feedback — run cycle / invite | — | D | D | D |
| 360 Feedback — summary review/release | — | — | D | D |
| 1:1 notes (participants only) | M | D·M | D·M | D·M |
| Approvals — inbox / act | — | D | D | D |
| Approvals — route tracker | M* | D | D | D |
| Approvals — workflow designer | — | — | D | D |
| JD library — browse (PUBLISHED) | M | D·M | D | D |
| JD — author / lifecycle / generate | — | — | D | D |
| JD — request a JD | — | D | D | D |
| Org chart / person card / vacancies | M (own line) | D (subtree) | D (tenant) | D (tenant) |
| Org — reassign / positions | — | — | D | D |
| **Succession (dashboard/9-box/bench/plan)** | **— (404)** | D (own tier) | D (tenant) | D (tenant) |
| Career roadmap (own) | M | D·M | D·M | D·M |
| Career roadmap (reports) | — | D | D | D |
| Analytics — individual (own) | M | D·M | D·M | D·M |
| Analytics — department | — | D | D | D |
| Analytics — calibration grid | — | — | D | D |
| Admin — users/roles/tenant config | — | — | — | D |
| Audit console | — | — | D | D |
| Integrations config | — | — | — | D |
| Billing / entitlements / upgrade | — | — | — | D |
| AI Chat panel | M | D·M | D·M | D·M |

\* The route tracker is visible to the route's initiator / an approver / a
config-holder; an employee generally only sees it if they initiated a route.
**Succession is invisible to employees — every succession endpoint returns 404 for
an employee (not 403). Mobile-Web must NOT contain any succession surface.**

---

## Auth flow (end-to-end)

All under `/api/auth/`. The JWT carries `tenant_id` + `role` + `email` — **the
frontend NEVER sends a tenant id**; it is bound server-side from the verified token.

1. **Login** — `POST /api/auth/login` with tenant-qualified local credentials
   (email + password + a tenant hint, e.g. slug). → `{access, refresh}` on success;
   **401** on bad credentials. If the user has MFA enabled, login returns an
   MFA-required signal and the client must complete step 2 before it holds usable
   tokens.
2. **MFA** (only when `user.mfa_enabled`):
   - Enrolment: `POST /api/auth/mfa/enroll` → provisioning secret/QR data →
     `POST /api/auth/mfa/enroll/confirm` with a TOTP code.
   - Challenge at login: `POST /api/auth/mfa/challenge` with the TOTP code → tokens.
3. **Authenticated requests** — send `Authorization: Bearer <access>` on every call.
4. **Refresh** — `POST /api/auth/token/refresh` with the refresh token → a new
   access (claims survive rotation). Refresh proactively on 401-due-to-expiry.
5. **Who am I** — `GET /api/auth/me` → the current user (id, email, role, tenant,
   mfa_enabled). Use it to bootstrap role-based routing.
6. **Logout** — `POST /api/auth/logout` (blacklists the refresh token + flushes the
   session). Clear local tokens.
7. **OIDC / SSO** — the IdP round-trip is handled at `/accounts/...` (django-allauth);
   on success the backend mints the same JWTs and the SPA continues as in step 3
   (`POST /api/auth/oidc/complete` finalises the mapping). The IdP never provisions
   accounts — an unknown identity is denied.

**Token storage:** store the access token in memory (and refresh in a secure,
http-only-style store per your platform); never decode it for authorization
decisions beyond reading `role` for routing — the server is the only authority.

---

## Global conventions (every screen obeys these)

### HTTP status → meaning
| Code | Meaning | Frontend handling |
|---|---|---|
| **200/201** | OK | Render. 201 on create. |
| **400** | Bad input (shape) | Show field/form error from the body. |
| **401** | Unauthenticated / token expired | Try refresh once; else route to login. |
| **403** | Role not permitted | Hide/disable the action; show "not permitted". A *role* lacks the capability. |
| **404** | Out-of-scope / cross-tenant / not found | Treat as **"not yours / not there"** — never reveal it existed. (Succession: an employee gets 404 on the whole module.) |
| **409** | Illegal state transition / conflict | The action isn't valid from the current state (e.g. publish twice, fill a filled position). Refresh the entity + re-derive available actions. |
| **422** | Domain validation | Body carries `{detail, code}` (e.g. `REPORTING_CYCLE`, `INVALID_JD_INPUT`, `TARGET_AMBIGUOUS`). Surface `detail`; key UI off `code`. |
| **429** | Rate-limited or agent budget exhausted | Honour `Retry-After` (seconds); if the body has `upgrade_hint`, show an upgrade prompt. Back off + disable the trigger until then. |
| **503** | AI seam not configured | An AI feature isn't live yet. Show "AI not available" (not an error) — the deterministic/manual path still works. |

### The "404 = not yours/not there" rule
The backend returns **404 (never 403)** for out-of-scope or cross-tenant rows, so
the UI must treat 404 on a detail/action as "this isn't in your scope" and route
back to the list — it must never imply the record exists elsewhere. (403 is only
for "your *role* can't do this action at all".)

### Throttling (429)
Per-tenant + per-user limits (entitlement-driven). On 429: read `Retry-After`,
disable the triggering control for that long, and if `upgrade_hint` is present,
offer the upgrade path. AI agent calls also carry a per-tenant **budget**; a
budget-exhausted 429 body includes `agent_code`, `window`, `limit`, `upgrade_hint`.

### Feature flags drive premium UI
`GET /api/billing/feature-flags` (Admin) → a complete `{feature: bool}` map for
every gated feature: `agent1` (Review Assistant), `agent2` (KPI Intelligence),
`agent3` (Feedback Summary), `agent4` (Succession Analyzer), `agent5`,
`jd_generator`, `career_roadmap`, `chat`. **Commercial packaging:** STARTER unlocks
only `agent2` + `chat`; **every generative agent — including Agent 1 — plus the JD
generator and career roadmap are FULL_AI (premium).** The UI must render a locked
premium feature as **disabled + "Upgrade to unlock"** (drive the upgrade modal from
`GET /api/billing/upgrade-prompt`), never hidden silently. `chat` + `agent2` are the
STARTER "AI taste". (Non-admin clients can't read the flag map directly — derive
availability from 503/403 on the agent surfaces, or have the Hub surface the map.)

### Request correlation
Echo any inbound `X-Request-ID`, or omit it; the server mints one and returns it.
Log it client-side for support correlation.

---

## The HITL principle (the UI MUST reflect this)

Reviews, 360 feedback summaries, succession plans, AI-generated JDs, and AI career
roadmaps are all locked **`PENDING_HUMAN_REVIEW`** (or an equivalent draft/hold)
until a human approves/publishes. The UI must:
- **Never present a draft as final** — badge AI/draft content as "Draft — pending
  review" with the confidence score + a low-confidence warning when present.
- **Always offer the human gate** — render Approve / Reject (reason required) /
  Edit / Publish / Release affordances to the role that holds the gating capability.
- **Show provenance** — `source = AI | MANUAL | DETERMINISTIC` and a confidence
  score where the entity carries one.
- An AI output can NEVER be auto-published; the human action is a required step in
  every relevant journey (see `04_role_journeys.md`).
