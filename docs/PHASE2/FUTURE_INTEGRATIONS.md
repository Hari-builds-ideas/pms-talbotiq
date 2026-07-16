# FUTURE_INTEGRATIONS — extension seams (design; each a plug-in, not a rewrite)

The codebase already follows a ports-and-adapters style in the two places that matter; every future
integration below reuses one of the existing seams. Grounded citations per item.

## The three existing seams
1. **Identity/SSO seam** — allauth `openid_connect` provider config (`config/settings/base.py:327+`) +
   `TenantSocialAccountAdapter` (`apps/identity/adapters.py`) + per-tenant SAML SP
   (`apps/identity/saml/`). New IdPs are CONFIG, not code.
2. **AI provider seam** — `apps/ai/providers.py` ABC + `LLM_PROVIDER` import string (OpenAI/Groq/
   Gemini already interchangeable). New model vendors implement `generate()` — nothing else changes.
3. **Notification/integration seam** — `apps/integrations/` (per-tenant config models + best-effort
   `notifications.py`). Today Slack-webhook only; the dispatch point is the seam to generalize.

## Per integration
- **Google / Microsoft login** — allauth providers (`google`, `microsoft`): add the provider app +
  per-tenant client credentials via `SOCIALACCOUNT_PROVIDERS`; identity→tenant mapping already handled
  by the adapter. Effort: small; config + one adapter test each.
- **Okta / Azure AD (enterprise SSO)** — both speak OIDC and SAML; the per-tenant SAML SP endpoints
  (`/api/auth/saml/<slug>/…`) already exist. Needs: a per-tenant IdP-metadata admin UI (today it's
  settings-side), JIT-provisioning rules per tenant. Effort: medium (admin UI), no auth rewrite.
- **Slack (real)** — the webhook notify exists; upgrade path: Slack OAuth app install per tenant
  (store bot token in `apps/integrations` config), replace raw webhook with chat.postMessage, add
  per-event-type routing. Keep the "silent no-op when unconfigured" contract.
- **Microsoft Teams** — same dispatch point; a `TeamsChannel` adapter (incoming-webhook first, Graph
  later). Design a `NotificationChannel` port: `send(tenant, event, payload)` with Slack/Teams/Email
  adapters — this is the same generalization the in-app notification center (v2) needs; build the port
  once.
- **Calendar (Google/Outlook)** — for 1:1s/check-in scheduling: OAuth per user (allauth social tokens),
  a `CalendarProvider` port (`create_event`, `list_availability`). Keep read-mostly at first.
- **HRMS / payroll (BambooHR, Workday, local payroll)** — importer framework: a `DirectorySource` port
  (`fetch_employees() → normalized rows`) + an idempotent sync job (the seed's `_ensure` pattern
  already shows the idempotent-upsert style); map to User/manager/department. Payroll export = a
  read-only CSV/API extract per cycle — never write into payroll v1.
- **Outbound webhooks (customer-facing)** — a `WebhookEndpoint` model per tenant (url, secret, event
  filter) + signed (HMAC) deliveries with retries from a Celery task; reuse the audit log as the event
  source. This is also the base for Zapier.
- **Public API** — the DRF API is already capability-gated; add: per-tenant API keys (a `ServiceToken`
  model mapping to a service user with a role), documented OpenAPI schema (drf-spectacular), and
  API-access as a plan feature (LANE-1 plan flags already reserve `api_access`).
- **AI providers** — seam done (see above); per-tenant keys is the only design question
  (`OPEN_QUESTIONS.md` #8).
- **Mobile** — backend ready (same JWT API, shared TS client); the Expo frontend is the v2 work
  (`docs/handoff/MOBILE.md`). No server seam needed.

## Order of value (recommendation)
1. NotificationChannel port + in-app center (unblocks the biggest UX gap) → 2. Google/Microsoft login
→ 3. Slack OAuth upgrade → 4. Okta/Azure admin UI → 5. Outbound webhooks → 6. HRMS import →
7. Public API keys → 8. Calendar.
