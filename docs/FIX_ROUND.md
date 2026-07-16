# FIX_ROUND — account features, integrations, AI-hang, scroll/layout

**Date:** 2026-07-14 · **App:** http://localhost:8090 · **Tenant:** `acme` · **Password:** `Passw0rd!demo`

Six fixes across the four areas, each root-caused, committed, and verified live. Backend
tests green; per-item retest steps at the bottom. Nothing weakened RBAC/HITL/tenant/audit —
the integrations change *removes* an unusable surface, the others *tighten* behavior.

| # | Area | Fix | Commit |
|---|------|-----|--------|
| 1 | Profile photo upload | send avatar as real multipart (was JSON) | `eb32fe2` |
| 2 | Integrations UI | hide Jira + Slack; notifications = email + in-app | `a6980f9` |
| 3 | Admin deep-links | stop proxying `/admin/*` to Django (SPA owns it) | `36e8d4b` |
| 4 | AI drafting hang | Celery soft time-limit force-fails a stuck job | `089a92e` |
| 5 | Scroll / dashboards | list tiles scroll inside fixed-height cards | `95d90f8` |

Account features 2–6 in the goal (password/email/prefs/2FA/sessions) were already functional —
re-verified live this round (see item 2 evidence). The one broken account feature was the photo.

---

## 1 · Profile photo upload — FIXED (`eb32fe2`)

**Symptom:** uploading a valid ~1.6 MB PNG failed.

**Root cause (client, not server):** the axios instance hard-sets
`Content-Type: application/json` (`shared/src/api/client.ts`). In axios 1.x a `FormData`
body only gets the `multipart/form-data; boundary=…` header **auto-computed when Content-Type
isn't already set**. With the JSON default forced, the avatar was sent as `application/json`
with no multipart boundary → DRF's `MultiPartParser` parsed nothing → `request.FILES` empty →
the view returned 400 "photo required". The backend was correct all along.

**Fix:** the request interceptor now deletes `Content-Type` when the body is `FormData`, so
axios sets the proper multipart header + boundary. General fix — covers any future upload.

