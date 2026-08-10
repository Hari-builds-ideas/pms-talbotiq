# Deploying TalbotIQ PMS to Railway

Click-by-click for a **multi-service** deploy: Django web (gunicorn) + Celery worker +
Celery beat, against Railway's managed **MySQL** and **Redis**.

Everything below was checked against this repo — the Dockerfile was built as Railway will
build it, and the start commands were run inside that image. Where a claim depends on
Railway's own UI (variable names, menu labels) it is marked **verify in the UI**, because
that cannot be checked from here.

> **Source of truth for env vars:** there is no `DEVELOPER_ENV_GUIDE.md` in this repo. The
> canonical, commented list of every variable the app reads is **`.env.example`**, verified
> against `config/settings/base.py` + `prod.py`. This document's checklist is derived from it.

---

## 0. What was changed to make Railway work

Three small commits' worth of change, all verified:

| File | Change | Why |
|---|---|---|
| `gunicorn.conf.py` | `bind` now honours `PORT` | Railway injects `PORT` and routes only to it. Bound to a fixed `8000`, the service is never reached and fails its health check. `GUNICORN_BIND` still wins, so docker-compose is unchanged. |
| `Dockerfile` | added `RUN python manage.py collectstatic --noinput` | See below — this was a real, latent 500. |
| `.gitignore` | ignore `staticfiles/*` (keep `.gitkeep`), ignore `env-for-testing.txt` | collectstatic output is a build artifact; the stray env file was untracked but *not* ignored. |
| `railway.json`, `railway.worker.json`, `railway.beat.json` | new | Build + start command per service. |

**The static files bug (worth understanding).** `STORAGES` uses whitenoise's
`CompressedManifestStaticFilesStorage` (`config/settings/base.py:637`), which resolves every
`{% static %}` through `staticfiles/staticfiles.json`. That file was never generated —
`collectstatic` appeared nowhere in the repo. Verified under prod settings:

```
static('…') -> ValueError: Missing staticfiles manifest entry
```

The JSON API never renders a template, which is why all 131 handover checks pass regardless.
But the **DRF browsable API** and the **allauth SSO pages at `/accounts/`** do render
templates, and would have 500'd on Railway. After the fix, in the built production image:

```
DRF browsable API    status=401  renders HTML     ← resolves, no exception
manifest entries: 36 (rest_framework/*)
```

It goes in the **image**, not a release command, because a Railway pre-deploy command runs in
its own throwaway container — files written there never reach the web process. Baking it in
also gives worker and beat an identical filesystem.

---

## 1. Does the Dockerfile work on Railway? Yes — verified

Built exactly as Railway builds it:

```
docker build --build-arg INSTALL_DEV=false -t pms-railway-check .
→ 36 static files copied to '/app/staticfiles', 88 post-processed.
→ build succeeded
```

And inside that image:

| Check | Result |
|---|---|
| `PORT=7777` → gunicorn bind | `0.0.0.0:7777` ✅ |
| no `PORT` (compose) → bind | `0.0.0.0:8000` ✅ unchanged |
| celery app loads | `celery app loaded: pms` ✅ |
| `celery beat --schedule` | valid flag ✅ |
| `celery worker --concurrency` | valid flag ✅ |
| static manifest under prod settings | resolves ✅ |

**One optional tweak.** The Dockerfile defaults to `INSTALL_DEV=true`, so Railway will build
with the test toolchain (pytest, factory_boy) unless you pass a build arg. It works fine —
just a fatter image. Both compose files set the arg explicitly, so if you want the lean
image you can safely flip the default in `Dockerfile`:

```dockerfile
ARG INSTALL_DEV=false
```

I left it alone rather than change behaviour you didn't ask about.

---

## 2. The three start commands

| Service | Start command |
|---|---|
| **web** | `gunicorn config.wsgi:application -c gunicorn.conf.py` |
| **worker** | `celery -A config worker -l info --concurrency=2` |
| **beat** | `celery -A config beat -l info --schedule=/tmp/celerybeat-schedule` |

