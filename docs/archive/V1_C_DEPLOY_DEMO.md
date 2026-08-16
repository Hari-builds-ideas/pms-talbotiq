# V1_C_DEPLOY_DEMO.md — free demo deployment (Vercel + Render)

**Goal:** a live, shareable demo URL — free tier only — that a CEO can open and show customers. NOT a
production deployment; no managed scaling infra. Just clean, working, and free.

**Shape:** frontend (React SPA) on **Vercel** (free). Backend + MySQL + Redis + Celery on **Render**
(free tier) via a Render Blueprint. Both free.

> IMPORTANT: Do the config/scaffolding autonomously and commit it, but the actual account
> connect / first deploy needs Hari's login. So: PREPARE everything so deploy is one click for Hari,
> and write exact step-by-step instructions. Do NOT attempt to log into Hari's Vercel/Render accounts or
> enter any credentials — prepare the files and document the clicks.

## 1. Backend on Render (free)
- Add a `render.yaml` Blueprint at repo root defining the services on the FREE plan:
  - a web service (Django/gunicorn) built from the existing Dockerfile,
  - a Celery worker,
  - a Celery beat (if free tier allows a third; if not, fold beat into worker for the demo and note it),
  - a **free Render PostgreSQL** OR keep MySQL — CHECK: Render's free managed DB is PostgreSQL. The app
    uses MySQL. For a FREE demo, the cleanest options, in order of preference:
    (a) run MySQL as a private Render service from the mysql:8 image with a small persistent disk, OR
    (b) if a persistent disk isn't free, document that the demo DB resets on restart (acceptable for a
        demo — reseed on boot).
    Pick the free path; document the tradeoff clearly. Do NOT introduce a paid DB.
  - a **free Render Redis** (Render offers a free Redis) for broker + cache (single instance is fine for
    a demo — note it's not the prod split).
- Environment: set `config.settings.prod`, generate a `DJANGO_SECRET_KEY`, set `ALLOWED_HOSTS` /
  `CSRF_TRUSTED_ORIGINS` to the Render + Vercel domains, `LLM_PROVIDER` = the Gemini provider,
  `GEMINI/LLM_API_KEY` from Render's secret env (Hari pastes the key in the dashboard — never commit it),
  a small `LLM_MAX_CALLS` demo cap.
- Run `deploy_migrate` once on deploy, then seed demo data on first boot (a one-off release command or a
  documented manual step). The demo must come up populated.
- Confirm the Gemini provider actually works end to end; if the Gemini provider class isn't wired, wire
  it (mirror the OpenAI provider) so the AI runs on the provided Gemini key. This is the one likely code
  gap — handle it.

## 2. Frontend on Vercel (free)
- Add a `vercel.json` (build the SPA, SPA rewrite to index.html) so it deploys clean.
- Point the frontend's API base URL at the Render backend URL via a Vercel env var
  (`VITE_API_BASE_URL` or the existing config key) — documented, not hardcoded.
- Ensure CORS/CSRF on the backend allows the Vercel domain.

## 3. Make deploy one-click for Hari
- Write `DEPLOY_DEMO.md`: exact steps — "connect this repo to Render, it reads render.yaml, paste the
  Gemini key in the dashboard, deploy; connect to Vercel, set VITE_API_BASE_URL to the Render URL,
  deploy; the demo is live at <vercel-url>." Include how to reseed and the demo login accounts.
- List every env var Hari must set, and clearly which one secret (the Gemini key) he pastes by hand.

## 4. Free-tier honesty
- Render free web services sleep after inactivity and cold-start (~30–60s first hit). Document this and
  the mitigation for the demo: hit the URL a minute before presenting to warm it. Do NOT paper over it.
- Note any free-tier limit that matters for the demo (DB persistence, sleep) plainly in DEPLOY_DEMO.md.

## Rules
- Everything free. If a step needs money, stop, use the free alternative, and note it.
- Never commit secrets. The Gemini key is pasted in the Render dashboard by Hari.
- Do not attempt to authenticate as Hari or deploy on his behalf — prepare + document so it's one click.

## Done when
- `render.yaml`, `vercel.json`, and `DEPLOY_DEMO.md` exist and are correct; the Gemini provider is wired;
  the deploy is one documented click-through for Hari; free-tier caveats are written plainly. Logged in
  PROGRESS_V1.md.
