# Production hardening — progress log

Branch: `hari/prod-hardening`. Items in the priority order given. Each entry records
what changed, how it was tested, and what a human still has to supply.

---

## Tier 1 recon (before any code)

Audited items 1–6 against the repo first, so nothing already built got rebuilt:

| Item | Found |
|---|---|
| 1. HTTPS/TLS | **Missing.** No Caddy/TLS artifacts. `docker-compose.prod.yml` had *no public entrypoint at all* — `web` is `expose`-only and there was no frontend service, so nothing was reachable. |
| 2. Secrets | Largely done: `.env` gitignored, `${VAR:?}` fail-closed in prod compose, `.env.example` is a complete commented reference. |
| 3. SMTP | Already env-driven (`EMAIL_BACKEND` etc., `base.py:363`) with a console default for dev. Needs verification, not building. |
| 4. Headers + limits | Prod sets HSTS, secure cookies, `X_FRAME_OPTIONS=DENY`, nosniff, CSRF trusted origins. Throttles: `TenantThrottle` + `UserThrottle` + anon. **One real gap found — see item 1.** |
| 5. Backups | **Missing.** No backup script anywhere. |
| 6. Health/monitoring | `/healthz` + `/readyz` exist; Sentry wired via `init_sentry` and a `SENTRY_DSN` env. Needs verification + docs. |

---

## Item 1 — HTTPS/TLS behind Caddy ✅ done

**Changed**
- `Caddyfile` (new) — public TLS edge. Site address and ACME contact come from
  `{$DOMAIN}` / `{$ACME_EMAIL}`; no hostname is committed. Routes Django-owned paths
  (`/api/*`, `/accounts/*`, `/static/*`, `/healthz`, `/readyz`) to `web:8000` and
  everything else to `frontend:80`. Security headers are set on the SPA branch only,
  so Django-served responses are not double-stamped.
- `docker-compose.prod.yml` — added the `caddy` service (the only one publishing
  `80`/`443`) and a `frontend` service built from `frontend/Dockerfile` at repo-root
  context, `expose`d not published. Added `caddy_data` / `caddy_config` volumes, and
  pinned `DJANGO_SECURE_SSL_REDIRECT=true` + `DJANGO_HSTS_SECONDS` in the app env so
  the posture is visible in the deployment file, not only in code.
- `config/settings/prod.py` — set `REST_FRAMEWORK["NUM_PROXIES"]` (env
  `DJANGO_NUM_PROXIES`, default 1). **This is a security fix, not plumbing** — see below.
- `apps/core/tests/test_prod_settings.py` — four tests.

**The security bug putting a proxy in front would have introduced.** Behind Caddy every
request reaches Django with `REMOTE_ADDR` set to Caddy, so DRF identifies anonymous
clients from `X-Forwarded-For` — and a proxy *appends* to that header rather than
replacing it. With `NUM_PROXIES` unset DRF keys on the whole chain, so a client sending
its own `X-Forwarded-For` gets a different bucket every request. Demonstrated against
DRF's own resolver:

```
NUM_PROXIES = None (before)      NUM_PROXIES = 1 (after)
  XFF '1.1.1.1' -> '1.1.1.1,203.0.113.9'    -> '203.0.113.9'
  XFF '2.2.2.2' -> '2.2.2.2,203.0.113.9'    -> '203.0.113.9'
  XFF '3.3.3.3' -> '3.3.3.3,203.0.113.9'    -> '203.0.113.9'
```

Three requests, three buckets — the per-IP limit protecting the login surface stops
existing the moment TLS is terminated upstream. The per-(tenant,email) lockout
(`LOGIN_LOCKOUT_ATTEMPTS`) is unaffected, so this was defence-in-depth rather than the
only control, but it is exactly the control that makes password spraying expensive.

**Tested**
- `caddy validate` against the real Caddyfile: **Valid configuration**, and it reports
  `enabling automatic HTTP->HTTPS redirects`.
- `docker compose -f docker-compose.prod.yml config` renders cleanly; asserted that
  **`caddy` is the only service publishing a host port**.
- 8/8 in `apps/core/tests/test_prod_settings.py`, including a negative control:
  removing the `NUM_PROXIES` line fails `test_prod_declares_how_many_proxies_front_it`.

**A human must**
- Point `DOMAIN` at the server (an A/AAAA record that already resolves) and open **:80
  and :443**. Port 80 is not optional — the HTTP-01 challenge is answered there, so
  closing it breaks *renewal* ~60 days later, not the first issue.
- Set `ACME_EMAIL` to a real address (Let's Encrypt expiry warnings go there).
- Set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` to the domain.
- Raise `DJANGO_NUM_PROXIES` to 2 if a CDN (Cloudflare, CloudFront) is put in front of
  Caddy. Too low throttles every user as one; too high trusts a forged hop.
- **Back up the `caddy_data` volume.** It holds the issued certificate and the ACME
  account key; Let's Encrypt allows 5 duplicate certs per week, so losing it twice in a
  week leaves the site HTTP-only until the window rolls.

---

## Item 2 — Secrets ✅ done (was already sound; now proven and documented)

**Audited, not assumed.** Scanned **all 444 commits** in the repo's history — every
diff, not just the working tree — for credential-shaped strings (Google `AIza…`/`AQ.…`,
OpenAI `sk-…`, Stripe `sk_live_`/`whsec_`, Razorpay `rzp_live_`, GitHub `ghp_`, AWS
`AKIA…`, PEM private keys).

| Check | Result |
|---|---|
| Credential-shaped strings in any committed diff | **NONE** |
| `.env` ever committed | **never** |
| `.env` / `env-for-testing.txt` gitignored | ✅ both |
| Tracked env files | only `.env.example`, `frontend/.env.example` — placeholders (`CHANGE-ME`) |
| `apps/integrations/secrets.py` (flagged by name) | legitimate: resolves tokens from the env by name, no literals, already documents the KMS/Vault swap |

**Changed**
- `docs/PROD/ENVIRONMENT.md` (new) — the single "what must I set" reference, split into
  fail-closed (won't boot without), required-to-actually-work (boots and silently
  degrades — the more dangerous class), and deployment-shape. Marks every secret, and
  derives the fail-closed list from the code rather than by hand.
- Two guards in `apps/core/tests/test_prod_settings.py`: a credential-pattern scan over
  the tree, and a `.gitignore` coverage check.

**A note on those guards.** Both first shelled out to `git` — and the runtime image has
no git binary, so both errored. Making them `skip` would have been worse than useless:
they'd skip in the only place they ever run. They now walk the filesystem and parse
`.gitignore` directly, so they actually execute (10/10 pass, no skips).

**Secret-store recommendation** (in `ENVIRONMENT.md`): a `.env` file is fine locally but
is the weakest link in production — plaintext on the host, survives into backups and
images, no rotation or audit trail. Preferred order: the platform's own secret store
(injected as env vars, so **no code change** — everything already reads the environment)
→ a managed manager (AWS/GCP Secret Manager, Vault) fetched at boot via an IAM role →
and only then a `chmod 600` file on an encrypted volume. `apps/integrations/secrets.py`
is the single function to repoint for per-tenant integration tokens.

**A human must**
- Decide the secret store and move `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `GEMINI_API_KEY`,
  `EMAIL_HOST_PASSWORD` and `METRICS_TOKEN` into it before real customer data lands.
- **Rotate the Gemini key that is currently in the local `.env`** — it is not committed,
  but it has been pasted into terminals and is known-invalid anyway (see the API-key
  check in the previous session).