Notes:
- **web** needs no `--bind`: `gunicorn.conf.py` reads `PORT` itself.
- **worker** `--concurrency=2` is deliberate. Each worker slot opens a MySQL connection;
  keep `web_replicas × gunicorn_workers × threads + concurrency` under the DB's
  `max_connections` (the sizing note lives in `config/settings/base.py:149`).
- **beat** writes its schedule DB to `/tmp` because the container filesystem is ephemeral and
  the default location is the read-mostly `/app`. Beat state resetting on redeploy is
  harmless here — the only periodic job is the approvals-escalation sweep.

---

## 3. Environment variable checklist

Legend: **[R]** = comes from a Railway plugin via a reference variable · **[YOU]** = you must
provide it · **[OPT]** = safe to skip for a demo.

### 3a. Required on ALL THREE services

Every row here must exist on web **and** worker **and** beat. The workers load the same
Django settings, so a missing `DJANGO_SECRET_KEY` fails them exactly as it fails web.

| Variable | Value | |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | **[YOU]** |
| `DJANGO_SECRET_KEY` | `python -c "import secrets;print(secrets.token_urlsafe(64))"` | **[YOU]** |
| `DJANGO_ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app` | **[YOU]** |
| `DB_HOST` | `${{MySQL.MYSQLHOST}}` | **[R]** |
| `DB_PORT` | `${{MySQL.MYSQLPORT}}` | **[R]** |
| `DB_NAME` | `${{MySQL.MYSQLDATABASE}}` | **[R]** |
| `DB_USER` | `${{MySQL.MYSQLUSER}}` | **[R]** |
| `DB_PASSWORD` | `${{MySQL.MYSQLPASSWORD}}` | **[R]** |
| `CELERY_BROKER_URL` | `redis://default:${{Redis.REDISPASSWORD}}@${{Redis.REDISHOST}}:${{Redis.REDISPORT}}/0` | **[R]** |
| `CELERY_RESULT_BACKEND` | same as broker (`/0`) | **[R]** |
| `REDIS_CACHE_URL` | `redis://default:${{Redis.REDISPASSWORD}}@${{Redis.REDISHOST}}:${{Redis.REDISPORT}}/1` | **[R]** |
| `REDIS_SESSION_URL` | `redis://default:${{Redis.REDISPASSWORD}}@${{Redis.REDISHOST}}:${{Redis.REDISPORT}}/2` | **[R]** |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | **[YOU]** |

> **Verify in the UI.** Railway's MySQL/Redis plugins expose their credentials under the
> plugin service's **Variables** tab. The names above (`MYSQLHOST`, `REDISPASSWORD`, …) are
> Railway's usual convention, but **open the plugin's Variables tab and copy the real names**
> before saving. If Railway offers a private/internal host variant, prefer it — it keeps DB
> traffic off the public network and off your egress bill.
>
> I build the Redis URLs from parts rather than using `REDIS_URL` because this app needs
> **three different logical DBs** (`/0` broker, `/1` cache, `/2` sessions — see
> `base.py:213`), and blindly appending `/1` to a URL that may already carry a path produces a
> broken DSN.

### 3b. Web service only

