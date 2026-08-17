# Overnight build — summary

**Branch: `hari/prod-hardening`** (50 commits on top of `e082597`), plus
**`hari/django-upgrade`** (4 commits, ready for review, deliberately unmerged).

Every phase was attempted. Nothing is half-committed: the tree is green at every
commit, and `docs/BUILD/PROGRESS.md` has the per-item detail with the reasoning.

**Read `## NEEDS FROM HUMAN` first** — the deployment is blocked on four
credentials and one DNS record, and nothing below can go live without them.

---

## 1. What was built

### PHASE A — mobile and UI (12 items, all done)

Started by reproducing the reported symptoms against the real Docker stack at
390×844 and 360×800, as four roles, and writing down what was actually wrong
before changing anything.

| Item | What changed |
| --- | --- |
| A0 | Inventory: **4,796 px of off-screen content, 1,249 under-sized touch targets, 6 tables wider than the viewport, 29 inputs under 16 px** |
| A1 | Root cause of the "app doesn't fit": a flexbox `min-width: auto` pushing the topbar cluster off-screen. Also added a shell-level error boundary — one component throwing was unmounting the whole app to a white screen |
| A2 | Sidebar became a real drawer below `md` instead of covering the content |
| A3 | The reported "jumps to the dashboard before painting" **did not reproduce** — measured with a 900 ms delay; the transition is correct. Fixed the real defect found instead (auth screens not full height) |
| A4 | "Good evening at midnight" — the greeting used the server's clock, not the reader's timezone |
| A5 | The "AI icons don't render" report traced to a missing asset rendering as nothing at all rather than as a fallback |
| A6 | Data tables render as stacked cards below `md` |
| A7–A9 | Forms, dialogs, sheets, charts; a 44×44 hit area on every control via a pseudo-element, so the dense desktop layout is untouched |
| A10 | Regression tests — which caught a real `nested-interactive` a11y fault I had shipped in A6 |
| A11 | Re-walked the A0 checklist: **off-screen 4,796 → 24 px, under-sized targets 1,249 → 13, wide tables 6 → 0, sub-16 px inputs 29 → 2** (`docs/BUILD/MOBILE_AUDIT.md`) |

### PHASE B — AI configuration (6 items, all done)

Per-tenant AI provider config with the key **encrypted at rest** (Fernet, only
the last four characters ever readable back), an admin surface for rotation and a
"test connection" action, and a PII scrubber extended to phone numbers and
employee ids — with a docstring stating plainly what it does *not* redact.

Two fixes worth naming: the tenant AI switch **failed open** (a missing config
meant AI enabled), and AI failures said nothing useful — a user could not tell
"no key configured" from "budget exhausted" from "the provider is down".

No live model call was made at any point. Verified against a fake provider.

### PHASE C — security and operations (14 items, all done)

| Item | What it fixed |
| --- | --- |
| C1 | CI on every push and PR — MySQL + Redis services, full pytest, frontend build |
| C2 | Containers run as uid 10001 with `cap_drop: ALL` and `no-new-privileges` |
| C3 | **Suspending a tenant did not end its sessions.** It was checked only at login, so a suspended tenant's users kept working for the token's lifetime. Now checked per request and on refresh, cached to 0 extra queries |
| C4 | `PUBLIC_APP_URL` required in prod — its default did not error, it *sent*, so every recovery email carried a dead link. Also consolidated four deployment stories into one |
| C5 | **`backup_db.sh` existed and nothing ever called it.** Now a systemd timer, offsite to GCS with versioning and lifecycle, and a weekly restore drill that checks the audit triggers survived. Proven on a real 27 MB / 78-table dump |
| C6 | The audit-immutability triggers are verified after every migration — on managed MySQL a migration can report success while never creating them |
| C7 | Self-serve signup closed until billing works |
| C8 | **Checkout returned a fabricated `cs_test_…` session and a URL that went nowhere**, with no signal that no money moved. Now an honest 501 |
| C9 | Uploaded avatars vanished on every container replacement (no volume). GCS or a named volume |
| C10 | `mockServiceWorker.js` shipped into the production build — inert, but a request-interception worker on the origin of an app holding performance reviews |
| C11 | A wrong proxy depth silently disables the login brute-force throttle. Now warns unless declared |
| C12 | **Sentry received request bodies.** Key-name redaction keeps every field whose *name* looks innocuous — which here is `draft_body`, `body`, `blockers`: the review text itself |
| C13 | Every endpoint declares what it gates; a URLconf-wide test enforces it |
| C14 | The whole stack is TLS-ready behind one variable (`DOMAIN`). It previously **could not start at all** without a domain |