**Proof the backend was fine + is correct:** a real multipart probe (scratchpad
`verify_photo.py`) uploaded a 1.6 MB PNG (200, streamed back 1,600,008 bytes), a JPG (200),
and correctly rejected a GIF (400 "Only JPEG, PNG or WebP") and a >2 MB file (400 "Max size
is 2 MB"). Magic-byte sniff + size cap + UUID filename under a tenant prefix all intact.

## 2 · Integrations + notifications — FIXED (`a6980f9`)

**Decision: removed BOTH Jira and Slack from the UI.**
- **Jira** — scaffolded, never connected (needs an API-token round-trip). Removed.
- **Slack** — also removed. It's webhook-based (no OAuth), but **delivery is not wired**:
  no code fires Slack on domain events (the worker even logs "Slack notify no-op … no enabled
  Slack integration"), and the settings card itself admitted Slack notifications are "v2".
  A toggle that can't deliver is exactly the broken-looking feature to cut. If/when Slack
  delivery is actually wired, re-add it — the backend `apps/integrations` code is kept.
- **Notifications** now show **Email + In-app only** — the two that work. Email delivers
  today (password reset, invitations, email-change confirmation; console backend in dev, SMTP
  in prod). In-app is the top-bar bell (real pending-actions count). The Slack channel toggle
  was removed from Settings.

**What changed:** the `/admin/integrations` route + `IntegrationsPage` import were removed from
the router (`frontend/src/app/router.tsx`); the code file is kept for v2. The Slack row was
removed from `NotificationPrefsCard` (`SettingsPage.tsx`) and the note text made honest. The
nav item was already gone.

**Live-verified this round (account features re-confirmed):** the Phase-2 HTTP probe passed
49/49 (profile edit, password change → sessions revoked, email change, sessions list/revoke,
lockout, plan gating), and a full **2FA round-trip** (`verify_2fa.py`) passed:
enroll → confirm (computed TOTP) → login now MFA-gated → challenge → disable → plain login again.
(2FA anti-replay correctly rejects a reused code — expected django-otp behavior.)

## 3 · Admin pages deep-link 404 — FIXED (`36e8d4b`)

**Found while verifying item 2.** A hard GET / refresh on `/admin/users`, `/admin/billing`
(and the removed `/admin/integrations`) returned **404**, while `/goals`, `/settings` etc.
worked. Cause: `frontend/nginx.conf` proxied `^/(api|admin|accounts|…)` to Django, so every
SPA client route under `/admin/*` was handed to the backend — which has **no Django admin
mounted** (`admin.site.urls` is absent; the only backend admin path is `/api/admin/`, already
covered by the `api` token). So the bare `admin` token served nothing and only 404'd the SPA's
own admin pages on refresh.

**Fix:** dropped the bare `admin` token from the proxy regex. `/admin/*` now falls through to
the SPA (`try_files … /index.html`); `/api/admin/` is still proxied via `api`. Verified:
`/admin/users`, `/admin/billing`, `/admin/integrations` → 200 (SPA loads; integrations then
client-redirects to the dashboard since its route is gone); `/api/auth/me` → 401 (still proxied).

## 4 · "Drafting with AI…" hang — FIXED (`089a92e`)

**Investigation:** the frontend polling was already correct — `useAIJob` polls the job every
1.5 s and stops at a terminal status (SUCCEEDED/DEGRADED/FAILED), and `AIJobBanner` shows a
spinner while RUNNING, a retry on FAILED, a calm note on DEGRADED. The `run_agent_job` wrapper
marks FAILED on any exception and always classifies the result to a terminal state. The Gemini
provider has a 30 s read timeout with ≤3 retries (worst case ~90 s → FAILED). So a *typical*
slow Gemini call resolves; it just feels long on a "thinking" model.

**The real gap:** there was **no Celery task time limit**. If a seam blocked in a path the
per-request timeout didn't cover (a hung socket, a starved worker), the task never returned,
the job stayed RUNNING forever, and the UI polled a spinner with no resolution — a true hang.

**Fix:** `run_agent_job` now has a **soft time limit (120 s) + hard limit (150 s)**
(`AI_JOB_SOFT_TIME_LIMIT` / `AI_JOB_HARD_TIME_LIMIT`, settings-tunable). The soft limit raises
`SoftTimeLimitExceeded` *inside* the task, which is caught and lands the job **FAILED /
error_code TIMEOUT** — so the spinner always resolves to the honest retry banner. 120 s sits
above the provider's own worst case so a slow-but-completing draft isn't killed. Regression
test `test_soft_time_limit_marks_job_failed_timeout` (job terminal, no fabricated draft).

## 5 · Scroll + consistent dashboard cards — FIXED (`95d90f8`)

**Root cause:** `ApprovalsInboxTile` rendered the whole approval inbox as an **uncapped** list
with no scroll — it stretched the dashboard arbitrarily long. Other tiles already `.slice()`.

**Fix (layout only, no data lost):** added a `scroll` prop to the shared `Panel` (and the
mirror `DashboardSection`) that caps the body height and scrolls internally
(`max-h` + `overflow-y-auto` + `scrollbar-thin`). Applied to the growable dashboard tiles —
Approval inbox, KPI nudges, Stale goals, Succession risk — and the manager "Team performance"
table. Every list now scrolls **within a fixed-height card** instead of stretching the page;
all rows remain reachable by scrolling, and each card's header keeps its "View all" link to
the full screen. Consistent card shape across roles (cockpit-roles already shares `Panel`;
manager uses the now-matching `DashboardSection`).

---

## Exact retest steps (all at http://localhost:8090, password `Passw0rd!demo`)

**1. Photo upload** — login `akhil@acme.test` → avatar menu → My Settings → **Upload photo**
→ pick a real JPG or PNG under 2 MB. SEE: "Photo updated", the avatar shows immediately.
Try a 3 MB image → "Max size is 2 MB". Try a .txt renamed .png → "Only JPEG, PNG or WebP".

**2. Integrations gone** — as `admin@acme.test`: the sidebar has **no** Integrations item;
browse to `/admin/integrations` directly → you land on the dashboard (no Jira/Slack screen).
My Settings → Notification preferences shows **Email** and **In-app** only (no Slack).

**3. Admin deep-links** — as `admin@acme.test`, go to **Users & Roles**, then **reload the
browser** (F5). SEE: the page reloads and still shows Users (not a 404). Same for
**Entitlements** (`/admin/billing`).

**4. AI drafting** — `ada@acme.test` → a report's review in DRAFT → **Request AI draft**.
SEE: "AI is working…" then, when Gemini returns, the PENDING draft appears (HITL). If the
provider is down/slow past the limit, within ~2 min it flips to "AI step failed — try again"
with a Retry button — never an endless spinner. (To force the failure state you can stop the
`celery-worker` container; the job lands FAILED at the soft limit.)

**5. Scroll** — `ada@acme.test` dashboard: the **Approval inbox** / **KPI nudges** cards stay
a fixed height and scroll inside when there are many rows; the page no longer grows to
thousands of lines. Manager **Team performance** table scrolls within its card for a big team.

## Not touched (as instructed)
Payments and the auth-cookie migration remain design-staged — untouched.

## For your visual pass
These are live-verified over HTTP + build, but the pixel-level look is yours to confirm:
avatar cropping/rounding, the exact card heights feel right on your screen, and the AI retry
banner styling. Everything else (routes, uploads, gating, scroll behavior) is machine-verified.
