# DEPLOYMENT_HANDOVER — for the deployment team

Refreshed for the PROD_A–E production pass. Grounded in `docker-compose.prod.yml`,
`config/settings/prod.py`, and the code. See `PRODUCTION_REQUIREMENTS.md` for the
full infra assessment and `docs/PHASE2/DEPLOYMENT_HANDOVER.md` for the prior detail.

## Required services (all in `docker-compose.prod.yml`)
- **migrate** (one-shot): `python manage.py deploy_migrate` — advisory-locked; the
  ONLY place migrations run. Run it each deploy before web/workers.
- **web**: `gunicorn config.wsgi:application -c gunicorn.conf.py` (WSGI, not uvicorn).
- **celery-worker**: `celery -A config worker` — the AI jobs run here (off the web
  thread). **Provision autoscaling + a separate AI queue for scale** (PROD_D report).
- **celery-beat**: scheduled tasks.
- **redis-broker**: `--maxmemory-policy noeviction` (queued AI jobs must not drop).
- **redis-cache**: separate instance, `allkeys-lru` (app cache + sessions).
- **mysql 8**: replace the compose MySQL with **managed MySQL** (backups + tested
  restore); optional read replica is config-only (`DB_REPLICA_*`).
- **frontend**: nginx serving the built SPA + proxying `/api,/accounts,/static,…`.
- **TLS-terminating LB / ingress** in front of web (prod forces `SECURE_SSL_REDIRECT`
  + expects `X-Forwarded-Proto=https`).

## Build + startup
1. Build the baked image (prod compose, no source mount, `config.settings.prod`).
2. Inject secrets via the host/platform secret store as **env** (never commit `.env`):
   `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
   `DB_*`, `REDIS_*`, `CELERY_*`, `METRICS_TOKEN`, and the new PROD_A–D vars below.
3. Run the one-shot `migrate` job, then start web + workers + beat.
4. Seed only if this is a fresh demo/pilot (`seed_demo_rich`); NOT for real tenants.

## New env for this pass (placeholders in `.env.example`)
- **Branding**: `APP_NAME` (backend email name; SPA name is `src/brand.tsx`).
- **Onboarding**: `SIGNUP_DEFAULT_SEATS`.
- **Google SSO**: `GOOGLE_OAUTH_CLIENT_ID/SECRET` (backend) + build
  `VITE_GOOGLE_SSO_ENABLED=true` (frontend) to show the button.
- **Payments (test → live)**: `PAYMENTS_ENABLED`, `STRIPE_SECRET_KEY`,
  `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `RAZORPAY_KEY_ID`,
  `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
- **AI**: `LLM_READ_TIMEOUT` (60), size `LLM_MAX_CALLS` for prod (default 500 is dev).
- **Email/SMTP**: `EMAIL_BACKEND=…smtp.EmailBackend` + `EMAIL_HOST/PORT/USER/PASSWORD/TLS`
  + `DEFAULT_FROM_EMAIL` + `PUBLIC_APP_URL` (signup/invite/reset emails need this).
- **Media**: `MEDIA_ROOT` on a mounted volume (avatar/logo uploads); object storage
  is the documented upgrade.

## Health / monitoring
- `/healthz`, `/readyz` (DB primary + replica + cache + sessions + broker + migrations),
  token-gated Prometheus `/metrics` (`METRICS_TOKEN`). Wire Sentry (`SENTRY_DSN`).
- Provision a Prometheus/Grafana scrape + alerts (biggest ops gap; see
  `docs/OBSERVABILITY.md`).

## Go-live steps for the staged items
1. **Payments**: set TEST keys → `PAYMENTS_ENABLED=true` → verify with test cards +
   the provider webhook/CLI (`docs/PHASE2/PAYMENTS_VERIFIED.md` §go-live) → wire the
   `create_checkout` SDK call → register the LIVE webhook URLs
   (`/api/billing/webhooks/{stripe,razorpay}`) → swap LIVE keys, supervised.
2. **Google OAuth**: create the Google Cloud OAuth client, set creds + the redirect
   URI, set `VITE_GOOGLE_SSO_ENABLED=true` (`docs/CUSTOMER_ONBOARDING.md` §3).
3. **AI scale**: provision managed Redis + worker autoscaling + the right LLM tier +
   a provider dollar-cap (`docs/AI_ROBUSTNESS.md` §7).
4. **Email**: provision SMTP (SES/SendGrid/Postmark) and set `EMAIL_*`.

Placeholders only — no secrets in the repo.
