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

---

## Item 3 — Real email/SMTP ✅ done (code was ready; the failure mode was not guarded)

**Already correct.** All four mail paths — password reset (`identity/views.py:269`),
welcome (`signup_views.py:96`), invitation (`invite_views.py:82`) and email-change
verification (`profile_views.py:256`) — go through `send_mail`, are fully env-driven,
and keep the console backend as the dev default. `fail_silently` is never passed
anywhere, so a real SMTP failure raises rather than vanishing; the reset path
deliberately catches and logs it so a mail outage cannot 500 or leak whether an
account exists.

**Proven, not assumed.** Stood up a real SMTP server on a socket, pointed Django's
**actual** `smtp.EmailBackend` at it via the same env vars a deployment sets, and sent
through the product's own code path:

```
send_mail returned: 1
messages received over SMTP: 1
RESULT: SMTP PATH WORKS
```

**The gap that was real.** Nothing stopped a deployment shipping with the console
backend, and that failure is silent in the worst way: every request returns 200, the
reset link is written to a container log, and *no one can join the product or recover
an account*. Same for `PUBLIC_APP_URL` left at localhost — the mail is delivered,
opened, and useless, and the failure lands on the recipient where nothing alerts.

**Changed**
- `apps/core/checks.py` (new) — deploy-time checks, registered `deploy=True` so they
  run under `manage.py check --deploy` and never during ordinary tests:
  - `pms.E001` non-delivering `EMAIL_BACKEND` (console/dummy/locmem/filebased)
  - `pms.E002` SMTP selected but `EMAIL_HOST`/`DEFAULT_FROM_EMAIL` unset
  - `pms.E003` `PUBLIC_APP_URL` missing, localhost, or not absolute
  - `pms.W001` `LLM_MAX_CALLS` still at the dev-sized ceiling
- `apps/core/apps.py` — import the module so the checks register.
- `apps/core/tests/test_deploy_checks.py` (new) — 8 tests, each asserting the check
  **fires** on the development default, not merely that it passes when correct.

**Verified end to end.** With the trap config the deploy is blocked:
`SystemCheckError … (pms.E001) … (pms.E003) … (pms.W001)`. With SMTP, a real
`DEFAULT_FROM_EMAIL`, an https `PUBLIC_APP_URL` and a production ceiling, all `pms.*`
issues are silent. 18/18 tests pass.

**A human must**
- Provide SMTP credentials (SES / SendGrid / Mailgun / Postmark) and set
  `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `PUBLIC_APP_URL`.
- Complete the provider's **domain authentication (SPF/DKIM)** — without it this mail
  lands in spam, which looks identical to "the product is broken" to a new customer.
- Run `manage.py check --deploy` as a release gate; it now fails the deploy on the
  above rather than letting it through.

---

## Item 4 — Security headers + rate limiting ✅ done (verified; one real fix in item 1)

**Headers** — all set in `config/settings/prod.py` and asserted by
`test_prod_loads_secure_with_required_env`:

| Control | Setting | Value |
|---|---|---|
| HSTS | `SECURE_HSTS_SECONDS` + subdomains + preload | 1 year |
| Clickjacking | `X_FRAME_OPTIONS` | `DENY` |
| MIME sniffing | `SECURE_CONTENT_TYPE_NOSNIFF` | on |
| Session cookie | `SESSION_COOKIE_SECURE` / `HTTPONLY` / `SAMESITE` | True / True / Lax |
| CSRF cookie | `CSRF_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS` | True, env-driven |
| HTTPS | `SECURE_SSL_REDIRECT` + `SECURE_PROXY_SSL_HEADER` | on, proxy-aware |
| `DEBUG` | hard-coded | `False` |

The SPA is served by nginx, which sets none of these, so the Caddy config adds HSTS,
nosniff, `X-Frame-Options` and a referrer policy on the SPA branch only — Django-served
responses are not double-stamped.

**Rate limiting** — `TenantThrottle` + `UserThrottle` globally (rates resolved per
request from the tenant's entitlement, not from settings), `AnonRateThrottle` on the
login surface (`THROTTLE_ANON`, default 100/min), a dedicated `AIThrottle` attached per
view, and a per-`(tenant, email)` login lockout (`LOGIN_LOCKOUT_ATTEMPTS`, default 8 per
15 min) independent of IP.

**The real finding is recorded under item 1**: terminating TLS upstream silently made
the per-IP limit forgeable, because DRF keys anonymous clients on a header the client
can write to. Fixed with `NUM_PROXIES` and covered by two tests.

**A human must**
- Set `DJANGO_NUM_PROXIES=2` if a CDN is placed in front of Caddy.
- Consider a WAF / edge rate limit for volumetric abuse — these limits are per
  application process and do not protect the network.

---

## Item 5 — Backups + a tested restore ✅ done (was entirely missing)

**Changed**
- `scripts/backup_db.sh` (new) — consistent (`--single-transaction`, InnoDB throughout,
  so no lock-out), complete (`--routines --triggers --events`), replayable
  (`--set-gtid-purged=OFF`, and no `--databases` so it can land in a differently named
  DB), compressed, and **verified**: gzip-tested plus a grep for mysqldump's
  `Dump completed` marker, deleting the file and exiting non-zero if either fails.
  Optional `S3_BUCKET` offsite copy; local retention pruning.
- `scripts/restore_db.sh` (new) — restores into a scratch DB **by default**, counts rows
  in five core tables, and refuses a truncated dump before dropping anything. Restoring
  over live data requires naming it in `RESTORE_TARGET` *and* typing it at a prompt.
- `docs/PROD/BACKUP_RESTORE.md` (new) — the procedure, with the real output.

**Tested for real, against this database — not described.**

```
✓ pms-20260811-183509.sql.gz ( 27M, 78 tables)

