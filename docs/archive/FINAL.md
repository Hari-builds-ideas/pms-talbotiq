# FINAL.md — complete Version 1 for production handover (unattended)

You are a **Senior Staff Software Engineer** doing the FINAL production-readiness pass on this
Performance Management System (PMS) before it is handed to a separate deployment team (the Malaysia
team). Work **fully autonomously** — investigate, fix, test, document, and only stop when everything
below is done. Do not stop to ask questions; if something is genuinely ambiguous, make the simplest
correct choice for a non-expert SME user, note it in `docs/V1_REVIEW/OPEN_QUESTIONS.md`, and keep going.

## The situation (read this first)
- The CEO believes the app is ~100% complete and that only deployment remains. It is NOT — there are
  functional, usability, authorization, and readiness gaps. Be critical. Do not assume "looks done" =
  "done". Verify against the actual running code.
- The **deployment team handles deployment**, not us. They only need a correct `.env.example` and
  deployment docs; they set the real environment themselves. Our job: make the app **fully working,
  stable, tested, authorization-correct, and documented** for handover.
- **Priority = FUNCTIONALITY over visual polish.** Do NOT redesign the frontend now. Branding/redesign
  is a later phase (only prepare notes for it).

## Iron rules (never break)
- Ground EVERY finding and fix in the real code — cite `file:line`. No guessing, no fabrication.
- Never weaken RBAC, HITL (human-in-the-loop), tenant isolation, or the audit log.
- Fix bugs at root cause; commit per fix; keep backend AND frontend tests green after every change.
- Never delete a working feature. If a feature is deferred, HIDE it (flag/route/nav) and document how to
  re-enable — do not remove code.
- Never commit secrets. `.env.example` holds placeholders only.
- Real data or an honest empty state — never fake data to make a screen look full.

## How to work
1. First pass: investigate the whole app and write the review docs (section A). Fix safe P0/P1 bugs as
   you find them.
2. Then implement the larger fixes (sections B–E), each committed and tested.
3. Then produce the handover package (section F) and the later-phase prep (section G).
4. Log progress continuously to `docs/V1_REVIEW/PROGRESS.md`.
5. End with `docs/V1_REVIEW/FINAL_REPORT.md` (section H): what was fixed, what remains, the exact
   testing checklist for the human, and any open questions. If context runs low, finish the current item
   cleanly, update PROGRESS.md with a precise "resume here" note, and stop — the run can be continued by
   pointing /goal at this file again.

Write all review/documentation output under `docs/V1_REVIEW/`.

---

# A. PROJECT REVIEW (write these docs, grounded in code)

## A1 — `docs/V1_REVIEW/PROJECT_ASSESSMENT.md`
Go through EVERY module and classify each as **Complete / Partial / Missing / Broken / Risky**, with the
evidence (files) and, for anything not complete, exactly what's wrong. Cover at least:
login, dashboard (each role), goals & OKRs, reviews, check-ins, feedback/360, recognition, employees,
JD library, analytics, notifications, chat/agent, settings/admin, approvals, audit.
End with a prioritized **fix-before-deploy checklist** (P0 blocks handover / P1 should-fix / P2 nice).

## A2 — `docs/V1_REVIEW/QA_CHECKLIST.md`
A production QA checklist per module covering: CRUD operations, edge cases, error handling, loading
states, empty states, and role variations. For each line, mark what you actually verified pass/fail
against the running app (recreate containers + seed first). This is the QA record for handover.

---

# B. AUTHENTICATION REVIEW + FIX

## B1 — `docs/V1_REVIEW/AUTH_REVIEW.md`
Explain, grounded in code, exactly how auth works today:
- Login flow (endpoints, what happens on submit).
- Session handling; token storage (where the JWT lives client-side); token refresh (rotation/blacklist);
  logout (is the token invalidated?).
- Authorization (how role/permission is resolved per request).
- Security concerns (token storage location, XSS/CSRF exposure, expiry, secret handling).
- A clear verdict: is it production-ready? What must change if not.

## B2 — Fix
Implement any P0/P1 auth fixes you identified (e.g. secure token handling, correct logout invalidation,
refresh correctness). Keep it standard and safe; do not invent a bespoke scheme. Commit + test. Record
what changed in AUTH_REVIEW.md.

---

# C. AGENT MEMORY REVIEW + FIX

## C1 — `docs/V1_REVIEW/AGENT_MEMORY_REVIEW.md`
Explain how chat/agent memory works now: is it persistent (survives reload)? user-specific and
tenant-scoped? why is previous context sometimes not remembered? The read/Q&A path is known-weak (no
memory, misroutes questions like "how many reviews do I have"). Diagnose the root cause in code.

## C2 — Fix
Make the assistant reliably remember the conversation within a session: persistent, user-specific,
tenant-scoped, and used on BOTH the plan/act path and the read/Q&A path so follow-up questions have
context. Do not weaken the read-only/scope rules. Commit + test; document the fix.

---

# D. RBAC — REPORT + THE "VISIBLE BUT UNAUTHORIZED" FIX (TOP PRIORITY)