### PHASE D — data subject rights (5 items, all done)

Designed before coding (`docs/BUILD/DATA_RIGHTS_DESIGN.md`), derived from the
model registry: 40 models carry a `User` FK, each sorted into subject / author /
machinery.

- **D1 export** — everything held about one employee, Admin-only, audited. Never
  egresses a feedback giver, proven by scanning the whole serialised document.
- **D2 erasure** — irreversible, one transaction, audited before it runs. Content
  *about* the person is redacted; content they *authored about others* keeps its
  text with the author repointed at a stable pseudonym.
- **D3 retention** — `LoginEvent` and `DeviceSession` purged after 90 days. They
  were kept forever, and across a tenant they are a movement log of the workforce.
- **D4** — a per-model retention reference.

Three things in D2 would each have shipped as a silent success: `.delete()` on a
tenant-scoped queryset is a **soft** delete; deleting device sessions would have
**un-revoked** live tokens; and `succession/engine.py` freezes a copy of the
person's name and email into JSON that tombstoning does not reach.

### PHASE E — real email (4 items, all done)

One sender, four flows converted, HTML + plaintext for all of them, and
`manage.py send_test_email`.

E3 found a real bug through the existing tests: Django autoescapes for HTML, so
in the **plaintext** body `&` became `&amp;` and the reset link a recipient
copies arrived with a parameter named `amp;uid`.

### PHASE F — polish (7 items: 5 done, 2 already done)

- **F1** — **nothing in the SPA ever created a performance cycle.** Goals and
  reviews both require one, so a new customer could invite their whole company
  and find both central modules switched off with no screen to switch them on.
- F2, F3 were already shipped (commit `d8a34db`).
- F4 — LICENSE, SECURITY, CONTRIBUTING, CODEOWNERS.
- F5 — 33 loose root markdown files archived; README corrected where it had
  drifted into fiction.
- F6 — OpenAPI schema at `/api/schema/`, authenticated.
- F7 — idempotency keys on submit / approve / finalize / checkout. **The first
  implementation silently did nothing on `CheckoutView`** — a mixin cannot
  intercept a method the class defines itself.

Plus a fix for a regression I introduced: F6 put 209 warnings into
`check --deploy`, burying `pms.W003`.

### PHASE G — Django upgrade (own branch, unmerged)

Django 4.2.16 → **5.2.17 LTS**, allauth 0.63.6 → 65.19.1, DRF and simplejwt with
them. **2,042 tests pass.**

It found the kind of bug this phase exists to find: simplejwt 5.4 added a user
lookup on refresh that goes through the tenant-scoped manager, which fails closed
when no tenant is bound — and refresh runs with no tenant bound by design. Every
session in the product would have failed to refresh, simultaneously, one access
token lifetime after deploy.

---

## 2. DECISIONS TAKEN

Judgement calls made without waking you. Each took the option that preserves the
invariants; each is reversible.

1. **HTTP-only is loud, not silent.** Turning off the HTTPS redirect and Secure
   cookies for a bare-IP deployment is a real reduction in security, so
   `check --deploy` reports it on every run (`pms.W003`) until `DOMAIN` is set.
   The alternative — leaving them on — is not "more secure", it is an infinite
   redirect loop and an admin who cannot sign in.

