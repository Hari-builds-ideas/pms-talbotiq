# Environment variables — the one place to look

`.env.example` is the full, commented catalogue of every variable the app reads,
verified against `config/settings/base.py` + `prod.py`. **This file is the shorter
question: what must I set for a real deployment, and which of those are secrets?**

Nothing here belongs in git. `.env` and `env-for-testing.txt` are gitignored; only the
`.env.example` placeholder templates are tracked.

---

## 1. Fail-closed — the stack will not start without these

Two independent guards enforce this, so a misconfigured deploy stops rather than
quietly running insecurely:

- `config/settings/prod.py` calls `env("DJANGO_SECRET_KEY")` and
  `env.list("DJANGO_ALLOWED_HOSTS")` **with no default** — Django raises at import.
- `docker-compose.prod.yml` uses `${VAR:?message}` — compose refuses to start.

| Variable | Secret? | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | 🔴 **secret** | `python -c "import secrets;print(secrets.token_urlsafe(64))"`. Rotating it invalidates every JWT and session — expect a forced re-login. |
| `DJANGO_ALLOWED_HOSTS` | no | The real domain(s), comma-separated. **Never `*`.** |
| `DOMAIN` | no | Hostname for the TLS certificate; must already resolve to this server. |
| `ACME_EMAIL` | no | Let's Encrypt expiry warnings. Use a monitored address. |
| `DB_PASSWORD` | 🔴 **secret** | |
| `DB_ROOT_PASSWORD` | 🔴 **secret** | Only needed by the bundled reference MySQL; a managed DB doesn't use it. |

## 2. Required for the product to actually work

Not fail-closed — the app boots without them and degrades. That is worse than crashing
if you don't know, so they are listed here.

| Variable | Secret? | Without it |
|---|---|---|
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | 🔴 password | Password reset, email verification and invitations **silently go to the console**. Nobody can join or recover an account. See item 3. |
| `EMAIL_BACKEND` | no | Must be `django.core.mail.backends.smtp.EmailBackend` in prod; the default is the dev console backend. |
| `DEFAULT_FROM_EMAIL` | no | Mail comes from `no-reply@localhost` and is spam-filed. |
| `PUBLIC_APP_URL` | no | Password-reset links point at the wrong host. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | no | The SSO/session flows reject the SPA's origin. |
| `GEMINI_API_KEY` | 🔴 **secret** | AI features return a clean 503; the rest of the app is unaffected. |
| `METRICS_TOKEN` | 🔴 **secret** | `/metrics` is disabled (fine if you don't scrape it). |

## 3. Deployment-shape variables

| Variable | Default | Set it when |
|---|---|---|
| `DJANGO_NUM_PROXIES` | `1` | A CDN sits in front of Caddy → `2`. Too low throttles every user as one; too high trusts a hop a client can forge. See PROGRESS item 1. |
| `DJANGO_SECURE_SSL_REDIRECT` | `true` | Only set `false` if something upstream already redirects. |
| `LLM_MAX_CALLS` | `2000` | A deployment-wide 24h ceiling. The dev value is 60 — do not ship that. |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | `true` only for a demo with no worker (AI runs inline in the request). |
| `SENTRY_DSN` | empty | Error monitoring; blank disables cleanly. |
| `DB_SSL_CA` | empty | Managed MySQL requiring TLS. |

---

## 4. Do not ship `.env` to production

A `.env` file is fine for local development and is what the compose files read. For a
real deployment it is the weakest link: it sits in plaintext on the host, survives in
backups and images, and has no rotation story or audit trail.

**Recommended, in order:**

1. **Your platform's secret store** — Railway/Render variables, ECS Secrets Manager
   integration, Kubernetes Secrets backed by an external store. Secrets are injected as
   environment variables at start, so **no application change is needed**: everything
   already reads from the environment.
2. **A managed secrets manager** — AWS Secrets Manager, GCP Secret Manager, or
   HashiCorp Vault, with the container fetching at boot via an IAM role rather than a
   long-lived key. This buys rotation, versioning and an access audit trail.
3. **If you must use a file**: `chmod 600`, owned by the service user, mounted
   read-only, on an encrypted volume, and never inside the image build context.

**The integration seam already exists.** `apps/integrations/secrets.py` resolves
per-tenant integration tokens from the environment by name and documents itself as the
single function to swap for KMS/Vault. Point that one function at your secrets manager
and every integration follows.

**Rotation.** Every secret above can be rotated by changing the value and restarting —
except `DJANGO_SECRET_KEY`, which invalidates sessions and JWTs, so plan it as a
user-visible event.
