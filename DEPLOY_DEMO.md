# DEPLOY_DEMO.md — free, shareable demo (Vercel + Render + Gemini)

A live demo URL a CEO can open, **entirely on free tiers**. NOT production (see
`PRODUCTION_REQUIREMENTS.md` for that). Shape: **React SPA → Vercel (free)**, **Django + Celery +
Redis + MySQL → Render (free)**, **AI → Google Gemini (free tier)**. Scaffolding is committed
(`render.yaml`, `vercel.json`); the account connect + first deploy need your login — this is the
click-through. **No secret is committed — you paste the Gemini key in the Render dashboard.**

## Before you start
- Push this branch to GitHub (Render + Vercel deploy from the repo).
- Get a **free Gemini API key** from Google AI Studio (aistudio.google.com → "Get API key"). Free.
- (Nothing to install locally.)

## Step 1 — Backend on Render (reads `render.yaml`)
1. Render dashboard → **New → Blueprint** → connect this GitHub repo → Render reads `render.yaml`
   and shows 3 services: `talbotiq-pms-api` (web), `talbotiq-redis` (Key-Value), `talbotiq-mysql`
   (private MySQL). All on **free**.
2. **Paste the one secret:** on the `talbotiq-pms-api` service → Environment → set **`GEMINI_API_KEY`**
   to your Gemini key. (Every other env is auto-generated or wired by the blueprint.)
3. Click **Apply / Create** — Render builds the Docker image, runs `deploy_migrate` (pre-deploy), and
   starts gunicorn. `DJANGO_SECRET_KEY` is auto-generated; MySQL user/passwords are auto-generated.
4. When the web service is live, copy its URL (e.g. `https://talbotiq-pms-api.onrender.com`) and set:
   - **`DJANGO_ALLOWED_HOSTS`** = `talbotiq-pms-api.onrender.com`
   - **`DJANGO_CSRF_TRUSTED_ORIGINS`** = your Vercel URL (from Step 2), e.g. `https://talbotiq-pms.vercel.app`
   (Save → it redeploys.)
5. **Seed the demo data:** the DB is empty on first boot. Open the web service → **Shell** → run:
   ```
   python manage.py seed_demo_rich
   ```
   (Idempotent. The demo now has ACME with ~200 people.) See the DB caveat below — you may need to
   re-run this if the free DB resets.

## Step 2 — Frontend on Vercel (reads `vercel.json`)
1. Vercel → **Add New → Project** → import this repo. `vercel.json` builds the SPA from the repo root
   (`cd frontend && npm run build` → `frontend/dist`) — leave the framework preset as detected; don't
   set a `frontend/` root directory (the build needs the sibling `../shared`).
2. **Point the SPA at the backend (no CORS needed):** edit `vercel.json`'s `/api` rewrite `destination`
   host to your Render URL (the one line marked `REPLACE-WITH-YOUR-RENDER-HOST`), commit, redeploy.
   Vercel then proxies `/api/*` to Render **same-origin**, so the browser needs no CORS and the backend
   needs no change. (Leave `VITE_API_BASE_URL` unset — the SPA defaults to `/api`.)
3. Deploy. The demo is live at your Vercel URL.

## Step 3 — Log in
Open the Vercel URL. Demo accounts (tenant `acme`, password **`Passw0rd!demo`**):

| Role | Email |
|---|---|
| Admin | `admin@acme.test` |
| HRBP | `priya@acme.test` |
| Manager | `ada@acme.test` |
| Employee | `akhil@acme.test` |

The AI (Ask-AI plan flow, review drafts, JD generation) runs on your Gemini key. Models default to
Gemini's **best/fast split** — `gemini-pro-latest` for the human-read agents (review / JD / feedback /
succession / career) and `gemini-2.5-flash` for chat. (`gemini-2.5-pro` is blocked for new API projects,
so the default is the stable `-latest` alias; the pro models "think", so `LLM_MAX_TOKENS` defaults to
4096.) Override with `GEMINI_MODEL_BEST`/`GEMINI_MODEL_FAST`, or force the fast model everywhere with
`GEMINI_MODEL=gemini-2.5-flash` if a free tier limits Pro. **Verified live on this stack:** the agent
plan→approve flow (fast model) and a review draft (best model, `gemini-3.1-pro-preview`) both produced
real, grounded output; injection requests planned only registered actions and executed nothing.

**Verify the AI end-to-end (one command, after the key is pasted):**
```bash
# on the Render web service shell (or locally with GEMINI_API_KEY set):
docker compose run --rm web python manage.py shell -c "from apps.ai.providers import get_llm_provider; p=get_llm_provider(); print(type(p).__name__, 'configured=', p.configured)"
# → GeminiProvider configured= True
```
Then in the app: open **Ask AI → "draft a review for <report>"** → a plan appears → approve a step → the
draft returns (lands PENDING for human review). If the key is missing you get a clean 503, never a fake.

## Every env var (backend / Render)
| Var | Set by | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | blueprint (`config.settings.prod`) | — |
| `DJANGO_SECRET_KEY` | Render auto-generate | — |
| `DJANGO_ALLOWED_HOSTS` | **you** (Step 1.4) | the Render host |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | **you** (Step 1.4) | the Vercel URL |
| **`GEMINI_API_KEY`** | **you — hand-paste** ⚠ | the only real secret; never committed |
| `LLM_PROVIDER` | blueprint | `apps.ai.gemini_provider.GeminiProvider` |
| `GEMINI_MODEL_BEST` / `_FAST` | defaults in settings | `gemini-2.5-pro` / `gemini-2.5-flash`; override to change ids |
| `GEMINI_MODEL` | *(optional)* | set to force ONE model for all agents (e.g. `gemini-2.5-flash` on a tight free tier) |
| `LLM_MAX_CALLS` | blueprint | `200` — demo-wide 24h cost cap |
| `CELERY_TASK_ALWAYS_EAGER` | blueprint (`true`) | AI runs inline (no free worker) |
| `DB_*` / `REDIS_*` / `CELERY_*` | blueprint (wired) | from the redis + mysql services |

Frontend (Vercel): none required (the `/api` proxy handles it). Optional `VITE_API_BASE_URL` only if
you skip the proxy and call Render cross-origin (then you'd also need to add CORS — the proxy avoids it).

## Free-tier honesty (do not paper over — mitigations included)
- **Web sleeps after ~15 min idle → ~30–60s cold start.** Mitigation: hit the URL a minute before you
  present so it's warm.
- **DB persistence:** Render's free managed DB is Postgres, but this app's stack is **locked to MySQL 8**,
  so MySQL runs as a private service **without a persistent disk** (a disk is a paid add-on). So the demo
  DB is **ephemeral — it resets when the service restarts.** Re-run `seed_demo_rich` (Step 1.5) after a
  reset. For a durable demo later, add a paid disk (see the commented `disk:` block in `render.yaml`) or
  a small managed MySQL. **This is a flagged decision — see PROGRESS_V1 QUESTIONS.**
- **No free background worker → Celery runs EAGER** (AI jobs inline in the web request). Fine for a demo
  with the small `LLM_MAX_CALLS` cap; production runs a real worker.
- **One Redis instance** for broker + cache + sessions (production splits broker/cache — see
  `docker-compose.prod.yml`).
- **Gemini free tier** has request-rate limits; the `LLM_MAX_CALLS=200/24h` cap keeps cost/quota bounded.

## Never
- Don't commit the Gemini key (it's dashboard-only, `sync: false` in `render.yaml`).
- Don't switch to a paid DB/worker for the demo — the free path above is complete.
