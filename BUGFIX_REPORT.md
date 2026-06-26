# BUGFIX_REPORT — hands-on test round (post Groq→OpenAI swap)

Four bugs from a hands-on test, fixed in priority order — root-cause (not patch), each
with a test and verified live, committed + pushed per fix. RBAC / HITL / tenant scope
intact throughout; no real LLM calls in the test suite (FakeLLMProvider).

> A note on the theme: **two of the four were stale-deployment bugs, not logic bugs.**
> The running containers were older than the code. BUG 1 was a crash-looping Celery
> worker; BUG 3 was a frontend image that hadn't successfully rebuilt since Jun 21
> because the Docker build was silently broken. Both are now fixed at the root so the
> running stack matches the source.

| # | Bug | Root cause | Commit |
|---|---|---|---|
| 1 | "Request AI Draft" hangs forever | Celery worker crash-looping on a top-level `onelogin` import | `83fa069` |
| 2 | Login doesn't ask for a password | Not a server defect (persisted session); closed the mock footgun | `36e9b56` |
| 3 | Goals approve doesn't update live | Stale frontend bundle — Docker build broken since the 8.1 shared-layer move | `a0bc723` |
| 4 | JD library crashes | `.join` on an undefined list when a JD body is partial/empty | `a1cfa71` |

**Suite status:** backend **1213 passing, 2 deselected** (+2 this round: SAML lazy-import
guard, OpenAI timeout). Frontend **83 vitest passing** (+7 this round: 3 AuthGuard, 4
normalizeBody); `tsc` clean, `eslint` clean, `vite build` clean.

**Active AI provider: OpenAI** (`gpt-4o` / `gpt-4o-mini`) — confirmed working live (a review
draft completed in ~4s, landed PENDING + metered + confidence 0.88). No Groq fallback needed.

---

## BUG 1 — "Request AI Draft" hangs forever (infinite spinner)

**Symptom.** Requesting an AI review draft span for 10+ minutes and never completed.
Started after the Groq→OpenAI swap.