## D1 — `docs/V1_REVIEW/RBAC_MATRIX.md`
A complete permissions matrix, grounded in the server-side permission code. For EVERY role
(Admin, HRBP, Manager, Employee, and any other): pages they can access, features/APIs/actions they can
use, actions they cannot perform, and pages they must never see.

## D2 — `docs/V1_REVIEW/AUTHZ_UI_ISSUES.md` + FIX (most important item)
Find EVERY place where a user can SEE a control (button, menu item, link, page) they are not allowed to
use — so they click and get "You are not authorized" / "outside your access scope". List each occurrence
(component + file). Then FIX them with the correct pattern:
- The frontend hides any control the user's role can't use — nav items, routes, and buttons all gated
  off the SAME server-provided permissions/entitlements that enforce the action server-side (single
  source of truth; never hardcode role checks in two places that can drift).
- A role that cannot do an action never sees the button; a page it can't access isn't in the nav and
  its route redirects cleanly (no dead ends, no "not authorized" walls in normal use).
Implement the fix across every occurrence. Keep the server-side checks intact (defense in depth — hide
in UI AND enforce on the server). Commit + test. This directly addresses the #1 complaint.

---

# E. AGENT CHAT UX FIX (TOP PRIORITY)

Review the current chat-panel architecture, then implement BOTH:

## E1 — Resizable panel
The chat panel must be **resizable** (drag to widen/narrow) so the user controls how much space it takes.

## E2 — Persistent, non-blocking copilot
Navigating or clicking elsewhere must NOT close the chat. Make it a persistent, dockable side panel that
stays open while the user navigates and works — page and chat side by side, like a real AI copilot. When
the AI says "go to X page", the user clicks it, the page loads beside the still-open chat, and the
conversation continues. No auto-dismiss on navigation or outside click.
Implement, commit, test. Document the approach in `docs/V1_REVIEW/AGENT_CHAT_UX.md`.

---

# F. DEPLOYMENT HANDOVER PACKAGE (for the Malaysia team)

## F1 — `.env.example` (at repo root) — FOR THIS PMS ONLY
Produce a correct, commented `.env.example` listing EVERY environment variable THIS app actually reads
(verify against `config/settings/*` — do not copy any other project's file). Placeholders only, no
secrets. Include at least (adjust to the real code):
- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (+ replica vars if present)
- the Redis URLs the app uses (broker + cache/session) and `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
- `LLM_PROVIDER` (default to the Gemini provider), `GEMINI_API_KEY`, and the Gemini model vars
  (a fast model for chat, a stronger model for the human-read agents — it's an enterprise key)
- `LLM_MAX_CALLS`, `METRICS_TOKEN`, `SENTRY_DSN`, and `EMAIL_*` if/when wired
Each var: a one-line comment saying what it's for. Group by purpose (Django / DB / Redis / AI / etc.).

## F2 — `docs/V1_REVIEW/DEPLOYMENT_HANDOVER.md`
Everything the deployment team needs:
- Required services (web/gunicorn, celery worker, celery beat, MySQL, Redis) and the prod compose.
- Build instructions, startup instructions, how migrations run (`deploy_migrate`, advisory-locked),
  how to seed if they want demo data.
- Third-party integrations + their env (Gemini; Slack/Jira are scaffolded-not-connected — say so).
- The honest "not yet wired" list (e.g. email/SMTP if still unwired) so they aren't surprised.
- Note on the Gemini provider: confirm it's wired and works; if it needed writing, note it's done.
Do NOT include secrets — placeholders and instructions only.

---

# G. LATER-PHASE PREP (identify only, do NOT implement now)

## G1 — `docs/V1_REVIEW/BRANDING_LOCATIONS.md`
Identify WHERE the app name, logo, favicon, and color system are configured (list the files), so a later
branding pass knows what to change. Do not change them now.

## G2 — `docs/V1_REVIEW/FRONTEND_REDESIGN_PLAN.md`
Write a high-quality Claude Design prompt to later modernize the UI as an enterprise SaaS PMS while
preserving ALL existing functionality. Clearly marked as AFTER v1 — for reference, not for this run.

---

# H. FINAL REPORT

## `docs/V1_REVIEW/FINAL_REPORT.md`
- What was fixed (with commits), grouped by section.
- What remains / couldn't be done and why.
- The exact human testing checklist: log in as each role and verify (create/edit/delete works, no
  "unauthorized" walls on visible buttons, chat stays open while navigating + resizes, agent remembers
  context, every module's core path works).
- Open questions / product decisions for the human.
- Confirmation that tests are green and the handover package (`.env.example` + DEPLOYMENT_HANDOVER.md)
  is complete.

## Recommended execution order (do in this order)
1. A1 assessment + fix P0 bugs found. 2. D1/D2 RBAC matrix + the visible-but-unauthorized fix.
3. E1/E2 chat resizable + persistent. 4. B auth review + fix. 5. C agent memory fix.
6. A2 QA pass. 7. F handover package. 8. G later-phase notes. 9. H final report.

Do all of it. Only stop at the end (or at a clean, documented resume point if context runs out).