2. **Device sessions are revoked and kept, not deleted, on erasure.**
   `session_is_revoked()` reads a *missing* row as not-revoked, so deleting them
   would hand an erased account a working token. The rows are stripped instead.

3. **Erasure redacts with a marker, not an empty string.** `""` cannot be told
   apart from "nobody wrote anything".

4. **Erased rows are kept, not deleted.** Deleting a review changes every
   aggregate that counts it. Numbers stay, words go.

5. **Erasing twice returns 200, not 409.** A second call is a retry after a
   timeout; a 409 invites the caller to try something more destructive.

6. **The pseudonym is the tombstoned user row itself.** Referential integrity for
   free, and it is what makes historical audit rows render a pseudonym without
   the append-only log being touched.

7. **Audit `justification` and `metadata` are not scrubbed on erasure.** They may
   name the person. An audit log that can be edited after the fact to remove a
   name is one that can be edited after the fact.

8. **The export withholds a small group's relationship label, not its body.** The
   body is data about the subject; the label is what identifies the giver.

9. **90 days for auth-event retention** — longer than any plausible investigation,
   much shorter than forever. `AUTH_EVENT_RETENTION_DAYS=0` disables it for a
   legal hold.

10. **35-day backup retention, 14 days for superseded versions**, and object
    versioning on — versioning is what survives a bad script, which retention
    alone does not.

11. **The restore drill uses `test_restore_drill`**, borrowing the app user's
    existing grant. A drill needing elevated rights is one nobody schedules.

12. **Idempotency is opt-in.** A required header would have broken every existing
    client on the day it shipped.

13. **Only 2xx responses are stored for idempotency.** Replaying a 4xx would trap
    a client that fixed its body and retried with the same key.

14. **drf-spectacular warnings are silenced in `check --deploy`**, and documented
    where they belong. 209 known warnings made the gate unreadable.

15. **The schema endpoint requires authentication.** Not secret; not an invitation
    either.

16. **The first cycle is created ACTIVE, not DRAFT.** A DRAFT cycle leaves every
    screen looking exactly as broken, with no hint a second step exists.

17. **`OVERNIGHT_BUILD_PROMPT.md` was left at the repo root** while every other
    loose markdown file was archived — it is the live instruction for this
    session and a resume re-reads it from that path.

18. **Only four dependencies were bumped in PHASE G.** Everything else runs on
    5.2 unchanged; bumping more would mix unrelated risk into a security upgrade.

19. **`requirements.lock` is not wired into the Dockerfile.** Changing how every
    build resolves dependencies inside a framework major upgrade would leave two
    suspects for one failure.

---

## 3. NEEDS FROM HUMAN

Nothing below is code. Each is a credential, a DNS record or a console action.

### Blocking — the deployment is not safe or complete without these

**a. A GitHub token that can push.** Both branches are committed locally and
**neither is pushed**:

```
! [remote rejected] refusing to allow a Personal Access Token to create or
  update workflow `.github/workflows/ci.yml` without `workflow` scope
```

GitHub → Settings → Developer settings → Personal access tokens → edit the token
→ tick **`workflow`**. Then:

```bash
git push -u company hari/prod-hardening
git push -u company hari/django-upgrade
```

