# Continuous integration

`.github/workflows/ci.yml` runs on **every push and every pull request, on any
branch**.

Before it existed, ~1,860 backend tests and ~180 frontend tests only ran when a
human remembered to run them. That is the single cheapest gap in the repo to
close, and it is the one an enterprise security questionnaire asks about first.

---

## What runs

### Job 1 — `test` (the gate)

| Step | Why it is there |
|---|---|
| MySQL 8.0 + Redis 7 as services | `config/settings/test.py` requires both on purpose: the audit-log immutability triggers are raw MySQL DDL, and tenant cache invalidation uses django-redis' `delete_pattern`. Neither survives a substitute. |
| `GRANT ALL ON test\_%.*` to the app user | pytest-django creates a throwaway `test_pms` database. Mirrors `db/init.sql`. |
| `SET GLOBAL log_bin_trust_function_creators = 1` | Without it a non-SUPER user cannot create the `audit_log` triggers and migration `audit/0002` fails. This is the same footgun that silently drops audit immutability on managed MySQL — CI now proves the triggers can be created. |
| `pytest -q` | `pytest.ini` already deselects `live_ai` and `large_tenant`, so CI never makes a paid model call and never seeds a 1k-employee tenant. |
| `npm ci` + `npm run test` | Frontend unit + a11y suites. |
| `npm run build` | Catches what tests cannot: type errors, broken imports, a bundle that will not build. `VITE_USE_MOCKS=false` is pinned so no CI artifact can carry the passwordless mock layer. |

`PMS_DOTENV_PATH` points at a nonexistent path so a stray `.env` can never leak a
developer's settings into a CI run.

### Job 2 — `audit` (advisory, non-blocking)

`pip-audit -r requirements.txt` and `npm audit --audit-level=high`.

`continue-on-error: true` is deliberate. A new advisory against a transitive
dependency should tell us within the hour; it should not block an unrelated fix
at 2am, because the failure is upstream and the fix is usually a version bump
nobody can make right then. Read it, don't be ruled by it.

> Expect this job to be red on the first run: Django 4.2 is past its security
> support window (see `docs/BUILD/DJANGO_UPGRADE.md` / PHASE G). That is a known,
> tracked finding, not a surprise.

### Credentials in the workflow file

The MySQL passwords in `ci.yml` are literal strings ending `-not-a-secret`. They
are the credentials of a throwaway container that exists for the ~10 minutes of a
CI run, is reachable only from that job, and holds nothing but generated test
data. They are not secrets and are not treated as such. **No real credential goes
in this file** — anything genuinely secret belongs in repository secrets and is
referenced as `${{ secrets.NAME }}`.

---

## Branch protection — a human step in the GitHub UI

The workflow proves the tests pass. It does not stop anyone merging when they
don't. Turning that on is a repository-settings change and cannot be done from
the repo:

1. GitHub → the repository → **Settings** → **Branches**
2. **Add branch ruleset** (or *Add rule* on older UI)
3. Name it `main protection`, target branch `main`
4. Enable:
   - **Require a pull request before merging**
     - Required approvals: `1` (drop to 0 while there is a single developer, but
       leave the PR requirement on — it is what makes the check block a merge)
   - **Require status checks to pass before merging**
     - Add the check: **`Tests (backend + frontend)`**
     - Tick **Require branches to be up to date before merging**
   - **Require conversation resolution before merging**
   - **Block force pushes**
   - **Restrict deletions**
5. Do **not** add the `Dependency audit (advisory)` check as required — it is
   advisory by design.
6. Save.

Repeat for `hari/prod-hardening` if that branch is treated as deployable.

### Verify it took

Open any PR and confirm the merge button is disabled until *Tests (backend +
frontend)* is green. If it is not, the check name in the ruleset does not match
the job's `name:` in `ci.yml`.

---

## Running the same thing locally

```bash
# Backend — needs the docker stack up
docker compose up -d mysql redis
docker compose run --rm web pytest -q

# Frontend
npm --prefix frontend ci
npm --prefix frontend run test
npm --prefix frontend run build
```

## When CI is slower than it should be

The backend suite is ~8 minutes and dominated by database setup. Before reaching
for parallelism, note that `pytest -n auto` (pytest-xdist) is **not** installed
and would need each worker to build its own test database — with MySQL that is
usually slower, not faster, at this suite size.