| Variable | Value | |
|---|---|---|
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<your-vercel-app>.vercel.app` (the SPA origin) | **[YOU]** |
| `PUBLIC_APP_URL` | the SPA base URL — password-reset links point here | **[YOU]** |
| `DJANGO_SECURE_SSL_REDIRECT` | `true` (leave default) | **[OPT]** |

### 3c. AI — needed for the assistant to work at all

| Variable | Value | |
|---|---|---|
| `LLM_PROVIDER` | `apps.ai.gemini_provider.GeminiProvider` | **[YOU]** |
| `GEMINI_API_KEY` | your key — **paste in the Railway UI, never commit** | **[YOU]** |
| `LLM_MAX_CALLS` | `2000` for real use; `200` to cap a demo | **[YOU]** |
| `GEMINI_MODEL` | `gemini-2.5-flash` to force the cheap model everywhere | **[OPT]** |

Unset `GEMINI_API_KEY` → AI endpoints return a clean 503 and the rest of the app works.
The dev default for `LLM_MAX_CALLS` is **60/window**, which is what tripped during testing —
don't ship that number.

### 3d. Everything else

| Variable | Notes | |
|---|---|---|
| `EMAIL_BACKEND` + `EMAIL_HOST/PORT/USER/PASSWORD`, `DEFAULT_FROM_EMAIL` | **Required for real users** — password reset and invites are dead without SMTP. Skippable only for a demo where nobody resets a password. | **[YOU]** |
| `METRICS_TOKEN` | required to enable the token-gated `/metrics`; unset disables it | **[OPT]** |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT` | blank disables cleanly | **[OPT]** |
| `LOG_LEVEL` | `INFO` | **[OPT]** |
| `DB_SSL_CA` | only if you point at a managed MySQL requiring TLS with a CA bundle | **[OPT]** |
| `DB_REPLICA_*` | leave unset — reads fall back to the primary | **[OPT]** |
| `PAYMENTS_ENABLED` | keep `false` | **[OPT]** |
| `FLOWER_BASIC_AUTH` | only if you deploy Flower (not covered here) | **[OPT]** |
| `MEDIA_ROOT` | ⚠️ see the ephemeral-storage warning in §7 | **[OPT]** |

---

## 4. Click-by-click

### Step 1 — Create the project and the databases
1. Railway → **New Project** → **Deploy from GitHub repo** → pick `PMS-Bucket3`, branch **`main`**.
2. Railway detects the `Dockerfile` and starts a build. Let it finish or cancel — it has no
   variables yet and will crash-loop; that is expected.
3. In the project canvas: **+ New** → **Database** → **Add MySQL**.
4. **+ New** → **Database** → **Add Redis**.

### Step 2 — Configure the **web** service
1. Click the service built from your repo → **Settings** → rename to `web`.
2. **Settings → Config-as-code / Railway Config File** → set to `railway.json` *(verify in the UI —
   the setting exists but its label moves around)*. That supplies the start command, the
   `/healthz` health check and the `deploy_migrate` pre-deploy in one go.
   If you can't find it, set them manually instead:
   - **Custom Start Command:** `gunicorn config.wsgi:application -c gunicorn.conf.py`
   - **Healthcheck Path:** `/healthz`
   - **Pre-Deploy Command:** `python manage.py deploy_migrate`
3. **Variables** tab → add every row from **§3a + §3b + §3c + §3d**.
4. **Settings → Networking → Generate Domain**. Copy it.
5. Confirm `DJANGO_ALLOWED_HOSTS` resolves to that domain (the `${{RAILWAY_PUBLIC_DOMAIN}}`
   reference does this automatically).

### Step 3 — Add the **worker** service
1. **+ New** → **GitHub Repo** → the same repo, same branch. (Same repo, second service — this
   is normal on Railway.)
2. **Settings** → rename to `worker` → **Railway Config File** = `railway.worker.json`,
   or set **Custom Start Command** to `celery -A config worker -l info --concurrency=2`.
3. **Variables** → add **§3a + §3c** (it runs the AI jobs, so it needs the Gemini key).
   It needs **no** domain and **no** health check.

### Step 4 — Add the **beat** service
1. **+ New** → **GitHub Repo** → same repo again.
2. Rename to `beat` → **Railway Config File** = `railway.beat.json`, or **Custom Start
   Command** `celery -A config beat -l info --schedule=/tmp/celerybeat-schedule`.
3. **Variables** → add **§3a**.
4. Keep this at **exactly one replica** — two beats mean every scheduled job fires twice.

### Step 5 — Deploy and verify
1. Deploy `web` first and watch the logs for the pre-deploy:
   `Migrations applied; advisory lock released.`