**Root cause (NOT the swap).** The Celery **worker and beat were crash-looping** on startup:
`ModuleNotFoundError: No module named 'onelogin'`. The W1 SAML SP code imported
`python3-saml` (`onelogin`) at **module top level** in `apps/identity/saml/{views,service}.py`.
Those modules are pulled in when Django builds the URLconf — which also happens in the
Celery worker (it imports the Django app). The worker image lacks that HTTP-only SSO
dependency, so the import killed it. With the worker dead, every "Request AI Draft"
enqueued an `AIJob` that **nobody ran** → the client polled a job that never reached a
terminal state → infinite spinner. (A `docker compose restart` earlier surfaced this
latent breakage; restart doesn't rebuild.)

**Fix.** Import `onelogin` **lazily**, inside the SAML request handlers, so the URLconf
imports everywhere (including the worker) without the dependency. SAML still works on web
(which has the dep) — proven by the existing metadata/login/acs tests. Also hardened the
provider HTTP call to a `(connect, read)` timeout in both providers so a slow/unreachable
OpenAI degrades to a clean error in seconds (defence in depth — a 30s timeout already
existed; the infinite hang was the dead worker, not a missing timeout).

**Files.** `apps/identity/saml/views.py`, `apps/identity/saml/service.py`,
`apps/ai/openai_provider.py`, `apps/ai/groq.py`.
**Tests (+2).** SAML modules must not import `onelogin` at top level (the worker-hang
invariant); provider request carries a bounded `(connect, read)` timeout.
**Verified live.** Brought the worker up → it drained the stuck queue; two review-draft
jobs completed against OpenAI in ~3.7s / ~3.9s → review `PENDING_HUMAN_REVIEW` (HITL
intact), metered (gpt-4o, 535+210 tokens), confidence 0.88. No more spinner.

## BUG 2 — Login doesn't ask for a password

**Symptom.** Visiting `/login` appeared to walk straight into the app with no credentials.

**Root cause — not a server defect.** Verified live with a headless browser against the
served app: a **fresh/incognito** session at `/login`, `/`, and deep links all **require
login** (redirect to `/login`, password field shown, no app shell); wrong credentials are
rejected by the real backend; `/api/auth/me` 401s without a token. The "walk straight in"
was a **persisted, still-valid refresh token** from an earlier login (remember-me), which
`AuthContext` validates via `/api/auth/me`. Clearing site data / incognito requires login.

The one real passwordless path in the repo: `VITE_USE_MOCKS` defaulted to `true`, and mock
mode shows "any password works" + auto-authenticates. The Docker build already forces it
`false` (so the served app was always safe), but a bare `npm run dev`/`build` would be
passwordless.

**Fix.** Flipped the `frontend/.env.example` default to `VITE_USE_MOCKS=false` so the safe
path is the default everywhere and mocks are an explicit opt-in. (The host-local gitignored
`.env` is flipped too; not committed.)
**Files.** `frontend/.env.example`.
**Test (+3).** AuthGuard unit test — unauthenticated → redirect to `/login` (no protected
content), loading → loader (not the app), authenticated → content.
**Verified live.** Fresh session → login required; wrong creds rejected; correct creds enter.

## BUG 3 — Goals approval doesn't update in real time (regression)

**Symptom.** Approving a goal showed the toast but the row stayed "Awaiting approval" until
a full reload — despite the prior fix (prefix-invalidate the goals list query).

**Root cause — stale deployment, not the React code.** The prior fix (`1a2849e`, Jun 22
00:21) is correct and unit-tested, but the **served frontend image was built Jun 21 17:23**
and **never successfully rebuilt since**. BUILD_8 8.1 moved the shared layer to the
repo-root `shared/` dir, consumed via the `@shared` alias (`../shared/src`). The frontend
Docker build context was `./frontend`, so the sibling `shared/` was never copied → the
`@shared` re-export shims resolved to nothing → `tsc --noEmit` failed → the build broke.
The failure was masked (build piped to `tail`, exit code lost), so the old bundle kept
serving — and **every** post-Jun-21 frontend fix (this one, BUG 4, the chat-intent fix, the
career-roadmap fix, the a11y pass) never reached the browser.

**Fix.** Build the frontend from the **repo root** so `shared/` is a sibling at `../shared`:
compose `context: .` + `dockerfile: frontend/Dockerfile`; the Dockerfile copies `shared/`
into `/app/shared` and frontend into `/app/frontend` (reproducing the local layout the alias
expects); `.dockerignore` excludes `**/node_modules`, `**/dist`, `frontend/.env` so host
artifacts can't leak into the now repo-root context.
**Files.** `docker-compose.yml`, `frontend/Dockerfile`, `.dockerignore`.
**Test.** The existing `useGoals` invalidation test already covers the code fix; this commit
unblocks its **deployment**.
**Verified live.** Freshly rebuilt + deployed bundle (`index-C-pjkoeb.js`): clicking Approve
flipped the row **without a reload** — Approve buttons 6→5, "Awaiting approval" 6→5,
"Approved" +1.

## BUG 4 — JD library crashes

**Symptom.** Opening/generating a JD (e.g. a manual "staff" draft) threw "This screen hit an
unexpected error".

**Root cause.** The backend stores `JDVersion.body` as a `JSONField` defaulting to `{}` (a
manual draft, or a JD before any AI/author body) — one seeded JD even had `body=[]`. The
editor effect did `body.responsibilities.join("\n")` (and `must_haves`/`nice_to_haves`)
directly, so a missing/empty list was `undefined` and `.join` threw a `TypeError` → the
error boundary replaced the whole screen. (The read-only `Section` already guarded `!items`;
the editor path did not.)

**Fix.** A `normalizeBody()` helper coerces any partial/null/`[]` body into a complete
`JdBody` (`summary ""` + the three arrays `[]`), applied at the editor effect and the read
view — so a bad/empty body degrades gracefully.
**Files.** `frontend/src/features/jd/JdDetailPage.tsx`.
**Test (+4).** `normalizeBody` handles `{}`, `null`, `undefined`, partial and complete bodies,
and the exact `.join` the editor performs never throws.
**Verified live.** Opening the `body=[]` "staff" JD now renders the detail screen — no error
boundary, no crash.

---

## What needs your device / eyes

Everything above is fixed and verified by automation, but two items are best double-checked
by you in a real browser:

1. **BUG 2 (login):** to *see* the login screen yourself, **clear site data for
   localhost:8080 or use an incognito window** — your current tab holds a valid session, so
   it (correctly) won't ask again. A fresh session does require credentials (verified).
2. **BUG 3 / BUG 4 (frontend fixes):** your browser may serve the **old cached bundle** —
   do a **hard refresh** (Cmd-Shift-R) on localhost:8080 so it loads `index-C-pjkoeb.js`,
   then confirm goals-approve updates instantly and a manual JD opens without the crash.

## Operational notes (not bugs, worth knowing)

- The frontend image had been **un-rebuildable since Jun 21**; it now rebuilds cleanly from
  the repo root. Rebuild the frontend after frontend changes:
  `docker compose build frontend && docker compose up -d frontend`.
- The Celery **worker/beat** must be running for any AI draft/feedback/JD/career/succession
  job to complete; they now start cleanly. Watch jobs in Flower (localhost:5555).
- Active LLM provider is **OpenAI** and the key is loaded — AI actions cost real (tiny) money
  per call. The data-egress sign-off for review/JD/career (names + KPIs to OpenAI) is still
  open in `docs/AI_GOLIVE.md` (feedback/succession are name-free).