▶ restoring -> pms_restore_check
  tables: 78 · identity_user 80914 · tenant 6 · goals_goal 81566
  reviews_review 219 · audit_log 15208
✓ restore verified   (live database untouched; scratch DB dropped afterwards)

✗ /tmp/truncated.sql.gz is truncated (no 'Dump completed' marker) — do not restore it
```

**Three bugs found by running it rather than reading it**
1. `${DB_PASSWORD:?…(the app's database password)}` — the apostrophe inside a
   `${VAR:?message}` broke bash's quote parsing and failed the script with a syntax
   error reported **40 lines further down**. A comment now warns against it.
2. `MYSQL_PWD=… docker compose exec …` sets the variable on the *host* shell, where the
   in-container client never sees it → `Access denied … (using password: NO)`. Fixed by
   exporting it and forwarding by name (`-e MYSQL_PWD`), which also keeps the value out
   of the docker command line.
3. The verification queried `tenancy_tenant` and `audit_auditlog`; the real tables are
   `tenant` and `audit_log`. Both reported `n/a` — which reads like a footnote and would
   have let a genuinely missing table pass the drill. Now `MISSING`, and it fails.

**A human must**
- Set `S3_BUCKET` (or equivalent). Until then every backup shares a disk with the
  database it protects, which is the failure being insured against. Enable versioning +
  write-only credentials so host-level ransomware cannot delete the backups.
- Schedule it (cron line in the doc) and **put the monthly restore drill in the
  calendar** — it is safe, takes a minute, and touches nothing live.
- Decide RPO: nightly dumps mean up to 24h of loss; binlog archiving is needed for
  point-in-time recovery.
- Encrypt the dumps at rest — they hold every employee's performance data.

---

## Item 6 — Health + monitoring ✅ done (already strong; documented the gap)

**Verified live, not read:**

| Endpoint | Result |
|---|---|
| `/healthz` | **200** — liveness (process is up) |
| `/readyz` | **200**, and it names every dependency: `DatabaseBackend`, `DatabaseReplica`, `Cache backend: default`, `Cache backend: sessions`, `CeleryBroker`, `RedisHealthCheck`, `MigrationsHealthCheck` — all `up` |
| `/metrics` | **401** — token-gated, not disabled (correct: it is enabled and refusing an unauthenticated scrape) |

`/readyz` naming the failing dependency is the difference between a five-minute and a
fifty-minute outage, so it is the first triage step in the runbook.

**Sentry** is already correct and needs no change: no-op without `SENTRY_DSN`, lazy
import so disabling it costs nothing, **both** Django and Celery integrations (async AI
job failures are captured, not just HTTP), `send_default_pii=False`, and a `before_send`
that scrubs headers/body/cookies/extra and tags each event with `tenant_id` +
`request_id`.

**Changed** — `docs/OBSERVABILITY.md` gained a *Reading the logs* section: the actual
commands, the `[req=… tenant=…]` prefix explained against a real line, how to follow one
request across `web` and `celery-worker` with a single grep on the correlation id, `jq`
recipes for the JSON format prod emits, and a triage order that starts at `/readyz`.
Also states plainly that Docker's local driver loses logs on redeploy.

**A human must**
- Set `SENTRY_DSN` + `SENTRY_ENVIRONMENT` (blank disables cleanly — no error, no events).
- Set `METRICS_TOKEN` and point a scraper at `/metrics` **from inside the network**; the
  Caddyfile deliberately does not publish it.
- Ship logs off the host before needing to investigate last week.
- Configure alerts on the SLIs already listed in `docs/OBSERVABILITY.md`.