2. `curl https://<your-domain>/healthz` → `200`.
3. Deploy `worker` and `beat`. Worker logs should show it connecting to Redis and listing
   its registered tasks.

### Step 6 — Seed demo data (optional)
Railway → `web` service → **⋮ → Run a command** *(verify in the UI; the CLI equivalent is
`railway run --service web python manage.py seed_demo_rich`)*:

```
python manage.py seed_demo_rich
```

Then log in with tenant `acme` / `Passw0rd!demo` as `admin@acme.test`.

---

## 5. Migrations — confirmed

`python manage.py deploy_migrate` (`apps/core/management/commands/deploy_migrate.py`) is the
right release command and is already race-safe: it wraps `migrate` in a MySQL **advisory lock**
(`GET_LOCK`), so if several replicas boot at once the first migrates and the rest exit 0 as a
no-op. It is idempotent — re-running applies nothing.

Set it as the **Pre-Deploy Command** on `web` only. Do **not** put it on worker/beat as well:
it's safe (the lock handles it) but it serialises three deploys behind one lock for no reason.

---

## 6. Django settings notes for Railway

| Concern | Status |
|---|---|
| **`PORT`** | **Fixed** in `gunicorn.conf.py`. Railway injects `PORT`; nothing else to do. |
| **`ALLOWED_HOSTS`** | `prod.py:17` is fail-closed — no wildcard fallback, so the app *will not boot* without it. Use `${{RAILWAY_PUBLIC_DOMAIN}}`. Add `healthcheck.railway.app` or Railway's health check (a different `Host` header) returns 400 `DisallowedHost` and the deploy is marked failed. If you hit that, `.railway.app` as a value is the looser fallback. |
| **Static files** | **Fixed** — collectstatic now runs in the image; whitenoise middleware is already installed (`base.py:121`). |
| **HTTPS redirect** | Fine as-is. `SECURE_PROXY_SSL_HEADER` is already `X-Forwarded-Proto` (`prod.py:21`), which Railway sets. If you ever see a redirect loop, set `DJANGO_SECURE_SSL_REDIRECT=false` and let the edge handle it. |
| **`DEBUG`** | Hard-coded `False` in prod settings. Nothing to set. |

---

## 7. Honest warnings

**Cost.** Five services (web + worker + beat + MySQL + Redis) on a $5 trial credit will not
last long. Fine for a demo tomorrow; add a payment method or the company plan for anything
longer. If you need to trim: set `CELERY_TASK_ALWAYS_EAGER=true` and drop the worker *and*
beat services — AI jobs then run inline in the web request. Slower, noticeably, but it is the
same shim `render.yaml` already uses, and it removes two services.

**Redis eviction policy.** `.env.example` is explicit that the broker needs
`maxmemory-policy noeviction` (a dropped key is a lost job) while the cache wants
`allkeys-lru`, and that **one instance cannot satisfy both**. This guide puts all three on one
Railway Redis because that is what a demo justifies. For production, add a second Redis and
split broker (`/0`) from cache/sessions (`/1`,`/2`).

**Uploaded media is ephemeral.** `MEDIA_ROOT=/app/media` is container-local, and Railway
containers are replaced on every deploy — avatars and tenant logos uploaded through the app
will vanish. Attach a Railway **Volume** mounted at `/app/media` on the web service, or move to
object storage (the documented upgrade path). Not a blocker for a demo; a data-loss bug if
anyone treats it as real.

**Frontend.** This deploys the **API only**. The React SPA deploys separately (Vercel,
`vercel.json`). After the API is live, point the SPA's API base URL at the Railway domain and
set `DJANGO_CSRF_TRUSTED_ORIGINS` + `PUBLIC_APP_URL` to the SPA origin.

**No secrets in git.** Every secret above goes in Railway's **Variables** UI. `.env` is
gitignored (`.gitignore:16`); only `.env.example` placeholders are committed. Nothing in this
change adds a secret to the repo.