**b. SMTP credentials.** Password reset, invitations and email verification all
go to a log and reach nobody today. `check --deploy` fails with `pms.E001` until
this is set. **No code change** — exact values per provider in
`docs/BUILD/EMAIL.md`:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=…   EMAIL_PORT=587   EMAIL_HOST_USER=…   EMAIL_HOST_PASSWORD=…
DEFAULT_FROM_EMAIL="Axiom <no-reply@your-domain.com>"
EMAIL_REPLY_TO=support@your-domain.com
```

Verify from the VM:
```bash
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py send_test_email you@your-domain.com
```

**c. The backup timers, installed.** The scripts work and are proven; nothing
runs them until the units are installed. Until then **there are no backups.**

```bash
GCS_BUCKET=gs://axiom-backups GCP_PROJECT=<project> ./scripts/gcs_backup_setup.sh
gsutil iam ch serviceAccount:<VM_SA>:roles/storage.objectAdmin gs://axiom-backups
sudo install -m 0600 /dev/null /srv/pms/.env.backup   # DB_PASSWORD, SENTRY_DSN
sudo cp deploy/systemd/pms-backup.{service,timer} /etc/systemd/system/
sudo cp deploy/systemd/pms-restore-drill.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pms-backup.timer
sudo systemctl start pms-backup.service    # prove it now, not at 02:15
```
Full steps, including the weekly drill timer: `docs/BUILD/BACKUP_RESTORE.md`.

**d. `DJANGO_NUM_PROXIES`, declared.** It defaults to 1 (correct for Caddy
alone) and `pms.W002` warns until you say so out loud. Wrong value → the login
brute-force throttle silently stops working. `1` for Caddy alone, `2` behind a
CDN.

### Needed for HTTPS

**e. A DNS A record** pointing a hostname at the VM's external IP, then:

```bash
DOMAIN=pms.your-domain.com
ACME_EMAIL=ops@your-domain.com
PUBLIC_APP_URL=https://pms.your-domain.com
DJANGO_ALLOWED_HOSTS=pms.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://pms.your-domain.com   # scheme included
```

Open ports 80 **and** 443. **Verify DNS resolves before setting `DOMAIN`** —
Let's Encrypt allows 5 failures per hostname per hour, and burning that window
costs an hour whatever you fix. Click-by-click: `docs/BUILD/ENABLE_TLS.md`.

### Needed for the AI features

**f. The Gemini Enterprise key**, entered per tenant by an admin in
Admin → AI. Until then every AI surface says *not configured* and never
fabricates. Nothing to deploy.

### Optional but recommended

- `SENTRY_DSN` in `/srv/pms/.env.backup` — otherwise a failed backup is a line in
  a log nobody reads.
- `USE_GCS_MEDIA=true` + `GS_BUCKET_NAME` — otherwise avatars live on the named
  volume rather than object storage.
- `SUPPORT_EMAIL` / `VITE_SUPPORT_EMAIL` — currently the obvious placeholder
  `support@example.com`.
- **Counsel-approved copy for `/privacy` and `/terms`.** Both carry a visible
  "Draft — pending legal review" banner, with a test asserting it is there.
- **Branch protection** on `main` — `docs/BUILD/CI.md` has the click path.

---

## 4. DEPLOY SEQUENCE

For `hari/prod-hardening`. **Not** the Django upgrade branch — that is reviewed
and deployed separately.

```bash
# ── 0. On the VM, in /srv/pms ────────────────────────────────────────────────
gcloud compute ssh pms-prod --zone asia-south1-a
cd /srv/pms

# ── 1. BACK UP FIRST. This deploy includes migrations. ───────────────────────
set -a; . ./.env.backup; set +a
GCS_BUCKET=gs://axiom-backups ./scripts/backup_db.sh
# expect: "✓ …sql.gz (NNM, NN tables)" then "✓ offsite copy stored"

# ── 2. Prove that backup is restorable BEFORE changing anything ──────────────
GCS_BUCKET=gs://axiom-backups ./scripts/restore_drill.sh --from-bucket
# all three checks must pass; if not, STOP — do not deploy without a rollback

# ── 3. Fetch and build ──────────────────────────────────────────────────────
git fetch company && git checkout hari/prod-hardening && git pull
docker compose -f docker-compose.prod.yml build web frontend

# ── 4. Confirm the environment before it can fail at runtime ────────────────
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py check --deploy
#   pms.E001 → SMTP is not configured (blocking)
#   pms.W003 → still HTTP-only (expected until DNS exists)
#   pms.W002 → declare DJANGO_NUM_PROXIES

# ── 5. Migrate ONCE (advisory-locked; also verifies the audit triggers) ─────
docker compose -f docker-compose.prod.yml run --rm migrate

# ── 6. Roll ─────────────────────────────────────────────────────────────────
docker compose -f docker-compose.prod.yml up -d web celery-worker celery-beat frontend caddy
```

### Post-deploy verification

```bash
# a. Alive and ready (readyz probes MySQL, both Redis instances and the broker)
curl -sS http://<IP>/healthz && echo && curl -sS http://<IP>/readyz

# b. The audit triggers survived the migration — this is the compliance
#    invariant, and a managed MySQL can drop them without erroring
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py verify_audit_triggers

# c. No pending migrations
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py migrate --check

# d. A real sign-in, in a browser. Then, if SMTP is configured, request a
#    password reset and CLICK the link in the email — that one click exercises
#    PUBLIC_APP_URL, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS and the token together.

# e. The mock service worker is not being served (it would be a 404)
curl -sS -o /dev/null -w '%{http_code}\n' http://<IP>/mockServiceWorker.js   # 404

# f. Checkout is honest about not taking money
curl -sS -X POST http://<IP>/api/billing/checkout -H 'Authorization: Bearer <admin>' \
  -H 'Content-Type: application/json' -d '{"plan":"PROFESSIONAL"}'          # 501

# g. Backups are scheduled and actually ran
systemctl list-timers 'pms-*'
gsutil ls -l gs://axiom-backups | tail -3
```

### Rolling back

```bash
git checkout <previous-sha> && docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml up -d web celery-worker celery-beat
```

Migrations in this branch are additive (`erased_at`, the idempotency table), so a
code rollback alone is safe — the older code ignores both. Only restore the
database if something else has gone wrong; the procedure is in
`docs/BUILD/BACKUP_RESTORE.md`, and **a restore must be followed by re-running
any erasure performed since that backup was taken.**

---

## 5. NOT DONE

Stated so each is a known gap rather than a surprise.

**Blocked on a credential or a decision** (built to the line, nothing more to code):

- **HTTPS** — no domain. One variable away.
- **Email delivery** — no SMTP provider. Env vars away.
- **Live payments** — `create_checkout` is an honest 501. Wiring a provider SDK
  is a supervised decision, not an overnight one.
- **AI output** — no Gemini key. Every surface reports *not configured*.
- **Both branches unpushed** — the token lacks `workflow` scope.

**Deliberately not attempted:**

- **The Django upgrade is not merged.** It is committed, green (2,042 tests) and
  documented. Merging a framework major without a human reading the
  refresh-serializer override would be the wrong call — that override reaches
  into a third-party auth path and its failure mode is "nobody can stay signed
  in".
- **`requirements.lock` is not used by the image.** Separate PR, after the
  upgrade lands.
- **No automated tenant-deletion flow.** An irreversible "delete everything for
  this customer" button is a support incident waiting to happen.

**Real limitations, documented where they live:**

- **193 API endpoints have no request/response body in the OpenAPI schema.** The
  paths are all there. Most views are plain `APIView`s with nothing to
  introspect; the two data-rights endpoints are annotated as the worked example.
  (`docs/BUILD/API_SCHEMA.md`)
- **RPO is 24 hours.** Nightly dumps, no binlog shipping. Worst case a day of
  performance data is lost. Closing it means binlog shipping or Cloud SQL PITR —
  a cost decision. (`docs/BUILD/BACKUP_RESTORE.md`)
- **Media is not in the database backup.** Only MySQL is dumped.
- **Erasure does not reach backups.** Pre-erasure rows persist until the archive
  ages out at 35 days.
- **The audit log keeps free-text `justification` and `metadata`** that may name
  an erased person. Deliberate — see decision 7.
- **allauth's conditional unique constraint on verified emails is not created by
  MySQL** (upgrade branch only). Nothing depends on it today.
- **13 touch targets remain under 44 px and 2 inputs under 16 px** — all inside
  third-party chart internals. (`docs/BUILD/MOBILE_AUDIT.md`)

**One process note:** running two `pytest` processes against this stack at once
produces dozens of spurious failures — they share one test database. Both suites
pass cleanly run one at a time.
